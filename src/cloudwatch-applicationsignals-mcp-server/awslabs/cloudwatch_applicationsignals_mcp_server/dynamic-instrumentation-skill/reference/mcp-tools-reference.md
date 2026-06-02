# MCP Tools Quick Reference

## Dynamic Instrumentation Tools (applicationsignals MCP)

### create_instrumentation

Create a breakpoint or probe at a code location.

```python
create_instrumentation(
    # Required
    instrumentation_type="BREAKPOINT",  # or "PROBE"
    service="order-service",
    environment="beta",
    language="Python",  # or "Java"
    file_path="/app/service.py",

    # Location (optional - refine target)
    code_unit="mymodule",           # module (Python) or package (Java)
    class_name="MyClass",           # class name (mainly Java)
    method_name="my_function",      # function/method name
    line_number=42,                 # specific line (line-level breakpoint)

    # Capture config
    capture_arguments=["arg1", "arg2"],  # REQUIRED - explicit argument names
    capture_return=True,                 # default: True
    capture_stack_trace=True,            # default: True
    capture_locals=["var1", "var2"],     # local vars (line-level only)
    max_hits=100,
    ttl_hours=24  # recommended for debugging sessions
)
```

**Important**:
- `capture_arguments` is required. The MCP does not infer argument names. Read the target source file directly to discover argument names before creating.
- `capture_arguments=["*"]` is not supported; wildcards are stripped.
- `description` must be **50 characters or fewer**. Keep it short (e.g., "debug auth 403", "check cache key"). The API rejects longer descriptions.

**Returns**:
- `LocationHash` (16-char hex) - save this for later operations!
- `CreatedAt` (ISO 8601 timestamp) - useful reference when choosing the status query time window

---

### list_instrumentations

List all active instrumentations for a service/environment.

```python
list_instrumentations(
    service="order-service",
    environment="beta",
    instrumentation_type="BREAKPOINT"  # or "PROBE"
)
```

---

### get_instrumentation

Get static configuration details. Supports lookup by hash or by code location.

```python
# By location hash (preferred)
get_instrumentation(
    service="order-service",
    environment="beta",
    instrumentation_type="BREAKPOINT",
    location_hash="abc123def4567890"
)

# By code location
get_instrumentation(
    service="order-service",
    environment="beta",
    instrumentation_type="BREAKPOINT",
    language="Python",
    file_path="/app/service.py",
    method_name="my_function"
)
```

---

### delete_instrumentation

Remove a single instrumentation. Supports lookup by hash or by code location.

```python
delete_instrumentation(
    service="order-service",
    environment="beta",
    instrumentation_type="BREAKPOINT",
    location_hash="abc123def4567890"
)
```

---

### batch_delete_instrumentations_by_scope

Delete all instrumentations matching a service/environment/type.

```python
batch_delete_instrumentations_by_scope(
    service="order-service",
    environment="beta",
    instrumentation_type="BREAKPOINT"
)
```

Use this for cleanup at the end of a debugging session when multiple breakpoints exist.

---

### check_instrumentation_status (preferred)

Consolidated status check in one call.
The `created_at` timestamp is automatically fetched from the instrumentation configuration.
`start_time` and `end_time` are required.

```python
check_instrumentation_status(
    service="order-service",
    environment="beta",
    instrumentation_type="BREAKPOINT",
    location_hash="abc123def4567890",  # from create response

    # Required time range
    start_time="2026-02-12T22:00:00Z", # explicit status query start
    end_time="2026-02-12T23:00:00Z"    # explicit status query end
)
```

**Returns**: Consolidated status report with:
- ACTIVE status (confirmed/not confirmed)
- READY status (confirmed/not confirmed)
- ERROR status (confirmed/not confirmed)
- OVERALL STATUS: ACTIVE | READY | ERROR | PENDING
- SNAPSHOT QUERY TIP with timestamp for `search_snapshots_for_status_event`

**Use this instead of multiple `get_instrumentation_configuration_status` calls!**

---

### get_instrumentation_configuration_status

Get status history for a specific status. **Use `check_instrumentation_status` instead for normal workflow.**

Use this tool for:
- Checking DISABLED status (hit-limit scenarios)
- Custom time range queries
- Paginating large event sets

```python
get_instrumentation_configuration_status(
    service="order-service",
    environment="beta",
    instrumentation_type="BREAKPOINT",
    location_hash="abc123def4567890",

    # Required - explicit status
    status="DISABLED",                  # or READY/ACTIVE/ERROR

    # Optional filters
    start_time="2025-01-15T00:00:00Z",  # time range
    end_time="2025-01-15T23:59:59Z"
)
```

**Returns**: Status + list of events with timestamps
**Important**:
- Do not omit `status` to query "all statuses" (API defaults to ACTIVE when omitted)
- A status is confirmed only when status events are present (not from CURRENT STATUS alone)
- Prefer `check_instrumentation_status` for the standard consolidated status check flow

---

### get_sample_snapshot_for_breakpoint

Fetch one snapshot to discover structure before building filters.

```python
get_sample_snapshot_for_breakpoint(
    service_name="order-service",
    environment="beta",
    location_hash="abc123def4567890",
    status_timestamp="2025-01-15T10:42:00Z"  # from status event
)
```

**Parameters**:
- `include_raw` (bool, default False) — When False, snapshots larger than 10 KB are replaced with a compact parsed summary. Set True to force the full raw snapshot.

**Returns**: JSON with one sample snapshot. For small snapshots (≤10 KB), the full raw snapshot is returned. For large snapshots (>10 KB), a parsed summary is returned with:
- `sample_snapshot.entry_arguments` — argument names and previewed values at entry
- `sample_snapshot.return_value` — return value (primitives shown directly, objects show `fields_preview` with one level of values expanded)
- `sample_snapshot.entry_locals` / `return_locals` — local variables
- `sample_snapshot.throwable` — exception info if thrown
- `sample_snapshot.line_local_previews` — local variables at instrumented lines
- `sample_snapshot.duration_ms` — execution time in milliseconds (method-level only)
- `sample_snapshot.location` — breakpoint location metadata
- `sample_snapshot.trace` — trace context (traceId, spanId)
- `sample_snapshot.stack_preview` — top 5 stack frames
- `note` — present when raw snapshot was replaced; suggests using `include_raw=True`
- `field_documentation` — explains each field's meaning and filter patterns

---

### search_snapshots_for_status_event

Query CloudWatch Logs for captured snapshot data. **Use the timestamp from status events!**

```python
search_snapshots_for_status_event(
    service_name="order-service",
    environment="beta",
    location_hash="abc123def4567890",
    status_timestamp="2025-01-15T10:42:00Z",  # from status event
    custom_filters=[
        '@message like /"arguments"/ and @message like /"order_id"/'
    ]
)
```

**Returns**: JSON with snapshot data including:
- `snapshot_summaries` — compact list with timestamp, snapshot_id, traceId, spanId, location_hash
- `results` — raw CloudWatch query results (each with `@timestamp` and `@message` containing full snapshot JSON)
- `query_string` — the actual Logs Insights query used
- Parse `results[*].@message` as JSON to access `captures` data for correlation analysis

---

### Inspecting source code

The applicationsignals MCP does not provide a source-inspection tool. To discover
argument names and code structure before creating a breakpoint, read the target
source file directly with your local file-reading tools.

**Do this when**:
- You need to verify exact argument names before `create_instrumentation`
- You're unsure about the code structure around a target line
- The function signature is complex or has many parameters

---

## Status State Reference

| Status | Meaning | Next Action |
|--------|---------|-------------|
| `READY` | Waiting for traffic | Notify customer, wait |
| `ACTIVE` | Confirmed only when ACTIVE status events exist | Wait 2-3 min, query snapshots |
| `ERROR` | Instrumentation failed | Check ErrorCause, notify customer |
| `DISABLED` | Hit limit exceeded | Query with earlier time range |

## Error Causes

| ErrorCause | Meaning |
|------------|---------|
| `FILE_NOT_FOUND` | File path doesn't match running app |
| `METHOD_NOT_FOUND` | Function not found or not loaded |
| `LINE_NOT_EXECUTABLE` | Line is comment/blank/declaration |
| `OVERLOADED_METHODS` | Ambiguous method (Java) |
| `LANGUAGE_MISMATCH` | Wrong language specified |
| `RUNTIME_ERROR` | Other runtime error |
