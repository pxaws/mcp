# AWS Dynamic Instrumentation Snapshot Specification

## Overview

This specification defines the JSON schema for snapshots produced by AWS Dynamic Instrumentation agents across all supported languages. A snapshot represents the complete captured state of a function execution at the point of instrumentation.

Snapshots are emitted as **OTLP log records**. The record envelope carries OTel-standard fields (`timeUnixNano`, `traceId`, `spanId`, `attributes`, `resource`); DI-specific metadata lives in `attributes` under the `aws.di.*` namespace; and the rich captured state (stack, captures) lives in `body`.

* * *

## Top-Level Schema

```json
{
  "timeUnixNano": number,
  "traceId": "string",
  "spanId": "string",
  "attributes": { ... },
  "resource": { "attributes": { ... } },
  "body": {
    "stack": [ ... ],
    "captures": { ... }
  }
}
```

### Field Definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `timeUnixNano` | number | **Required** | Snapshot capture time in **nanoseconds** since the Unix epoch. |
| `traceId` | string | Optional | OpenTelemetry trace ID (hex, 32 chars). Absent if no active trace context. |
| `spanId` | string | Optional | OpenTelemetry span ID (hex, 16 chars). Absent if no active trace context. |
| `attributes` | object | **Required** | DI metadata keyed under the `aws.di.*` namespace. See [Attributes](#attributes). |
| `resource` | object | **Required** | OTel resource. `resource.attributes` carries `service.name`, `deployment.environment.name`, etc. |
| `body` | object | Optional | Captured execution state. See [Body](#body). Emitted only when the agent produced at least one of stack / captures; absent otherwise. |

* * *

## Attributes

DI-specific metadata is flattened into the OTLP `attributes` map under the `aws.di.*` namespace.

| Key | Type | Required | Description |
|---|---|---|---|
| `event.name` | string | **Required** | Constant value `"aws.dynamic_instrumentation.snapshot"`. Identifies the OTLP event type for routing/filtering. |
| `aws.di.snapshot_id` | string | **Required** | Unique identifier for this snapshot (UUID v4). |
| `aws.di.location_hash` | string | **Required** | Hash identifying the instrumentation location (e.g., `"b1cca82f82fcd637"`). Used for deduplication and correlation with the instrumentation config. Emitted as an empty string if the agent has no hash. |
| `aws.di.instrumentation_level` | string | **Required** | `"method"` for function-entry/exit instrumentation, `"line"` for line-level (breakpoint) instrumentation. Derived from whether the instrumentation `line_number > 0`. |
| `aws.di.instrumentation_type` | string | Optional | Category of instrumentation that produced this snapshot. One of: `"BREAKPOINT"`, `"PROBE"`. Set for every real snapshot the agent produces; only absent when the upstream `Snapshot` object has no type (edge case in tests). |
| `aws.di.code_unit` | string | Optional | Package/module path. Java: `com.example.order`. Python: `com.example.order_service`. |
| `aws.di.class_name` | string | Optional | Fully qualified class name. Java: `com.example.OrderService`. Python: `com.example.order_service`. .NET: `Example.OrderService`. JS: `OrderService`. |
| `aws.di.method_name` | string | Optional | Method or function name. |
| `aws.di.file_path` | string | Optional | Source file name (e.g., `OrderService.java`, `order_service.py`). |
| `aws.di.line_number` | number | Optional | Source line number. Emitted only for `instrumentation_level = "line"` (line-level instrumentation). |
| `aws.di.duration_ms` | number (float) | Optional | Method execution duration in milliseconds (entry to exit), as a floating-point value (typically fractional). Emitted for method-level instrumentation only; absent for line-level and also absent if the measured elapsed time was zero nanoseconds. |

> **Runtime language (Java/Python/JS/.NET) is not currently emitted as a snapshot attribute.** It is carried only by the instrumentation configuration, not the snapshot record. Consumers that need the language must look it up via `aws.di.location_hash`.

* * *

## Resource

Standard OTel resource. Only fields DI consumers care about are listed here — the resource may contain additional OTel-standard attributes merged in by the SDK (e.g., from `OTEL_RESOURCE_ATTRIBUTES`).

| Key | Type | Required | Description |
|---|---|---|---|
| `resource.attributes["service.name"]` | string | Optional | Service name. Absent if not configured. |
| `resource.attributes["deployment.environment"]` | string | Optional | Deployment environment under the **legacy** OTel semantic-conventions key. Emitted by the Python agent and by the Java agent's fallback resource. Absent if not configured. |
| `resource.attributes["deployment.environment.name"]` | string | Optional | Deployment environment under the **modern** OTel semantic-conventions key. Emitted by the Java agent when OTel autoconfiguration populates the resource from `OTEL_RESOURCE_ATTRIBUTES`. Absent if not configured. |

> **Dual-key lookup.** Because different agents / autoconfiguration paths emit different keys, consumers filtering on deployment environment should match **both** forms. The MCP implementation does this via `(resource.attributes.deployment.environment = "..." or resource.attributes.deployment.environment.name = "...")`.

* * *

## Body

Container for the captured execution state.

```json
{
  "stack": [ ... ],
  "captures": { ... }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `stack` | array | Optional | Call stack at the point of capture, ordered top (current frame) to bottom (entry point), with debugger-internal frames already filtered out. Emitted when the agent's configuration requests `CaptureStackTrace: true`, subject to `max_stack_frames`. The Python agent additionally never emits a stack for line-level captures, even when `CaptureStackTrace` is true; the Java agent emits stacks for both method-level and line-level captures. See [Stack Frame](#stack-frame). |
| `captures` | object | Optional | Captured variable data. See [Captures](#captures). Absent when no entry / return / line capture was produced; in that case the `body` itself may also be absent. |

* * *

## Stack Frame

Each element in `body.stack` represents one frame in the call stack.

```json
{
  "file_path": "string",
  "function": "string",
  "line_number": number
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | **Required** | Source file name or path. |
| `function` | string | **Required** | Function or method name. |
| `line_number` | number | **Required** | Line number in source file. `0` if unavailable. |

* * *

## Captures

Contains all captured variable data, organized by capture point.

```json
{
  "entry":  { CapturedContext },
  "return": { CapturedContext },
  "lines":  { "<line_number>": CapturedContext, ... }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `entry` | CapturedContext | Optional | State captured at function entry. Present for method-level instrumentation. |
| `return` | CapturedContext | Optional | State captured at function exit. Present for method-level instrumentation. |
| `lines` | map<string, CapturedContext> | Optional | State captured at specific line numbers. Key is the line number as a string. Present for line-level (breakpoint) instrumentation. |

In practice a `captures` block produced by the agent always carries at least one of `entry`, `return`, or `lines`; if none are produced, the agent omits the `captures` field entirely rather than emit an empty object.

* * *

## CapturedContext

Represents the variable state at a single capture point.

```json
{
  "arguments":    { ... },
  "locals":       { ... },
  "return_value": { ... },
  "throwable":    { ... }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `arguments` | map<string, CapturedValue> | Optional | Method/function parameters. Key is the parameter name. Present in `entry` context. May also be present in `return` context if the agent captures arguments at exit. |
| `locals` | map<string, CapturedValue> | Optional | Local variables in scope at the capture point. Key is the variable name. |
| `return_value` | CapturedValue | Optional | Method return value. Present only in `return` context when the method returned normally. Note the snake_case key name. |
| `throwable` | CapturedThrowable | Optional | Exception/error if the method exited via exception. Present only in `return` context. Null or absent if no exception. |

All fields are optional, but at least one MUST be present in a CapturedContext.

* * *

## CapturedValue

The core data structure representing a single captured value. This schema is uniform across all languages.

A CapturedValue contains `type` and exactly one of: `value`, `fields`, `elements`, `entries`, `is_null`, or `not_captured_reason`.

```json
{
  "type": "string",
  "value": "string",
  "fields": { ... },
  "elements": [ ... ],
  "entries": [ ... ],
  "is_null": true,
  "not_captured_reason": "string",
  "truncated": true,
  "size": number
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | **Required** | Type name of the value. Language-specific format (see [Type Naming](#type-naming)). |
| `value` | string | Conditional | String representation of the value. Present for primitives, numbers, strings, booleans, enums. Always a string — numeric values are string-encoded (e.g., `"42"`, `"3.14"`, `"true"`). |
| `fields` | map<string, CapturedValue> | Conditional | Object/struct fields. Key is the field name, value is a nested CapturedValue. Present for objects/structs/class instances. |
| `elements` | array<CapturedValue> | Conditional | Ordered collection elements. Present for arrays, lists, sets, tuples. |
| `entries` | array<CapturedMapEntry> | Conditional | Map/dictionary entries. Present for maps, dictionaries, hash tables. See [CapturedMapEntry](#capturedmapentry). |
| `is_null` | boolean | Conditional | `true` if the value is null/None/nil/undefined. When present, no other value fields are set. |
| `not_captured_reason` | string | Conditional | Reason the value was not fully captured. See [Not Captured Reasons](#not-captured-reasons). |
| `truncated` | boolean | Optional | `true` when capture stopped short of the full value. For strings, this means `value` was cut off at `max_string_length`. For collections and maps, it means `elements` / `entries` contains only the first `max_collection_width` items. In either case `size` carries the original size. |
| `size` | number | Optional | Original size before truncation. For strings: character count. For collections/maps: element count. |

### CapturedMapEntry

```json
{
  "key":   { CapturedValue },
  "value": { CapturedValue }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `key` | CapturedValue | **Required** | The map key, serialized as a CapturedValue. |
| `value` | CapturedValue | **Required** | The map value, serialized as a CapturedValue. |

### Not Captured Reasons

When a value cannot be captured at all, `not_captured_reason` is set to one of the following. **The literal string is agent-specific:** the Python agent emits lowercase camelCase (e.g., `"depth"`, `"fieldCount"`, `"timeout"`); the Java agent serializes the enum name as uppercase with underscores (e.g., `"DEPTH"`, `"FIELD_COUNT"`, `"TIMEOUT"`). Consumers that filter on this field must match both forms.

| Reason (Python / Java) | Description |
|---|---|
| `"depth"` / `"DEPTH"` | Maximum object traversal depth exceeded. Also used when a circular reference is detected while walking an object graph. |
| `"fieldCount"` / `"FIELD_COUNT"` | Object has more fields than `max_fields_per_object`. Fields captured up to the limit are still returned under `fields`; this reason indicates additional fields were dropped. Emitted by the Python agent; reserved in the Java enum but not currently produced by the Java serializer. |
| `"timeout"` / `"TIMEOUT"` | Serialization time budget exceeded. |

> Collections and maps that exceed `max_collection_width` are **not** marked with a `not_captured_reason`. Instead, the CapturedValue carries the first `max_collection_width` items in `elements` / `entries` and sets `truncated = true` plus `size = <original element count>`.

* * *

## CapturedThrowable

Represents an exception or error.

```json
{
  "type": "string",
  "message": "string",
  "stacktrace": [ StackFrame, ... ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | **Required** | Exception type name (e.g., `java.lang.NullPointerException`, `ValueError`, `TypeError`). |
| `message` | string | **Required** | Exception message, verbatim (no truncation is currently applied). Empty string if the exception carries no message. |
| `stacktrace` | array<StackFrame> | **Required** | Exception stack trace. Always present; may be an empty list. Same format as [Stack Frame](#stack-frame). |

* * *

## Type Naming

The `type` field in CapturedValue uses language-idiomatic type names:

| Category | Java | Python | JavaScript | .NET |
|---|---|---|---|---|
| Integer | `java.lang.Integer`, `java.lang.Long`, `java.lang.Short`, `java.lang.Byte` (boxed wrapper, from `getClass().getName()`) | `int` | `number` | `int` or `System.Int32` |
| Float | `java.lang.Double`, `java.lang.Float` (boxed wrapper) | `float` | `number` | `double` or `System.Double` |
| String | `java.lang.String` (hard-coded) | `str` | `string` | `System.String` |
| Boolean | `java.lang.Boolean` (boxed wrapper) | `bool` | `boolean` | `bool` or `System.Boolean` |
| Null | Type of the declared variable | `NoneType` | `null` | Type of the declared variable |
| Array | JVM descriptor from `Class.getName()` — `[I` for `int[]`, `[Ljava.lang.String;` for `String[]`, etc. | `list`, `tuple`, `set`, `frozenset` (the exact `type(value).__name__`) | `Array` | `System.Int32[]` |
| Map | Runtime class name from `getClass().getName()` (e.g., `java.util.HashMap`, `java.util.LinkedHashMap`) | `dict` | `Object` or `Map` | `System.Collections.Generic.Dictionary` |
| Object | Fully qualified class name from `getClass().getName()` | Qualified class name | Constructor name or class name | Fully qualified type name |

Agents use the most specific runtime type available. The Java agent always reports boxed wrapper names for primitives (never the unboxed `int` / `double` / `boolean` forms) and uses JVM descriptor syntax for arrays rather than Java source syntax.

* * *

## Capture Limits

Agents enforce the following configurable limits during serialization. Values supplied by the DI configuration are validated and clamped into the ranges below.

| Limit | Config key | Default | Min | Max | Description |
|---|---|---|---|---|---|
| Max object depth | `max_object_depth` | 3 | 1 | 5 | Maximum nesting depth for object field traversal. |
| Max collection width | `max_collection_width` | 10 | 1 | 20 | Maximum number of elements/entries captured from a collection or map. |
| Max string length | `max_string_length` | 100 | 1 | 255 | Maximum character length for string values before truncation. |
| Max fields per object | `max_fields_per_object` | 10 | 1 | 20 | Maximum number of fields captured per object. |
| Max stack frames | `max_stack_frames` | 2 | 1 | 20 | Maximum number of stack frames captured on the snapshot. |
| Max stack trace size | `max_stack_trace_size` | 200 | 1 | 1000 | Maximum number of frames in a throwable's stack trace. |
| Serialization timeout | (internal) | 200 ms | — | — | Time budget for serializing all captured values. |

When a limit is exceeded, the agent either sets `not_captured_reason` on the affected CapturedValue (depth, fieldCount, timeout) or returns a partial value with `truncated = true` and `size = <original size>` (string length, collection width).

> **Known limitation (Python agent).** The serializer that produces CapturedValues for method-level entry/return captures is currently constructed with its own module-level defaults (`max_collection_size = 20`, `max_string_length = 255`, `max_fields = 20`) rather than the user-configured `CaptureConfig` values. Line-level captures pass `CaptureConfig` limits through correctly. Consumers should not rely on the `CaptureConfig` numbers above holding for method-level snapshots until the wrapper is updated to re-configure the serializer per capture.

* * *

## Querying Snapshots in CloudWatch Logs Insights

Because snapshots are OTLP log records, filter expressions reference the wrapped paths, not bare field names:

```
fields @timestamp, @message
| filter attributes.aws.di.location_hash = "<hash>"
    and resource.attributes.service.name = "<service>"
    and resource.attributes.deployment.environment = "<env>"
| sort @timestamp desc
| limit 10
```

Common filter paths:

| Filter on | Path |
|---|---|
| Event type | `attributes.event.name` (`"aws.dynamic_instrumentation.snapshot"`) |
| Snapshot ID | `attributes.aws.di.snapshot_id` |
| Location hash (breakpoint) | `attributes.aws.di.location_hash` |
| Level (method vs line) | `attributes.aws.di.instrumentation_level` |
| Config type (BREAKPOINT / PROBE) | `attributes.aws.di.instrumentation_type` |
| Line number (line-level only) | `attributes.aws.di.line_number` |
| Service | `resource.attributes.service.name` |
| Environment | `resource.attributes.deployment.environment` (note: legacy key, not `.name`) |
| Trace correlation | `traceId`, `spanId` |
| Duration (method-level) | `attributes.aws.di.duration_ms` |

For captured values that don't round-trip as Insights fields (anything under `body`), fall back to `@message like /.../ ` regex matching.

* * *

## Complete Examples

### Line-level snapshot

```json
{
  "timeUnixNano": 1772082470861000000,
  "traceId": "699fd526604ca34dca1c02e0bdb2e7e4",
  "spanId": "5b312345a7a0e034",
  "attributes": {
    "event.name": "aws.dynamic_instrumentation.snapshot",
    "aws.di.snapshot_id": "a0476c7d-037a-4470-a52e-08fbdaa0d5e7",
    "aws.di.location_hash": "b1cca82f82fcd637",
    "aws.di.instrumentation_level": "line",
    "aws.di.instrumentation_type": "BREAKPOINT",
    "aws.di.code_unit": "com.amazon.sampleapp.basic",
    "aws.di.class_name": "com.amazon.sampleapp.basic.BasicMethods",
    "aws.di.method_name": "compute",
    "aws.di.file_path": "BasicMethods.java",
    "aws.di.line_number": 32
  },
  "resource": {
    "attributes": {
      "service.name": "demo-service",
      "deployment.environment": "staging"
    }
  },
  "body": {
    "stack": [
      {"file_path": "Thread.java", "function": "getStackTrace", "line_number": 2451},
      {"file_path": "DIDataStore.java", "function": "captureLocals", "line_number": 60},
      {"file_path": "LineBreakpointAdvice.java", "function": "onLineBreakpointHit", "line_number": 54},
      {"file_path": "BasicMethods.java", "function": "compute", "line_number": 32},
      {"file_path": "TestController.java", "function": "basicCompute", "line_number": 105}
    ],
    "captures": {
      "lines": {
        "32": {
          "locals": {
            "a": {"type": "java.lang.Integer", "value": "10"},
            "b": {"type": "java.lang.Integer", "value": "5"},
            "this": {
              "type": "com.amazon.sampleapp.basic.BasicMethods",
              "fields": {
                "instanceLabel": {"type": "java.lang.String", "value": "BASIC", "size": 5},
                "instanceCounter": {"type": "java.lang.Integer", "value": "42"}
              }
            },
            "sum": {"type": "java.lang.Integer", "value": "15"}
          }
        }
      }
    }
  }
}
```

### Method-level snapshot

```json
{
  "timeUnixNano": 1772082470861000000,
  "traceId": "699fd526604ca34dca1c02e0bdb2e7e4",
  "spanId": "5b312345a7a0e034",
  "attributes": {
    "event.name": "aws.dynamic_instrumentation.snapshot",
    "aws.di.snapshot_id": "759fea21-4c5f-4b70-90cf-7caf0fc63fb5",
    "aws.di.location_hash": "b1cca82f82fcd637",
    "aws.di.instrumentation_level": "method",
    "aws.di.instrumentation_type": "PROBE",
    "aws.di.code_unit": "com.amazon.sampleapp.basic",
    "aws.di.class_name": "com.amazon.sampleapp.basic.BasicMethods",
    "aws.di.method_name": "compute",
    "aws.di.file_path": "BasicMethods.java",
    "aws.di.duration_ms": 0.124531
  },
  "resource": {
    "attributes": {
      "service.name": "demo-service",
      "deployment.environment": "staging"
    }
  },
  "body": {
    "stack": [
      {"file_path": "Thread.java", "function": "getStackTrace", "line_number": 2451},
      {"file_path": "DIDataStore.java", "function": "captureMethodEntry", "line_number": 98},
      {"file_path": "BasicMethods.java", "function": "compute", "line_number": 31},
      {"file_path": "TestController.java", "function": "basicCompute", "line_number": 105}
    ],
    "captures": {
      "entry": {
        "arguments": {
          "arg1": {"type": "java.lang.Integer", "value": "5"},
          "arg0": {"type": "java.lang.Integer", "value": "10"}
        }
      },
      "return": {
        "return_value": {"type": "java.lang.Integer", "value": "65"}
      }
    }
  }
}
```

