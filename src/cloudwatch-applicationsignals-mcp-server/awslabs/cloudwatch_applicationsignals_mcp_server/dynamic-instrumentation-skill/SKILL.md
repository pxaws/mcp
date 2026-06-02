---
description: "Interactive debugging using AWS Application Signals Dynamic Instrumentation. Place breakpoints on running services, capture snapshots, and perform evidence-based root cause analysis with correlation-driven methodology."
---

# Dynamic Instrumentation Debugging Skill

This skill enables AI agents to perform **interactive, evidence-based debugging** using AWS Application Signals Dynamic Instrumentation. The agent works collaboratively with the user, explaining reasoning, proposing actions, and waiting for confirmation before proceeding.


## Core Principles

### 1. Evidence Before Conclusions
**NEVER state a root cause or conclusion without snapshot data evidence.**

```
WRONG: "Based on the code, the cache key mismatch is causing the latency issue."
RIGHT: "I suspect cache key mismatch may be involved. Let me set a breakpoint
        to capture the actual keys and confirm this hypothesis with data."
```

### 2. User Confirmation Required
**Before taking any significant action, explain your reasoning and ask for confirmation.**

For each step:
1. **Explain** what you observed and your reasoning
2. **Propose** the specific action you want to take
3. **Show** the details (breakpoint parameters, query parameters, etc.)
4. **Ask** for user confirmation or modifications

### 3. No Autonomous Debugging
The agent should NOT proceed through multiple debugging steps without user involvement. Each action requires explicit approval.

**Exception:** If the user explicitly grants upfront approval to proceed without per-step confirmation (e.g., "you have my full approval, don't ask me, just go ahead"), run the investigation autonomously. Still narrate before acting (rule 4) so the user can follow along, but do not pause for approval at each step.

### 4. Narrate Before Acting
**Before every significant action — not just breakpoint creation — explain your reasoning.**

For each step (including analysis commands like jq/python):
1. **What** you're about to do
2. **Why** — what question this action answers
3. **What you expect to learn** from the result

Analysis steps (jq aggregations, python scripts) are often the most important part of debugging. Don't let them be a silent black box — the user should understand what pattern you're looking for before you run the command.

```
WRONG: [silently runs jq command, then shows results]
RIGHT: "I have 50 snapshots but don't know which orders are problematic.
        I'll extract orderId and paymentRef from each snapshot, group by orderId,
        and look for any orderId that has more than one distinct paymentRef —
        which would indicate a duplicate charge.
        [runs jq command]
        Results: 4 out of 35 orders have duplicate paymentRefs."
```


## Debugging Methodology

This is the reasoning framework that drives the entire debugging process. Every decision — where to place breakpoints, what data to look at, where to go next — is guided by this methodology.

### The Core Loop

Debugging is an iterative search through a **correlation space**. Each cycle:

```
1. HYPOTHESIZE — form a testable prediction about what value/behavior causes the problem
2. INSTRUMENT  — place a breakpoint to capture the specific data that would prove or disprove it
3. OBSERVE     — collect snapshot data from the running application
4. CORRELATE   — analyze which captured values correlate with the problem
5. DECIDE      — based on the correlation result, choose the next direction
```

The key insight: **each breakpoint is a probe that tests a specific correlation hypothesis.** You are not randomly inspecting code — you are systematically narrowing down which value, in which function, causes the observed problem.

### What Makes a Good Hypothesis

A good hypothesis is **tied to an observable value** and is **testable with a breakpoint**:

```
WEAK:  "Something is wrong in the payment flow"
       (too vague — what would you capture? what would confirm it?)

GOOD:  "I suspect calculate_shipping() is slow for international addresses
        because it makes an uncached API call"
       (testable: capture address argument + measure duration
        confirm: international addresses show high duration, domestic don't)

GOOD:  "I suspect the auth check uses a stale user ID from the wrong context"
       (testable: capture the user ID argument at the auth check
        confirm: the captured ID doesn't match the actual request's user)
```

### Correlation Analysis — The Analytical Framework

After collecting snapshot data, systematically check these four correlation categories. This is what transforms raw data into debugging direction:

**1. Input correlation** — Do certain argument values co-occur with failures?
- Check `captures.entry.arguments` across multiple snapshots
- Look for: unexpected values, edge cases, specific patterns that only appear in failing cases
- If suspicious inputs found -> go **upstream** to find who passed them

**2. Return correlation** — Does the output indicate wrong behavior?
- Check `captures.return.returnValue` and `captures.return.throwable`
- Look for: wrong results, null where non-null expected, exceptions
- If inputs look correct but output is wrong -> go **downstream** (inside the function)

**3. Local-state correlation** — Do intermediate values drive wrong branches?
- Check `captures.lines.<line>.locals` or `captures.return.locals`
- Look for: variables with unexpected values at conditional branches, loop counters, flags
- If you need to trace variable changes -> go **line-level** within the same function

**4. Cross-snapshot correlation** — What differs between good and bad cases?
- Compare multiple snapshots from the same breakpoint
- Look for: what's different in the inputs/outputs/locals between successful and failing invocations
- If the issue is intermittent -> use **multi-snapshot comparison** with higher `max_hits`

**After each analysis, state a verdict**: correlation confirmed, disproven, or inconclusive. This verdict determines your next move.

### Direction Choices — Where to Go Next

Based on the correlation analysis, choose one of these directions for the next iteration:

**Upstream (Caller)** — The inputs look suspicious and you need to find where they came from.
- Look at `stack[*]` frames to identify the calling function
- Set breakpoint in the caller to see what inputs were passed and why
- Example: Argument `discount = -50` is clearly wrong -> go upstream to find who passed it

**Downstream (Callee)** — The inputs look fine but the return value is wrong. The problem is inside.
- Identify functions called within the current function
- Set breakpoint in the callee to measure its duration/behavior
- Example: `calculate_total(items)` receives valid items but returns `0` -> go inside

**Line-level (Same Function)** — You need to see intermediate state within the function.
- Set breakpoint at a specific line number with `capture_locals`
- Use before/after suspicious assignments or at conditional branches
- Example: `if (found)` takes the wrong branch -> capture `found` value just before the `if`

**Multi-snapshot Comparison** — The issue is intermittent and you need to find the pattern.
- Set breakpoint with higher `max_hits` (e.g., 50-100)
- Query multiple snapshots and compare systematically
- Example: 1 in 10 requests fails -> capture 20 snapshots and find what differs


## Canonical Workflow

### Phase 1: Intake and Planning

1. Collect required inputs (service, environment, problem description, source paths).
2. Read relevant source files to understand the code.
3. Build a compact call graph of the suspected area.
4. Check whether candidate entry point is auto-instrumented (if so, skip it — place breakpoints on internal functions instead).
5. Form one explicit hypothesis tied to an observable value (see "What Makes a Good Hypothesis").
6. Propose one or more breakpoints with **code snippet** and request user confirmation.

Breakpoint proposal must include:
- location (`file_path`, `code_unit`, `class_name`, `method_name`, `line_number` if line-level)
- **code snippet** (see "Code Snippet Display" section)
- capture plan (`capture_arguments` with explicit names, `capture_return`, `capture_locals`, `max_hits`)
- `ttl_hours=24`
- what correlation you expect to find (e.g., "I expect slow requests to correlate with large item lists")

### Phase 2: Instrument and Validate

1. Create breakpoint(s) only after user confirms.
2. If uncertain about exact argument names, read the target source file directly to verify before calling `create_instrumentation`.
3. Wait at least 2 minutes for status events to appear.
4. Use `check_instrumentation_status` to check the breakpoint status.
5. Interpret status and act accordingly (see "Status API Rules").

### Phase 3: Observe and Analyze

1. Fetch one sample snapshot with `get_sample_snapshot_for_breakpoint` to discover structure.

2. **Choose analysis mode based on what you know:**

   **Mode A — Targeted analysis** (you have a specific value to search for):
   Use `custom_filters` to narrow to known targets (specific traceId, orderId, error type, duration threshold, etc.).
   Suitable when you already know which request/entity is problematic.

   **Mode B — Discovery analysis** (you need to find the anomaly pattern):
   When you don't yet know which specific values are problematic:
   a. **Fetch a broad batch**: `search_snapshots_for_status_event` with `limit=20`, no `custom_filters` beyond the default locationHash scope. If multiple ACTIVE event timestamps exist, search them in parallel for broader coverage. If the initial batch shows no clear anomaly pattern, gradually increase the limit (e.g., 20 → 50 → 100).
   b. **Save results to a file**: Large result sets can exceed context window limits and may be auto-persisted by the platform to a file (shown in the tool output). The persisted file has a wrapper format `{"result": "<escaped JSON>"}` — unwrap it with `json.loads(json.loads(open(file).read())['result'])` before analysis. For smaller results, save manually using Bash redirection or the Write tool. All subsequent analysis operates on the saved file, not on context window contents.
   c. **Aggregate locally**: Use jq or python against the saved file to extract key fields, group by a domain identifier (e.g., orderId, userId), and surface anomalies (duplicates, outliers, unexpected values). When combining results from multiple parallel queries, deduplicate by snapshot `id` before aggregating. See `reference/snapshot-query-playbook.md` for jq templates.
   d. **Identify anomalous cases** from the aggregation output.
   e. **Switch to Mode A** to drill into those specific cases with targeted filters.

   **Narrate** (Principle 4): Before running the aggregation, explain what fields you're extracting, what grouping you're applying, and what anomaly pattern you're looking for.

3. **Run the correlation analysis** (the four categories above) on the collected data.
4. **State your correlation verdict**: confirmed, disproven, or inconclusive.
5. **Choose your next direction** based on the verdict (upstream, downstream, line-level, or multi-snapshot).
6. Present findings and proposed next action to the user. Get confirmation before proceeding.
7. Repeat the core loop until evidence is sufficient.

### Phase 4: Closure

1. Summarize root cause with explicit **correlation chain**: `[input value] -> [intermediate effect] -> [observed problem]`.
2. Provide recommendations.
3. Ask user whether to delete breakpoints.
4. Delete if requested:
   - `delete_instrumentation` for individual breakpoints
   - `batch_delete_instrumentations_by_scope` to delete all breakpoints for the service/environment


## Critical Rules

1. Never claim root cause without snapshot-data evidence.
2. Use `check_instrumentation_status` (preferred) for consolidated status checks.
3. Always wait at least 2 minutes after creating a breakpoint before status checks.
4. Always set `ttl_hours=24` for breakpoints.
5. Always use `get_sample_snapshot_for_breakpoint` first to discover snapshot data structure before running `search_snapshots_for_status_event`.
6. `capture_arguments` is required — the MCP does not infer argument names.
7. `description` must be 50 characters or fewer. Use short labels like "debug auth 403" or "check cache key".
8. Ask customer before deleting breakpoints at session end.
9. When proposing breakpoints, display code snippet with line numbers.
10. Void/None methods: to read a field assigned *inside* the method, use a **line-level breakpoint after the assignment** with `capture_locals` — never `capture_return` (it does not capture mutated arguments for void methods).
## Required Inputs Before Debugging

Collect these first:
- Problem description.
- Service name.
- Environment.
- Source path(s).
- Suspected entry point (if known).
- For latency issues: explicit threshold and expected baseline.

If any required input is missing, ask for it before proceeding.


---

# Tool Reference

## Tool Surface

### Instrumentation CRUD
- `create_instrumentation`: create breakpoint/probe. Returns `LocationHash` and `CreatedAt`. Requires explicit `capture_arguments`.
- `get_instrumentation`: fetch static config. Supports lookup by `location_hash` or by code location.
- `list_instrumentations`: list active instrumentations.
- `delete_instrumentation`: remove single instrumentation.
- `batch_delete_instrumentations_by_scope`: delete all instrumentations for a service/environment/type.

### Status
- `check_instrumentation_status`: **preferred** consolidated status check with required `start_time` and `end_time`.
- `get_instrumentation_configuration_status`: individual status query (for DISABLED or custom time ranges).

### Snapshot Query
- `get_sample_snapshot_for_breakpoint`: **use before searching** — fetches one raw snapshot to discover data structure. Includes `field_documentation` explaining each field's meaning so you can construct targeted filters.
- `search_snapshots_for_status_event`: query snapshots near a status event time. Use `custom_filters` for targeted analysis (Mode A); omit for discovery analysis (Mode B — see Phase 3).

### Source Inspection
- Read the target source file directly to verify argument names or code structure before creating a breakpoint. The applicationsignals MCP does not infer argument names, so `capture_arguments` must be chosen explicitly from the source.

## Status API Rules

**Preferred**: Use `check_instrumentation_status` for a single consolidated status call.

**Fallback**: Use `get_instrumentation_configuration_status` with explicit `status` for DISABLED checks, custom time ranges, or pagination.

**After breakpoint creation:**
1. Wait at least 2 minutes before the first status check.
2. Perform ONE status check.
3. If PENDING/READY: ask user before rechecking. Maximum 3 automatic rechecks.

**Status actions:**
- ACTIVE -> proceed to snapshot query
- READY -> ask user to generate traffic
- ERROR -> investigate error cause
- PENDING -> ask user if they want to wait and recheck
- DISABLED -> breakpoint exhausted `max_hits`. Delete and recreate with the same or higher `max_hits` if more data is needed.

**DISABLED detection:** `check_instrumentation_status` does not check DISABLED status. If a breakpoint was previously ACTIVE but has no recent events, use `get_instrumentation_configuration_status` with `status=DISABLED` to check whether it was disabled due to `max_hits` exhaustion. If the most recent ACTIVE event is significantly older than expected given ongoing traffic, the breakpoint is likely DISABLED — check explicitly before assuming it is still capturing.

**Time window selection:** If no events are found in the initial time window, try a larger window (e.g., from breakpoint creation time to now) before concluding the breakpoint has no activity.

## Snapshot Query Rules

**Use filters for targeted search.** For discovery analysis (Phase 3, Mode B), broad fetches without custom_filters are acceptable — but always save results to a file and aggregate locally rather than reading raw data into context.

1. Call `get_sample_snapshot_for_breakpoint` first — inspect the raw snapshot JSON and the `field_documentation` to understand the data structure and available fields.
2. Choose your analysis mode:
   - **Targeted**: Construct `custom_filters` relevant to your hypothesis. Use as many filters as possible to narrow scope. Use default limit (10).
   - **Discovery**: Omit `custom_filters`, use `limit=20` (increase gradually to 50/100 if patterns are not found), save results to a file, and aggregate with jq/python to find anomaly patterns. Then switch to targeted mode to drill in.
3. If insufficient results: ask user before extending time range or relaxing filters.

### Understanding Search Results

The `snapshot_summaries` in search results are a compact overview (timestamp, snapshot_id, traceId, location_hash). Full capture data is in `results[*].@message` — parse as JSON and navigate the `captures` object. For large result sets, use python or jq to extract specific fields from `@message`.

### Search Window Timing

The search window for `search_snapshots_for_status_event` is asymmetric: `status_timestamp - 5 seconds` to `status_timestamp + 1 minute` (~65 seconds total, biased forward). The window for `get_sample_snapshot_for_breakpoint` is wider: `status_timestamp - 30 seconds` to `status_timestamp + 90 seconds` (~2 minutes).

Use timestamps from `check_instrumentation_status` ACTIVE events. **Start with the oldest event timestamp** — older events have had more time for CloudWatch Logs ingestion. If no results are found, try the next-oldest timestamp before expanding the search.

### Filter Patterns by Problem Type

Snapshot logs are JSON. Use JSON field access for top-level/shallow fields (faster, exact match). Use `@message like` only for deep nested captures where field auto-discovery may not reach.

| Problem | Filter Pattern |
|---------|---------------|
| Specific method | `instrumentation.location.methodName = "<method_name>"` |
| Specific trace | `trace.traceId = "<trace_id>"` |
| Duration threshold | `duration > <ms>` |
| Specific argument | `@message like /"arguments"/ and @message like /"<param_name>"/` |
| Argument with value | `@message like /"<param_name>"/ and @message like /(?i)"<value>"/` |
| Return value | `@message like /"returnValue"/ and @message like /(?i)"<value>"/` |
| Local variable | `@message like /"locals"/ and @message like /"<var_name>"/` |
| Line-level event | `@message like /"lines"/ and @message like /"<line_number>"/` |
| Exclude noise | `@message not like /(?i)<noise_regex>/` |

## Snapshot Field Reference

### Function-level captures
- `captures.entry.arguments.<name>` — input arguments at entry
- `captures.return.returnValue` — function return value
- `captures.return.arguments.<name>` — argument values at return (shows mutations)
- `captures.return.throwable` — exception info (`type`, `message`, stacktrace)
- `captures.entry.locals.<name>` / `captures.return.locals.<name>` — local variables

### Line-level captures
- `captures.lines.<line>.locals.<name>` — local variables at specific instrumented line

### Metadata
- `instrumentation.location.*` — breakpoint location metadata
- `trace.traceId` — request correlation ID
- `duration` — execution duration in milliseconds (method-level only; absent for line-level)
- `stack[*]` — call stack frames (`fileName`, `function`, `lineNumber`)
- `locationHash` — breakpoint identifier
- `thread.id` / `thread.name` — **records the DI agent's snapshot collector thread, NOT the actual application thread that executed the instrumented code.** Do not rely on this field to identify which application thread hit the breakpoint.

### Entry vs Return Distinction
- `captures.entry`: values at function entry (arguments and locals at that point)
- `captures.return`: values at function exit (arguments may have mutated, return value and throwable available)
- Compare entry vs return arguments to detect mutation during execution


---

# Breakpoint Creation Reference

## Breakpoint Location Fields

- `file_path`: source file path in the running application.
- `code_unit`: Python module or Java package.
- `class_name`: class name when targeting a class method.
- `method_name`: function/method name.
- `line_number`: required for line-level breakpoints; omit for function/method-level.

### Python mapping rules
- `code_unit` = module path (e.g., `services.billing`). Use `"__main__"` only for script entrypoint.
- For direct import aliasing (`from mod import func`): target the importing module and use alias as `method_name`.

### Java mapping rules
- `code_unit` = package name (e.g., `com.amazon.sampleapp`).
- `class_name` = simple class name only (NOT fully qualified).

### Pre-flight checklist
Before creating a breakpoint, verify:
1. `file_path` matches deployed runtime source path.
2. `code_unit` matches module/package exactly.
3. `class_name` is simple name for Java (not FQCN).
4. `method_name` matches executed symbol name.
5. `line_number` is executable code if line-level.
6. `ttl_hours=24` is set.
7. `capture_arguments` lists correct parameter names.

If uncertain, read the source file directly to inspect it first.

### max_hits Exhaustion

Breakpoints stop capturing after `max_hits` is reached, and their status transitions to **DISABLED**. Use `max_hits=100` as the default. Check for DISABLED status to know whether a breakpoint has exhausted its quota. If a breakpoint is DISABLED due to max_hits exhaustion and you need more snapshots, delete it and recreate it with the same parameters (or a higher `max_hits`). When doing multi-phase debugging, check whether earlier breakpoints are still ACTIVE before relying on them for new data.

### Code Snippet Display (when proposing breakpoints)

When proposing breakpoints, **read the local source file** and display a code snippet so users can verify the location.

**Method-level:**
```
File: /app/product_service.py
Class: CacheKeyNormalizer  (omit if no class)
Method: def normalize_for_lookup(self, product_id)
Capture arguments: ["product_id"]
```

**Line-level (target line + 2 lines context):**
```
File: /app/product_service.py
   40|     key = product_id
   41|     if settings["strip_whitespace"]:
>> 42|         key = key.strip()
   43|     if settings["lowercase"]:
   44|         key = key.lower()
Capture locals: ["key"]
```


---

# Interaction Patterns

## Quick Interaction Template

Before breakpoint creation:
- observation
- hypothesis (tied to an observable value)
- proposed action
- exact parameters (including `capture_arguments`)
- expected correlation to confirm/disprove
- request user confirmation

Before analysis (discovery or targeted):
- what data you have (e.g., "50 snapshots from FraudService.authorize saved to file")
- what you don't know yet (e.g., "which orderId is problematic")
- what aggregation/filter you'll run and why (e.g., "group by orderId, find those with multiple distinct paymentRefs")
- what the result would mean (e.g., "multiple paymentRefs for one orderId = duplicate charge")

After data:
- evidence summary (which correlation category)
- correlation verdict (confirmed / disproven / inconclusive)
- next direction (upstream / downstream / line-level / multi-snapshot)
- request user confirmation for next step

## Auto-Instrumented Entry Point Rule

Do not place breakpoints on framework route handlers/controllers that are already auto-instrumented. Use the auto-instrumented route trace for top-level timing/status. Place breakpoints on internal business functions.

## Anti-Patterns (Do Not Do)

- Declaring root cause from code inspection only.
- Setting breakpoints without a clear hypothesis about what correlation to look for.
- Running unfiltered snapshot queries without a discovery analysis purpose (see Phase 3, Mode B).
- Querying snapshots and not performing correlation analysis on the results.
- Choosing a direction (upstream/downstream/etc.) without explaining which correlation finding led to that choice.
- Reading large result sets (20+ snapshots) directly into context instead of saving to a file and using jq/python.
- Running analysis commands (jq, python) without narrating what you're looking for and why (Principle 4).
- Aggressive status rechecking (max 3 automatic, then ask user).
- Omitting `capture_arguments` (required by the MCP).
- Silently expanding queries without asking user.
- Proposing breakpoints without code snippet display.

## Report Contract

Report purpose: session continuity.

Must include:
- active breakpoints with location hashes and clear location context
- key evidence (concise, not full dumps)
- correlation verdicts for each step
- current hypothesis and next direction
- final correlation chain: `[value] -> [effect] -> [failure]`

Use `templates/debugging-report-template.md` as canonical report structure.

## Reference Map (Progressive Disclosure)

Read only what is needed:

- `reference/mcp-tools-reference.md` — tool parameters and status state reminders
- `reference/snapshot-data-examples.md` — field interpretation or schema confusion
- `reference/snapshot-query-playbook.md` — custom filter patterns when default search is weak
- `reference/user-confirmation-examples.md` — concrete wording for proposals/conclusions
- `reference/call-tree-and-directions.md` — visual call-tree patterns and direction examples
- `reference/reporting-guidelines.md` — report conciseness guidance
- `reference/language-and-troubleshooting.md` — Python/Java details, import aliasing, troubleshooting

## Start Prompt Example

"Read `SKILL.md` and use this debugging workflow.
Service: <service>
Environment: <environment>
Problem: <problem>
Source: <paths>
Latency threshold (if relevant): <threshold>"
