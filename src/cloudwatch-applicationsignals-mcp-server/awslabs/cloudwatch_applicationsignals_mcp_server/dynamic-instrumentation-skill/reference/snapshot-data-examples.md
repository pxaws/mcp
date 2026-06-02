# Snapshot Data Examples

This document shows example snapshot data patterns to help with analysis.

## Snapshot Structure Overview

Dynamic instrumentation snapshots are stored in CloudWatch Logs (`/telemend/telemetry`).
Each snapshot captures a function invocation with entry/return phases and optional line-level data.

## Full Snapshot Example (Function-Level Breakpoint)

```json
{
  "id": "snap-abc123def456",
  "timestamp": 1707000000000,
  "duration": 174,
  "locationHash": "1418596592c9f6cb",
  "instrumentation": {
    "location": {
      "filePath": "/app/demo_app.py",
      "codeUnit": "__main__",
      "methodName": "process_payment",
      "className": "",
      "language": "Python"
    }
  },
  "trace": {
    "traceId": "abc123def456789",
    "spanId": "span123456"
  },
  "thread": {
    "id": 1,
    "name": "MainThread"
  },
  "stack": [
    {
      "fileName": "/app/api.py",
      "function": "checkout",
      "lineNumber": 42
    },
    {
      "fileName": "/app/services/order.py",
      "function": "process_order",
      "lineNumber": 100
    }
  ],
  "captures": {
    "entry": {
      "arguments": {
        "order_id": { "type": "str", "value": "123" },
        "total": { "type": "float", "value": "99.5" }
      },
      "locals": {}
    },
    "return": {
      "arguments": {
        "order_id": { "type": "str", "value": "123" },
        "total": { "type": "float", "value": "99.5" }
      },
      "locals": {
        "result": { "type": "dict", "value": "{\"status\": \"success\"}" }
      },
      "returnValue": {
        "type": "dict",
        "value": "{\"status\": \"success\", \"transaction_id\": \"txn-order-6474\"}"
      }
    },
    "lines": {}
  }
}
```

## Snapshot with Line-Level Captures

```json
{
  "id": "snap-line789",
  "timestamp": 1707000001000,
  "duration": null,
  "locationHash": "1418596592c9f6cb",
  "instrumentation": {
    "location": {
      "filePath": "/app/demo_app.py",
      "codeUnit": "__main__",
      "methodName": "process_payment",
      "language": "Python",
      "lineNumber": 70
    }
  },
  "captures": {
    "entry": {
      "arguments": {},
      "locals": {}
    },
    "return": {
      "arguments": {},
      "locals": {}
    },
    "lines": {
      "70": {
        "locals": {
          "total": { "type": "float", "value": "99.5" },
          "discount": { "type": "float", "value": "0.0" }
        }
      }
    }
  }
}
```

## Snapshot with Exception (Throwable)

```json
{
  "captures": {
    "return": {
      "throwable": {
        "type": "ValueError",
        "message": "Invalid order ID format",
        "stacktrace": [
          {
            "fileName": "/app/services/billing.py",
            "function": "validate_order",
            "lineNumber": 25
          }
        ]
      }
    }
  }
}
```

## Key Fields Explained

### Duration
```
duration: 174
```
- Unit: milliseconds (top-level field in snapshot JSON, per snapshot spec v1.0)
- Use directly — no conversion needed
- Use for: Identifying slow functions
- Note: Line-level snapshots may omit duration entirely

### Function Arguments (Entry)
```json
"captures.entry.arguments": {
  "order_id": { "type": "str", "value": "123" },
  "total": { "type": "float", "value": "99.5" }
}
```
- Format: Named map of CapturedValue objects
- Each value has `type` and `value` (string representation)
- May include `truncated: true` for large values
- May include `notCapturedReason` if capture failed
- May include `isNull: true` for null values
- Contains: Only parameters listed in `capture_arguments`

### Function Arguments (Return)
```json
"captures.return.arguments": {
  "order_id": { "type": "str", "value": "123" },
  "total": { "type": "float", "value": "99.5" }
}
```
- Same arguments captured at function exit
- Compare with entry arguments to detect mutation during execution

### Return Value
```json
"captures.return.returnValue": {
  "type": "dict",
  "value": "{\"status\": \"success\", \"transaction_id\": \"txn-order-6474\"}"
}
```
- Single CapturedValue (not indexed like old format)
- Use for: Verifying function output is correct
- Only present when `capture_return=True`

### Throwable (Exception)
```json
"captures.return.throwable": {
  "type": "ValueError",
  "message": "Invalid order ID format",
  "stacktrace": [...]
}
```
- Present only when the function throws an exception
- Includes exception type, message, and stack trace
- Use for: Understanding exception root cause

### Stack Trace
```json
"stack": [
  { "fileName": "/app/api.py", "function": "checkout", "lineNumber": 42 },
  { "fileName": "/app/services/order.py", "function": "process_order", "lineNumber": 100 }
]
```
- Array of frame objects with `fileName`, `function`, `lineNumber`
- Shows: Call chain leading to the breakpoint
- Use for: Understanding how the function was called, deciding upstream breakpoints
- Tool responses include `stack_preview` (first 5 frames) and `stack_frame_count`

### Local Variables (Line-Level Only)
```json
"captures.lines.70.locals": {
  "total": { "type": "float", "value": "99.5" },
  "discount": { "type": "float", "value": "0.0" }
}
```
- Keyed by line number string
- Each line has a `locals` map of CapturedValue objects
- Only available: For line-level breakpoints
- Use for: Tracing variable values at specific code points

### CapturedValue Format
Each captured value is a structured object:
```json
{ "type": "str", "value": "hello" }                    // simple value
{ "type": "NoneType", "isNull": true }                  // null
{ "type": "str", "value": "hel...", "truncated": true }  // truncated
{ "type": "str", "notCapturedReason": "depth" }          // not captured
{ "type": "list", "elements": [...], "size": 10 }       // collection
{ "type": "dict", "fields": {"key": ...}, "size": 5 }   // object/dict
{ "type": "dict", "entries": [...] }                     // map entries
```

### Java HashMap / Map Captures

When capturing a Java `HashMap` or `Map` local variable, entries are expanded as key-value pairs. This is useful for extracting runtime-computed values (e.g., thread names, trace IDs) that the application stores in a map but not in a simple local variable. Requires `max_object_depth` and `max_collection_width` to be set high enough.

```json
"errorResponse": {
  "type": "java.util.HashMap",
  "entries": [
    {
      "key": { "type": "java.lang.String", "value": "threadName", "size": 10 },
      "value": { "type": "java.lang.String", "value": "http-nio-127.0.0.1-8080-exec-3", "size": 30 }
    },
    {
      "key": { "type": "java.lang.String", "value": "orderId", "size": 7 },
      "value": { "type": "java.lang.String", "value": "ORD-ADA70E6F", "size": 12 }
    }
  ],
  "size": 5
}
```

## Analyzing Duration

### Normal Response (< 100ms)
```json
{
  "duration": 45,
  "instrumentation": { "location": { "methodName": "validate_input" } }
}
```

### Slow Response (> 1s)
```json
{
  "duration": 5234,
  "instrumentation": { "location": { "methodName": "process_payment" } }
}
```

### Calculating Percentage
If parent function takes 5000ms and child takes 4800ms:
- Child contributes: 4800/5000 = 96% of latency
- This is likely the root cause

## Analyzing Arguments

### Unexpected Input
```json
{
  "captures": {
    "entry": {
      "arguments": {
        "items": { "type": "list", "elements": [], "size": 0 },
        "discount": { "type": "float", "value": "1.5" }
      }
    }
  }
}
```
- Issue: Empty items list, discount > 100%
- Action: Go upstream to see where these values came from

### Large Input
```json
{
  "captures": {
    "entry": {
      "arguments": {
        "items": { "type": "list", "elements": [...], "size": 10000 }
      }
    }
  }
}
```
- Issue: Unexpectedly large input
- Action: Check if this is normal, may explain slow loop

## Analyzing Return Values

### Error in Return
```json
{
  "captures": {
    "return": {
      "returnValue": {
        "type": "dict",
        "value": "{\"error\": \"Database connection failed\"}"
      }
    }
  }
}
```
- Issue: Function returned an error
- Action: Investigate database connectivity

### Null Return
```json
{
  "captures": {
    "return": {
      "returnValue": { "type": "NoneType", "isNull": true }
    }
  }
}
```
- Issue: Function returned null unexpectedly
- Action: Check logic path, may need line-level breakpoint

## Analyzing Stack Traces

### Identifying Caller
```json
"stack": [
  { "fileName": "/app/api/checkout.py", "function": "checkout", "lineNumber": 42 },
  { "fileName": "/app/services/order.py", "function": "process_order", "lineNumber": 100 }
]
```
- Current function: the breakpoint target
- Called by: `checkout` at line 42
- Called by: `process_order` at line 100
- Upstream options: Set breakpoint at `checkout` or `process_order`

## Common Patterns

### Latency Issue Pattern
1. Entry function snapshot shows high duration
2. Set breakpoints at called functions
3. Find the one with matching high duration
4. Drill down until you find the slow operation

### Incorrect Value Pattern
1. Function returns wrong value (check `captures.return.returnValue`)
2. Check input arguments (check `captures.entry.arguments`) - are they correct?
3. If yes, set line-level breakpoints to trace logic
4. Find where the value goes wrong (check `captures.lines.<line>.locals`)

### Exception Pattern
1. Function throws exception (check `captures.return.throwable`)
2. Check exception type and message
3. Check input arguments that may have triggered the exception
4. Set line-level breakpoints before the throwing line to see state

### Intermittent Issue Pattern
1. Set breakpoint with higher `max_hits`
2. Query multiple snapshots
3. Compare: What's different between good and bad cases?
4. Look for: Different inputs, different code paths

## Duration Thresholds (Guidelines)

| Operation Type | Normal | Investigate |
|----------------|--------|-------------|
| Simple computation | < 10ms | > 50ms |
| Database query | < 100ms | > 500ms |
| External API call | < 1s | > 3s |
| File I/O | < 100ms | > 500ms |

Note: These are rough guidelines. Actual thresholds depend on your application.
