# Language Notes, Troubleshooting, and Advanced Examples

Language-specific guidance, troubleshooting playbooks, and a full worked session.

## Language-Specific Notes

### Python
- `code_unit` = module name (e.g., `__main__`, `myapp.utils`)
- `method_name` = function name
- `class_name` = class name if method is in a class
- Line numbers start at 1

Example:
```
create_instrumentation(
    language="Python",
    file_path="/app/services/billing.py",
    code_unit="services.billing",
    method_name="generate_invoice",
    capture_arguments=["invoice_id", "customer_id", "amount"],
    ttl_hours=24,  # Always use 24 hours for debugging
    ...
)
```

### Python: Direct Import Handling (Important)

If a target function is imported by value (e.g., `from mod import func`), the SDK only wraps the function
inside the defining module and does not update imported aliases. This can cause breakpoints to never fire.

**Rule**:
- If the call site uses a direct import, set the breakpoint location to the importing module.
- Use the alias name as `method_name`.
- Use the importing file as `file_path`.

**Example**:
```
from user_service import fetch_user_profile
...
fetch_user_profile(...)
```

Breakpoint should target:
- `code_unit="__main__"` (if the app is run as a script)
- `method_name="fetch_user_profile"`
- `file_path="/path/to/app.py"`

If aliasing is used (`from mod import func as f`), set `method_name="f"`.

### Python: Discovering Argument Names

The MCP requires explicit `capture_arguments`. To discover argument names:

1. **Read the source file** directly with your local file-reading tools. This
   returns the function source so you can identify parameter names.
2. **Match the signature** to the target function/method and choose
   `capture_arguments` explicitly from the parameter list.

### Java

**IMPORTANT: Use simple class name, NOT fully qualified name!**

- `code_unit` = package name (e.g., `com.example.service`)
- `class_name` = **simple class name only** (e.g., `OrderService`, NOT `com.example.service.OrderService`)
- `method_name` = method name
- Note: Java may have overloaded methods (same name, different params)

**Common Mistake:**
```
WRONG: class_name="com.example.service.OrderService"  # Fully qualified - will fail!
RIGHT: class_name="OrderService"                      # Simple name only
```

**Correct Example:**
```
create_instrumentation(
    language="Java",
    file_path="/src/main/java/com/example/service/OrderService.java",
    code_unit="com.example.service",  # Full package path here
    class_name="OrderService",         # Simple class name only!
    method_name="processOrder",
    capture_arguments=["orderId", "customerId"],
    ttl_hours=24,  # Always use 24 hours for debugging
    ...
)
```

**Real Example from OrderContext.java:**
```
# Given: package com.amazon.sampleapp; public class OrderContext { ... }

create_instrumentation(
    language="Java",
    file_path="/path/to/OrderContext.java",
    code_unit="com.amazon.sampleapp",  # Package name
    class_name="OrderContext",          # Simple class name, not com.amazon.sampleapp.OrderContext
    method_name="getCustomer",
    capture_arguments=["customerId"],
    ttl_hours=24,
    ...
)
```

### Java: Argument Names in Snapshots

Java bytecode does not always preserve parameter names. In snapshots, arguments appear as
positional names (`arg0`, `arg1`, `arg2`, ...) regardless of what you specify in `capture_arguments`.
Map them by position to the method signature:

```
# Method signature:
#   calculateTotal(String productId, int quantity, String couponCode, String state)
#
# Snapshot arguments:
#   arg0 = productId
#   arg1 = quantity
#   arg2 = couponCode
#   arg3 = state
```

When building snapshot search filters, use the positional names:
```
@message like /"arg0"/ and @message like /"laptop"/     # filter by productId
@message like /"arg1"/ and @message like /"10"/          # filter by quantity
```

## Error Handling

### Breakpoint in ERROR State
1. Record the error in the report
2. Check the `ErrorCause` field
3. Notify customer with specific issue:
   - FILE_NOT_FOUND: "The file path may not match the running application"
   - METHOD_NOT_FOUND: "The function name may be incorrect or not loaded"
   - LINE_NOT_EXECUTABLE: "This line may be a comment, blank, or declaration"
4. Ask customer for guidance

### Breakpoint Stays in READY State (5 min timeout)
1. Record in report that no traffic hit the breakpoint
2. Notify customer: "The breakpoint at [location] was successfully applied but received no traffic in 5 minutes."
3. Ask customer:
   - Is this code path being executed?
   - Should we wait longer?
   - Should we try a different location?
4. If traffic is known to hit the function but it stays READY, check for direct import aliasing.
   - If the call site uses `from module import func`, instrument the importing module instead.

### Breakpoint in DISABLED State
1. This means MaxHits was exceeded
2. Query `get_instrumentation_configuration_status` with earlier time range to find ACTIVE timestamps
3. Use those timestamps to query snapshots
4. Record in report that breakpoint auto-disabled due to hit limit

### No Snapshot Data Found
1. **First, check your timestamp**: Are you using the latest timestamp? Try the 2nd or 3rd latest instead
2. CloudWatch Logs has ingestion delay (typically 1-3 minutes)
3. If using an older timestamp and still no data, wait another 2-3 minutes and retry
4. If still no data after waiting, notify customer

## Best Practices

### User Confirmation (Critical!)
- **ALWAYS ask for confirmation** before creating, modifying, or deleting breakpoints
- **ALWAYS show the full breakpoint parameters** (including `capture_arguments`) so the user can review and modify
- **NEVER proceed autonomously** through multiple debugging steps
- **NEVER state conclusions** without presenting the supporting snapshot data evidence first

### Evidence-Based Debugging
- **Hypotheses are NOT conclusions** — always phrase them as "I suspect..." or "This might be..."
- **Conclusions require evidence** — only state root causes after showing snapshot data proof
- **Show your data** — present tables, timestamps, and specific values to support findings
- **Acknowledge uncertainty** — if data is inconclusive, say so and propose next steps

### Breakpoint TTL
- **ALWAYS set `ttl_hours=24`** when creating breakpoints
- Debugging sessions often span multiple hours or even days
- Short-lived breakpoints (1 hour) will expire before investigation completes
- 24 hours provides sufficient time for iterative debugging without needing to recreate breakpoints

### Capture Arguments
- **ALWAYS specify `capture_arguments` explicitly** — the MCP does not infer argument names
- Read the source file directly to discover parameter names
- `capture_arguments=["*"]` is not supported; wildcards are stripped
- For line-level breakpoints, also specify `capture_locals` for the variables you want to inspect

### Void / None-Return Methods That Mutate Arguments

**HARD RULE: If the target method returns `void` (Java) or `None` (Python), you MUST
place a line-level breakpoint on the line immediately after the assignment. Do NOT use
a method-level breakpoint to observe a mutated field.**

**Do not rely on `capture_return` for void methods.** This is a common false assumption:
"Java passes objects by reference, so `capture_return=true` will show the mutated field
at method exit." **This is wrong.** For void/None methods the SDK omits the `return`
key from the snapshot entirely — there is no `captures.return`. The `capture_arguments`
snapshot reflects **entry state only**, so a field assigned inside the method still
shows its pre-call value (`0`, `null`, or default). Setting `capture_return=true` on a
void method does not re-capture argument fields at exit.

What a method-level breakpoint on a void method actually gives you:
- No `captures.return` key at all
- The mutated field stuck at its pre-call value in `captures.arguments`

The ONLY way to observe the post-mutation value is a **line-level breakpoint on the
line immediately after the assignment**, capturing the mutated object as a local:

```java
// Java example
void applyCouponDiscount(PricingContext ctx) {
    ctx.couponSavings = round(ctx.subtotal * couponRate);  // line 57
    ctx.orderAmount = ctx.orderAmount - ctx.couponSavings; // line 58  ← breakpoint here
}
// At line 58, ctx.couponSavings is already set — it appears in captures.lines.58.locals.ctx
```

**Proof (real snapshot from a method-level breakpoint on a `void` Java method with
`capture_return=true`).** Note: there is NO `return` key, and `couponSavings` is `0.0`
even though the method sets it — because the snapshot is entry-state only:

```json
{
  "captures": {
    "entry": {
      "arguments": {
        "ctx": {
          "type": "com.amazon.sampleapp.PricingService$PricingContext",
          "fields": {
            "subtotal":      { "type": "java.lang.Double", "value": "299.99" },
            "orderAmount":   { "type": "java.lang.Double", "value": "299.99" },
            "couponSavings": { "type": "java.lang.Double", "value": "0.0" }
        }
      }
    }
  }
}
```
There is no `captures.return`. `capture_return=true` was set and still produced nothing
at exit. This is why you must use a line-level breakpoint.

**When to apply this pattern:**
- Method signature is `void` / returns `None` (this alone is enough — apply the rule)
- The value you need is assigned inside the method, not passed in as an argument
- Method-level breakpoint snapshot shows the field as `0`, `null`, or its default value,
  and has no `captures.return` key

### Efficiency
- For latency issues, consider setting multiple breakpoints at suspected functions simultaneously
- Compare durations across snapshots to quickly identify the slow component
- Use `max_hits` wisely - too low may miss intermittent issues, too high may flood logs

### Parallel Breakpoints Strategy

Setting multiple breakpoints simultaneously is often more efficient than sequential debugging. This applies to **two key scenarios**:

#### Scenario 1: Latency Investigations (compare timing)

When debugging latency, set breakpoints on all suspected functions at once to compare durations:

**When to use:**
- The call chain has multiple branches and you don't know which is slow
- You want to quickly narrow down which component is the bottleneck

**Example**: For a user registration latency issue:
```
Set breakpoints on ALL suspected functions at once:
1. check_username_available()  -> LocationHash: abc123
2. hash_password()             -> LocationHash: def456
3. create_user_record()        -> LocationHash: ghi789
4. send_welcome_email()        -> LocationHash: jkl012

Then compare durations across snapshots to find the slow one.
```

#### Scenario 2: Cache / State / Data Flow Issues (compare values)

When investigating cache mismatches, data transformation bugs, or state inconsistencies, set ALL suspected breakpoints BEFORE waiting for traffic. These issues often involve comparing values across multiple functions for the same request.

**When to use:**
- Investigating key/hash mismatch patterns (need to see both computation and verification)
- Debugging data transformation pipelines (need to see input/output at each stage)
- Tracing state across multiple functions (need values from the same request)

**Why parallel is critical for these issues:**
- Traffic with the problematic pattern may be **intermittent** — if you set breakpoints one at a time, you may capture the first function but miss the second because the next problematic request hasn't arrived yet
- You need data from **the same request** across multiple functions to compare values
- Setting breakpoints sequentially wastes time waiting for traffic at each step

#### Parallel vs Sequential Decision Tree

```
Is the issue about TIMING (latency)?
  -> YES: Set parallel breakpoints on all suspected functions, compare durations

Is the issue about VALUES (wrong data, cache miss, transformation bug)?
  -> YES: Set parallel breakpoints on all functions in the data flow, compare values

Is the issue about LOGIC (wrong branch, incorrect condition)?
  -> YES: Use sequential breakpoints, trace step-by-step

Do you already have a specific hypothesis about ONE function?
  -> YES: Start with sequential on that function, expand if needed
```

**When to use sequential breakpoints:**
- You already have a strong hypothesis about a single function
- You need to see the output of one function before deciding where to look next
- The issue is a logic error requiring step-by-step tracing through conditionals

### Transparency & Reasoning
- **Explain your reasoning** at every step before taking action
- **Distinguish hypothesis from conclusion**: "I suspect X" vs "The data shows X"
- Always record your hypothesis before setting a breakpoint
- Explain your reasoning in the report
- Include key snapshot data for verification
- **Present options** when there are multiple valid next steps

### Clean Up
- Track all breakpoints created in the report
- Always offer to clean up at the end
- Use `batch_delete_instrumentations_by_scope` for bulk cleanup
- Don't leave orphaned breakpoints

### Asking for Help
- If stuck after 3-4 iterations, ask the customer for guidance
- If the problem seems to require domain knowledge, ask
- If snapshot data is ambiguous, present findings and ask for interpretation

## Example Session (Correlation-Focused)

Customer: "Our monthly financial report sometimes shows negative revenue for departments that definitely have positive sales"

**Step 1**: Read source code, find the report generation entry point:
```python
@app.route('/reports/monthly', methods=['POST'])
def generate_monthly_report():
    departments = fetch_departments(org_id)
    report = build_department_summary(departments, start_date, end_date)
    return format_report(report)
```

**Note**: `generate_monthly_report()` is a Flask route handler -> **auto-instrumented, skip it**

**Hypothesis 1**: The issue is in `build_department_summary()` since that's where revenue calculations happen. Since the problem is intermittent ("sometimes"), this suggests an **input-problem correlation** — certain department data may trigger incorrect calculations.

**Action**: Set breakpoint at `build_department_summary()` to see inputs and outputs.
```python
create_instrumentation(
    ...,
    method_name="build_department_summary",
    capture_arguments=["departments", "start_date", "end_date"],
    ...
)
```

**Results & Correlation Analysis**:
- Input `departments`: List of 12 department objects
- Return: Report with one department showing `-$45,230` revenue

**Correlation Finding**: The return value shows the problem (negative revenue). Need to look **inside** the function to find where it goes wrong.

**Hypothesis 2**: Looking at the code:
```python
def build_department_summary(departments, start_date, end_date):
    summaries = []
    for dept in departments:
        revenue = calculate_dept_revenue(dept.id, start_date, end_date)
        summaries.append({"dept": dept.name, "revenue": revenue})
    return summaries
```

The revenue comes from `calculate_dept_revenue()`. **Suspected correlation**: Certain `dept.id` values produce negative results.

**Action**: Set breakpoint at `calculate_dept_revenue()` with `max_hits=20` to compare across departments.
```python
create_instrumentation(
    ...,
    method_name="calculate_dept_revenue",
    capture_arguments=["dept_id", "start_date", "end_date"],
    max_hits=20,
    ...
)
```

**Results (Cross-Snapshot Comparison)**:
| dept_id | revenue | duration |
|---------|---------|----------|
| D001 | $125,000 | 45ms |
| D002 | $89,000 | 42ms |
| D003 | -$45,230 | 48ms |
| D004 | $210,000 | 44ms |

**Correlation Analysis**: Only `D003` returns negative. What's special about it?

Looking at the snapshots more closely:
- D001, D002, D004: `start_date="2024-01-01"`, `end_date="2024-01-31"`
- D003: `start_date="2024-01-01"`, `end_date="2024-01-31"` (same dates)

Dates are the same — not the differentiator. Need to look inside `calculate_dept_revenue()`.

**Hypothesis 3**: Looking at the calculation code:
```python
def calculate_dept_revenue(dept_id, start_date, end_date):
    transactions = fetch_transactions(dept_id, start_date, end_date)
    total = 0
    for txn in transactions:
        if txn.type == "SALE":
            total += txn.amount
        elif txn.type == "REFUND":
            total -= txn.amount
        elif txn.type == "ADJUSTMENT":
            total += txn.adjustment_value  # Could be negative!
    return total
```

**Suspected correlation**: ADJUSTMENT transactions with large negative `adjustment_value` might be causing the issue.

**Action**: Set line-level breakpoint at line with `txn.adjustment_value`, capturing `txn` and `total` local variables.

**Results (Line-Level)**:
```python
# Snapshot: captures.lines.14.locals
# txn.type="ADJUSTMENT", txn.adjustment_value=-180000, total=134770
# After line: total = 134770 + (-180000) = -45230
```

**Local Variable Correlation Found**:
- `txn.adjustment_value = -180000` is a massive negative adjustment
- This single transaction flips the total from positive to negative
- The `adjustment_value` is already negative, but code does `total += adjustment_value`

**Root Cause Confirmed**: The ADJUSTMENT handling has a sign error. The `adjustment_value` field is stored as a signed value (negative for reductions), but the code adds it unconditionally. For D003, a large inventory write-off adjustment (`-$180,000`) was recorded with the correct negative sign in the database, but the code should have used `abs()` or the field should store unsigned values with a separate direction flag.

**Correlation Chain**:
```
dept_id = "D003" (INPUT)
  -> has ADJUSTMENT transaction
  -> txn.adjustment_value = -180000 (LOCAL: already negative)
  -> code does total += (-180000) (double-negative logic error)
  -> final revenue = -$45,230 (RETURN: incorrect)
```

**Recommendation**: Either change the code to `total += abs(txn.adjustment_value)` if adjustments should always add, or add a `txn.direction` field and handle positive/negative adjustments explicitly. Review the data model with the finance team to clarify intended semantics.
