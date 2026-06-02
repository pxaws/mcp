# Debugging Report: [PROBLEM_TITLE]
Generated: [TIMESTAMP]
Last Updated: [TIMESTAMP]

## Session Context
- **Service**: [SERVICE_NAME]
- **Environment**: [ENVIRONMENT]
- **Problem Description**: [CUSTOMER_DESCRIPTION]
- **Source Files**:
  - [FILE_PATH_1]
  - [FILE_PATH_2]

## Status: IN_PROGRESS

---

## Debugging Timeline

### [TIMESTAMP] Step 1: Initial Analysis

**Source Analysis**:
[Describe what was observed when reading the source code]

**Import Style Check (Python only)**:
- Direct import aliasing checked: [YES/NO]
- If YES: breakpoint targets importing module: [YES/NO]

**Current Hypothesis** (with suspected correlation):
[State the initial hypothesis about what might be causing the issue]
- Suspected correlation type: [INPUT/RETURN/LOCAL_VARIABLE/CROSS-SNAPSHOT]
- Specific value/pattern suspected: [describe]
- How it might cause the problem: [explain]

**Action**:
Setting initial breakpoint
- Location: [FILE:FUNCTION_NAME]
- LocationHash: [PENDING]
- Type: BREAKPOINT
- Language: [Python/Java]
- Capture arguments: [LIST OF ARGUMENT NAMES]
- Reasoning: [why this function, what correlation we expect to find]

**Waiting for breakpoint status...**

---

### [TIMESTAMP] Step 2: [TITLE]

**Breakpoint Status**: [READY/ACTIVE/ERROR/DISABLED]

**Snapshot Data Retrieved**:
```json
{
  "duration_ms": [DURATION],
  "captures": {
    "entry": {
      "arguments": [ARGS]
    },
    "return": {
      "returnValue": [RETURN],
      "throwable": [THROWABLE_OR_NULL]
    },
    "lines": [LINE_LOCALS]
  },
  "stack_preview": [STACK]
}
```

**Correlation Analysis**:
[For each captured value category:]
- Input arguments (captures.entry.arguments): [observations, any suspicious values?]
- Return value (captures.return.returnValue): [observations, expected or unexpected?]
- Local variables (captures.lines or captures.return.locals): [observations]
- Duration: [observations, does it correlate with input characteristics?]
- Throwable (captures.return.throwable): [any exceptions?]

**Correlation Verdict**:
- [ ] Correlation confirmed: [describe which value correlates with problem]
- [ ] Correlation disproven: [the suspected value is not the cause]
- [ ] Inconclusive: [need more data, next step...]

**Updated Hypothesis**:
[Updated hypothesis based on correlation analysis]

**Next Step**:
- Direction chosen: [UPSTREAM/DOWNSTREAM/LINE-LEVEL/MULTI-SNAPSHOT]
- Reasoning: [which correlation finding led to this direction choice]

---

## Active Breakpoints

| LocationHash | Location | Language | Type | Status | Created |
|--------------|----------|----------|------|--------|---------|
| [HASH] | [LOCATION] | [LANG] | BREAKPOINT | [STATUS] | [TIME] |

---

## Observed Correlations Summary

[Accumulate confirmed correlations here as debugging progresses]

| Correlation Type | Value/Pattern | Effect on Problem | Confirmed? |
|-----------------|---------------|-------------------|------------|
| [INPUT/RETURN/LOCAL] | [value pattern] | [how it affects problem] | [Y/N/?] |

---

## Final Summary

### Root Cause
[To be filled when debugging completes]

### Key Correlation
[The specific value-problem correlation that explains the root cause]
- Value: [which input/return/local]
- Pattern: [when/how it causes the issue]
- Evidence: [snapshot data proof]

### Correlation Chain
[Show the chain of correlations from input to problem]
```
[value1] -> [effect1] -> [value2] -> [effect2] -> [problem]
```

### Authorization Bug Evidence (if applicable)
**Use this section for 403/401/access denied issues. ALL fields required for complete proof.**

| Evidence Item | Value | Source |
|--------------|-------|--------|
| **Failing Request TraceId** | [TRACE_ID] | [which snapshot/query] |
| **Resource ID** | [ID] | [e.g., documentId, recordId from request] |
| **Expected Identity** (who should have access) | [VALUE] | [e.g., resource.ownerId] |
| **Actual Identity** (who system thinks is asking) | [VALUE] | [e.g., currentUserId, sessionUser] |
| **Comparison Result** | [true/false] | [expected.equals(actual)] |
| **HTTP Response Code** | [200/403/401] | [auto-instrumented trace] |

**Complete Failure Case**:
```
TraceId: [TRACE_ID]
Request: [HTTP method + URL]
  - Resource owner: [EXPECTED_IDENTITY]
  - Identity used for auth: [ACTUAL_IDENTITY]
  - Match: [YES/NO]
  - Result: [HTTP status code + response]
```

**Evidence Quality Checklist**:
- [ ] Specific failing request identified (traceId/timestamp)
- [ ] Expected identity captured from data source
- [ ] Actual identity captured from auth context
- [ ] Mismatch between expected and actual proven
- [ ] HTTP 403/401 confirmed in same trace
- [ ] Causal chain fully documented

### Recommendations
[Suggested fixes or next steps for the customer]

---

## Appendix: Raw Snapshot Data

<details>
<summary>Click to expand raw snapshot data</summary>

```json
[Include full snapshot JSON here for verification]
```

</details>

---

## Cleanup Checklist
- [ ] Customer reviewed the report
- [ ] Asked customer about breakpoint cleanup
- [ ] Breakpoints deleted (if requested)
- [ ] Used batch_delete_instrumentations_by_scope for bulk cleanup (if applicable)
