# User Confirmation Examples

Detailed conversational examples for proposing breakpoints and presenting evidence.

### Example 1: Before Creating a Breakpoint

**IMPORTANT**: Always include the relevant code snippet and explicit `capture_arguments` when proposing a breakpoint. This helps the customer:
- Verify you're targeting the correct function
- Catch naming errors (e.g., class methods vs module-level functions, underscore prefixes)
- Confirm the argument names to capture
- See the context of what the function does

```
AGENT: Based on my analysis of the source code, I see that `fetch_user_profile()`
       calls `query_user_database()` which connects to an external database.
       I suspect this might be causing the latency spikes.

       **My hypothesis**: Slow database queries in `query_user_database()` are
       causing the overall latency issue.

       **Proposed action**: I'd like to create a breakpoint on `fetch_user_profile`
       to capture the input `user_id` and the return value, so we can
       correlate slow requests with specific user patterns.

       **Target code** (user_service.py:42-55):
       ```python
       def fetch_user_profile(user_id, include_preferences=True):
           """Fetch user profile from database with optional preferences."""
           cache_key = _build_cache_key(user_id)

           if cache_key in _user_cache:
               return _user_cache[cache_key]

           # Cache miss - query database
           profile = query_user_database(user_id)
           if include_preferences:
               profile["preferences"] = load_user_preferences(user_id)
           _user_cache[cache_key] = profile
           return profile
       ```

       **Breakpoint details**:
       - File: /src/user_service.py
       - Function: fetch_user_profile
       - Capture arguments: ["user_id", "include_preferences"]
       - Capture return: True
       - Max hits: 100
       - TTL: 24 hours

       **What I expect to learn**: The duration will tell us if it was a
       cache hit (~0ms) or miss (potentially slow), and which user IDs are
       affected.

       Does this look correct? Should I proceed, or would you like to
       modify any parameters?

USER: Yes, proceed.

AGENT: [Now creates the breakpoint with capture_arguments=["user_id", "include_preferences"]]
```

**Why code snippets and explicit capture_arguments matter**:
- Prevents errors like targeting `build_cache_key` (without underscore) vs `_build_cache_key` (with underscore)
- Shows exact parameter names for `capture_arguments`
- The MCP requires explicit argument names — you must list them
- Helps customer verify the function is what they expect
- Provides context for understanding breakpoint results later

### Example 2: Before Drawing Conclusions

```
WRONG (jumping to conclusions):

AGENT: Looking at the code, I can see there's a session ID mismatch bug.
       The validation uses different encoding than storage. This is
       causing the authentication issues.

RIGHT (evidence-based):

AGENT: Looking at the code, I notice that `encode_session_id()` and
       `decode_session_id()` might use different encoding logic. This COULD
       cause session validation failures.

       However, I need to verify this with actual data. I'd like to create
       breakpoints on both functions to capture:
       - The input session data
       - The encoded/decoded result

       This will show us if there's actually a mismatch in practice.

       **Proposed breakpoints**:
       1. encode_session_id - capture_arguments: ["session_data"]
       2. decode_session_id - capture_arguments: ["encoded_id"]

       Should I proceed with these breakpoints?
```

### Example 2b: Inspecting Source When Unsure About Arguments

When you're not sure about the exact parameter names, read the source file first:

```
AGENT: I want to set a breakpoint on `process_order()` but I'm not sure
       about the exact parameter names. Let me check the source first.

       [Reads /app/orders.py and locates process_order]

       The source shows:
       ```python
       def process_order(order_id: str, items: list, discount_code: Optional[str] = None):
       ```

       **Proposed breakpoint**:
       - Function: process_order
       - Capture arguments: ["order_id", "items", "discount_code"]

       Should I proceed?
```

### Example 2c: Proposing Breakpoints on Internal Functions

When proposing breakpoints on internal/helper functions that are not obvious entry points,
**always include a simplified code snippet** showing how the function fits into the
workflow. This helps the customer understand:
- What the function does
- Why it's relevant to the investigation
- What you expect to learn

**Bad Example** (no context):
```
I'd like to set breakpoints on:
1. compute_request_hash() - to see the hash used for deduplication lookup
2. generate_storage_hash() - to see the hash used for storing results
```

**Good Example** (with workflow context):
```
AGENT: Based on the snapshot data, I suspect a hash mismatch in the deduplication logic.
       Here's the relevant code flow I found in the source:

       def process_request(request_data):
           # Step 1: Compute hash for DEDUP LOOKUP
           lookup_hash = compute_request_hash(request_data)  # <-- Breakpoint 1

           cached_result = dedup_store.get(lookup_hash)
           if cached_result:
               return cached_result  # Already processed

           # Process the request
           result = expensive_processing(request_data)

           # Step 2: Compute hash for STORAGE
           storage_hash = generate_storage_hash(request_data)  # <-- Breakpoint 2
           dedup_store.set(storage_hash, result)

           return result

       If `lookup_hash != storage_hash` for the same input, deduplication will fail.
       I want to verify this by capturing the actual hashes returned by each function.

       **Proposed breakpoints:**
       1. `compute_request_hash()` - capture_arguments: ["request_data"], capture_return: True
       2. `generate_storage_hash()` - capture_arguments: ["request_data"], capture_return: True

       **What I expect to find:** The two functions may return different hashes for
       the same input, confirming the deduplication failure hypothesis.
```

This approach:
- Shows the function in context of the larger workflow
- Explains the hypothesis clearly
- Makes it obvious why both breakpoints are needed
- States what evidence would confirm or disprove the hypothesis

### Example 3: After Analyzing Snapshot Data

```
AGENT: I've analyzed the snapshot data from `lookup_customer_profile`. Here's what I found:

       **Evidence**:
       | Timestamp    | Region Code | Duration | Result          |
       |--------------|-------------|----------|-----------------|
       | 21:40:09.912 | "us-west"   | 541 ms   | Database lookup |
       | 21:41:00.062 | "us-west"   | 2 ms     | Cached          |
       | 21:41:15.330 | "US-WEST"   | 498 ms   | Database lookup |

       **Observation**: "US-WEST" (uppercase) triggered a database lookup despite
       "us-west" (lowercase) being cached 75 seconds earlier. This suggests
       the region code handling is case-sensitive somewhere.

       **Interpretation**: The caching layer may not normalize region codes consistently,
       causing case variations to bypass the cache.

       **Next step options**:
       1. Create breakpoints on the region code handling functions to see actual values
       2. Increase max_hits and look for more case-variation patterns
       3. Consider this investigation complete

       What would you like me to do?
```
