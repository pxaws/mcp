# Reporting Guidelines

Guidance for concise debugging reports. Use `templates/debugging-report-template.md` for the canonical report structure.

## Report Conciseness Guidelines (Important!)

The debugging report serves one primary purpose: **enabling session continuity**. If a debugging session is interrupted, another person (or the same person later) should be able to read the report and continue debugging without repeating work.

**Document ONLY what's essential for session continuity:**
- Active breakpoints and their LocationHashes
- Key observations and confirmed correlations (brief)
- Current hypothesis and next planned step
- Critical evidence (specific values that proved or disproved a hypothesis)

**Do NOT include:**
- Verbose reasoning or step-by-step thought process
- Full snapshot JSON dumps (summarize the relevant fields instead)
- Multiple examples of the same pattern (one representative example is enough)
- Descriptions of what was tried and didn't work (unless it prevents repeating the same dead end)
- Redundant context the reader can get from source code

**Rule of thumb**: Each timeline step should be 3-8 lines, not 20+. If a step needs more, the observation is either too verbose or should be split into sub-steps.

## Active Breakpoints Table

Always include File, Module, and Function to provide full context.

**Good format**:

| LocationHash | Location | Status |
|--------------|----------|--------|
| abc123def456 | `user_service.py:user_service.fetch_user` | ACTIVE |

**Bad format** (missing context):

| LocationHash | Function |
|--------------|----------|
| abc123def456 | fetch_user |

## Correlation Analysis Sections

For each debugging step, analyze captured data by category:
- Input arguments (`captures.entry.arguments`): suspicious values?
- Return value (`captures.return.returnValue`): expected or unexpected?
- Local variables (`captures.lines` or `captures.return.locals`): wrong control flow?
- Duration: correlates with input characteristics?
- Throwable (`captures.return.throwable`): any exceptions?

Always state a correlation verdict: confirmed, disproven, or inconclusive.

## Final Summary Requirements

The final summary must include:
- **Root Cause**: description backed by evidence
- **Key Correlation**: specific value-problem link with snapshot proof
- **Correlation Chain**: `[value1] -> [effect1] -> [value2] -> [problem]`
- **Recommendations**: suggested fixes

## When to Create/Update

- Create at session start (after Phase 1)
- Update after each debugging step
- Finalize when root cause is confirmed or session ends
