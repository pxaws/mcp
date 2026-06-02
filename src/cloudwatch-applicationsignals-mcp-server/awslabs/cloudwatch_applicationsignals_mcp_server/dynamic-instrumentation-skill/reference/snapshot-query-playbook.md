# Snapshot Query Playbook

Use this when `search_snapshots_for_status_event` returns too much noise, too little signal, or no hits.

## Field Meaning Quick Map

- `captures.entry.arguments.<name>`: captured function input argument at entry.
- `captures.return.arguments.<name>`: captured function argument at return (may show mutation).
- `captures.return.returnValue`: captured function return value.
- `captures.return.throwable`: exception info if function threw.
- `captures.entry.locals.<name>` / `captures.return.locals.<name>`: local variables.
- `captures.lines.<line>.locals.<name>`: local variable at specific line (line-level breakpoint).
- `instrumentation.location.methodName`: instrumented method/function.
- `instrumentation.location.filePath`: source path.
- `locationHash`: breakpoint identifier for grouping.
- `trace.traceId`: end-to-end request correlation ID.
- `duration`: snapshot duration in milliseconds (top-level field, method-level only).
- `stack[*]`: call stack frames with `fileName`, `function`, `lineNumber`.

## Pattern Templates for custom_filters

Snapshot logs are JSON. Use JSON field access for top-level/shallow fields (faster, exact match). Use `@message like` for deep nested captures.

**JSON field filters (preferred for known fields):**
- Method name:
  - `instrumentation.location.methodName = "<method_name>"`
- Trace ID:
  - `trace.traceId = "<trace_id>"`
- Duration threshold:
  - `duration > <ms>`

**Regex filters (for deep nested capture data):**
- Argument by name:
  - `@message like /"arguments"/ and @message like /"<param_name>"/`
- Argument by value:
  - `@message like /"<param_name>"/ and @message like /(?i)"<value>"/`
- Return value contains marker:
  - `@message like /"returnValue"/ and @message like /(?i)"<value>"/`
- Specific local variable:
  - `@message like /"locals"/ and @message like /"<var_name>"/`
- Specific line event:
  - `@message like /"lines"/ and @message like /"<line_number>"/`
- Throwable/exception:
  - `@message like /"throwable"/ and @message like /"<exception_type>"/`
- Exclude noisy traffic:
  - `@message not like /(?i)healthcheck|metrics|warmup/`

## Adaptation Strategy

1. Start with `locationHash` + narrow time window + no extra filters.
2. Add exactly one focused filter (argument/local/return/method) when narrowing.
3. If zero hits, remove the last restrictive filter before widening time range.
4. For intermittent issues, start with `limit=20` and increase gradually (20 → 50 → 100) if patterns are not found.
5. When one suspicious request is found, pivot by `traceId` and inspect related snapshots.

## Using get_sample_snapshot_for_breakpoint

Before crafting custom filters, always call `get_sample_snapshot_for_breakpoint` first:

1. It returns one snapshot showing the data structure and available fields.
2. The `field_documentation` explains each field's meaning and provides filter patterns.
3. For large snapshots (>10 KB), a compact parsed summary is returned with `fields_preview` showing one level of object field values — enough to construct targeted filters.
4. Use the discovered field names and values to build `custom_filters` for `search_snapshots_for_status_event`.

## Filter Combination Examples

### Find slow invocations with specific argument
```python
custom_filters=[
    'duration > 1000',
    '@message like /"arguments"/ and @message like /"product_id"/'
]
```

### Find exceptions of a specific type
```python
custom_filters=[
    '@message like /"throwable"/',
    '@message like /"ValueError"/'
]
```

### Find snapshots for a specific trace
```python
custom_filters=[
    'trace.traceId = "abc123def456"'
]
```

## Discovery Analysis — Finding Anomalies Without a Known Target

When you don't know which specific request/entity is problematic, use broad fetch + file-based aggregation.

### The Pattern

```
1. FETCH   — broad batch (limit=20, increase gradually if needed), no custom_filters
2. SAVE    — write raw results to a working file (or use auto-persisted file)
3. NARRATE — explain what fields you'll extract and what anomaly pattern you're looking for
4. AGGREGATE — use jq/python against the file to group and surface anomalies
5. DRILL IN — switch to targeted filters (Mode A) for flagged cases
```

### Step 1-2: Fetch and Save

Fetch a broad batch with `limit=20`. If multiple ACTIVE event timestamps exist, search them
in parallel for broader coverage. If no anomaly patterns emerge, gradually increase the limit
(20 → 50 → 100).

Large tool results are auto-persisted by the platform to a file path shown in the output.
The persisted file has a wrapper format `{"result": "<escaped JSON>"}`. Unwrap before analysis:

```python
# Python — unwrap auto-persisted result file
import json
with open("/path/to/auto-saved-results.txt") as f:
    data = json.loads(json.loads(f.read())["result"])
# data["results"] is the list of snapshot records
```

```bash
# jq — unwrap auto-persisted result file
jq -r '.result' "/path/to/auto-saved-results.txt" | jq '.' > snapshots-<location_hash>.json
```

When combining results from parallel queries (multiple timestamps), deduplicate by
snapshot `id` before aggregating to avoid double-counting overlapping windows.

### Step 3-4: Narrate and Aggregate

**Before running any jq command, narrate:**
- What data you have (e.g., "50 FraudService.authorize snapshots")
- What you don't know (e.g., "which orderId is being double-charged")
- What grouping/aggregation you'll apply and why
- What the result would mean

**Find duplicate values** (e.g., same orderId with different paymentRefs):
```bash
jq '[.results[] | .["@message"] | fromjson
  | { key:   .captures.return.returnValue.fields.orderId.value,
      value: .captures.return.returnValue.fields.paymentRef.value }]
  | group_by(.key)
  | map({ key: .[0].key, values: ([.[].value] | unique), count: length })
  | map(select(.values | length > 1))' snapshots-<hash>.json
```

**Find outliers by frequency** (e.g., IDs that appear more often than expected):
```bash
jq '[.results[] | .["@message"] | fromjson
  | .captures.return.returnValue.fields.orderId.value]
  | group_by(.) | map({ value: .[0], count: length })
  | sort_by(-.count) | .[:5]' snapshots-<hash>.json
```

**Extract field distributions** (e.g., compare argument values across snapshots):
```bash
jq '[.results[] | .["@message"] | fromjson
  | { id:    .captures.entry.arguments.arg0.value,
      field: .captures.entry.arguments.arg1.value }]
  | group_by(.id)
  | map({ id: .[0].id, values: [.[].field] | unique })' snapshots-<hash>.json
```

**Adapt the jq field paths** to match your sample snapshot structure — use
`get_sample_snapshot_for_breakpoint` output to identify the correct paths.

### Step 5: Drill In

Once anomalous cases are identified, switch to targeted filters:
```python
# Example: drill into a specific overcharged order
custom_filters=['@message like /"ORD-00002B2C"/']
```
