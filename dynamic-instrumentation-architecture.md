# Dynamic Instrumentation MCP Tools — Architecture Notes

Reference notes for `private-aws-otel-python-instrumentation-staging/mcp/telemend_mcp/dynamic_instrumentation/`.

## Source layout

```
mcp/telemend_mcp/
├── server.py                 # FastMCP("Telemend") — host server
├── telemend_cli.py           # Telemend Server REST API client (NOT used by DI)
├── appsignals/               # Forked subset of awslabs server (registered conditionally)
├── dynamic_instrumentation/  # ★ THE THING WE ARE MERGING
│   ├── __init__.py           # empty marker
│   ├── registration.py       # public surface — `register_tools(mcp)`
│   ├── constants.py          # SNAPSHOT_SIGNAL_TYPE, SNAPSHOT_LOG_GROUP
│   ├── aws_clients.py        # ★ private-model boto3 client factory
│   ├── application_signals_gateway.py  # the only seam to botocore
│   ├── error_translation.py  # botocore exc → human prose
│   ├── aws_data/application-signals/2024-04-15/service-2.json  # ★ private API model
│   ├── crud_tools.py         # 6 tools: create / list / get / delete / batch-delete-by-scope / batch-delete-by-arns
│   ├── crud_rendering.py
│   ├── status_tools.py       # 3 tools: get / check / report
│   ├── status_assessment.py  # pure verdict logic (ACTIVE → READY → ERROR/PENDING)
│   ├── status_rendering.py
│   ├── snapshot_tools.py     # 2 tools: search_snapshots_for_status_event / get_sample_snapshot_for_breakpoint
│   ├── snapshot_queries.py   # CW Logs Insights helpers
│   ├── snapshot_parsing.py
│   ├── snapshot_rendering.py
│   ├── location.py           # Location ADT (CodeLocation | HashLocation)
│   ├── capture.py            # Capture ADT (CodeCapture | UnknownCapture) + CaptureLimits
│   ├── validation.py         # shared input validators
│   ├── formatting.py
│   ├── README.md             # design notes (very good — keep as design ground truth)
│   └── snapshot-spec.md
└── tests/
    ├── test_dynamic_instrumentation_helpers.py  # 907 lines
    ├── test_dynamic_instrumentation_eval.py     # LLM eval
    ├── test_capture_adt.py                      # 119 lines
    ├── test_status_assessment.py                # 150 lines
    ├── test_snapshot_queries.py                 # 150 lines
    └── conftest.py
```

About 4070 lines of `.py` plus the 4286-line bundled service model JSON.

## What the tools do (the 11-tool surface)

### CRUD family (`crud_tools.py`)

1. `create_instrumentation` — creates a BREAKPOINT/PROBE (code) configuration.
   Returns the `LocationHash` and resolved location details.
2. `list_instrumentations` — list active configs filtered by `service` / `environment`.
3. `get_instrumentation` — look up by code location or location hash.
4. `delete_instrumentation` — single delete, same lookup forms as `get`.
5. `batch_delete_instrumentations_by_scope` — delete all configs for `service` + `environment`.
6. `batch_delete_instrumentations_by_arns` — delete by explicit ARN list.

### Status family (`status_tools.py`)

7. `get_instrumentation_configuration_status` — raw event-history pull.
8. `check_instrumentation_status` — consolidated verdict (ACTIVE/READY/ERROR/PENDING) backed by `status_assessment.assess`.
9. `report_instrumentation_configuration_status` — agent-side reporter (writes a status event).

### Snapshot family (`snapshot_tools.py`)

10. `search_snapshots_for_status_event` — query CW Logs for snapshot events matching a status event.
11. `get_sample_snapshot_for_breakpoint` — pick one representative captured snapshot for a breakpoint.

All return JSON strings (not prose) for the snapshot family; CRUD/status return human-readable prose.

## Critical design fact: bundled private service model

`aws_clients.py` does not call `boto3.client("application-signals")` — instead:

```python
botocore_session = botocore.session.Session()
botocore_session.get_component("data_loader").search_paths.insert(0, str(AWS_DATA_PATH))
session = boto3.Session(botocore_session=botocore_session, profile_name=profile)
client = session.client(
    "application-signals",
    api_version="2024-04-15",       # ← pinned
    region_name=region,
    endpoint_url=os.environ.get("DYNAMIC_INSTRUMENTATION_ENDPOINT_URL"),
    config=Config(user_agent_extra="..."),
)
```

The bundled model lives at `aws_data/application-signals/2024-04-15/service-2.json`.
This file declares operations that are NOT in the public botocore release yet:

```
CreateInstrumentationConfiguration
ListInstrumentationConfigurations
GetInstrumentationConfiguration
DeleteInstrumentationConfiguration
BatchDeleteInstrumentationConfigurations
GetInstrumentationConfigurationStatus
ReportInstrumentationConfigurationStatus

# plus several TeleMend* operations the staging server uses,
# but the dynamic_instrumentation tools only call the 7 above.
```

**The pinned `api_version="2024-04-15"` and the scoped data loader together
guarantee that the bundled (private) model is found instead of any public
model that ships with botocore in the future.** The env-var `AWS_DATA_PATH`
is intentionally NOT mutated — that would leak to other processes and
break sibling AWS calls.

The bundled JSON is licensed/owned by AWS Application Signals and ships in the
package.

## Single-seam pattern: the gateway

`application_signals_gateway.py` is the only file that imports
`botocore.exceptions`. Every CRUD/status tool calls one of these typed wrappers:

```python
def create_instrumentation_configuration(**kwargs) -> dict: ...
def list_instrumentation_configurations(**kwargs) -> dict: ...
def get_instrumentation_configuration(**kwargs) -> dict: ...
def delete_instrumentation_configuration(**kwargs) -> dict: ...
def batch_delete_instrumentation_configurations(**kwargs) -> dict: ...
def get_instrumentation_configuration_status(**kwargs) -> dict: ...
def report_instrumentation_configuration_status(**kwargs) -> dict: ...

def render_error(err: GatewayError, *, action, attempted, possible_causes, troubleshooting, trailer) -> str: ...
```

Internally:

```python
def _call(method_name, **kwargs):
    try:
        return getattr(get_application_signals_client(), method_name)(**kwargs)
    except (BotoCoreError, ClientError) as exc:
        raise GatewayError(exc) from exc
```

Programming errors (`AttributeError`, `TypeError`) propagate raw — only
`BotoCoreError` and `ClientError` get wrapped. This invariant matters for
debugging and is worth preserving.

## Domain ADTs

`location.py` and `capture.py` define small sealed sum types so the three
location flavors (CodeLocation / LocationHash) and the two
capture flavors (CodeCapture) live in exactly one place.

Tools don't inspect raw dicts — they parse to the ADT first, then call
`.to_api_payload()` / `.to_identifier()` / `.describe()`. Renderers parse the
API response into the same ADT and call `.format_details()` / `.level()`.

This is why the package is so cleanly partitioned into `*_tools.py` /
`*_rendering.py` / `*_queries.py`. Stick to that partition when integrating.

## Constants and environment

```python
# constants.py
SNAPSHOT_SIGNAL_TYPE = "SNAPSHOT"          # always SNAPSHOT in this package
SNAPSHOT_LOG_GROUP = "/telemend/telemetry"  # CW log group snapshots land in
```

Environment variables read by this package:

- `AWS_REGION` — direct read (also via boto3 profile fallback).
- `AWS_PROFILE` — passed to `boto3.Session(profile_name=...)`.
- `MCP_RUN_FROM` — appended to user-agent string.
- `DYNAMIC_INSTRUMENTATION_ENDPOINT_URL` — optional `endpoint_url` override
  for the application-signals client only (Logs client does not honor it).

NOTE: `SNAPSHOT_LOG_GROUP` is hardcoded to `/telemend/telemetry`. This is the log group the snapshot tools query via CW Logs Insights. There is no env override for this. (May want to add one when integrating.)

## How tools are registered onto the host server

```python
# registration.py
def register_tools(mcp) -> None:
    mcp.tool()(create_instrumentation)
    mcp.tool()(list_instrumentations)
    mcp.tool()(get_instrumentation)
    mcp.tool()(delete_instrumentation)
    mcp.tool()(batch_delete_instrumentations_by_scope)
    mcp.tool()(batch_delete_instrumentations_by_arns)

    mcp.tool()(get_instrumentation_configuration_status)
    mcp.tool()(check_instrumentation_status)
    mcp.tool()(report_instrumentation_configuration_status)

    mcp.tool()(search_snapshots_for_status_event)
    mcp.tool()(get_sample_snapshot_for_breakpoint)
```

Called from `server.py::main()` after env setup:

```python
from telemend_mcp.dynamic_instrumentation.registration import register_tools
register_tools(mcp)
```

This is the only public coupling between the package and its host. The package
explicitly does NOT create its own `FastMCP` — that contract should be preserved
when we move it under awslabs.

## Tests we should bring along

| Test file | What it covers | Lines |
|---|---|---|
| `test_dynamic_instrumentation_helpers.py` | end-to-end happy/error paths for all CRUD + status tools, mocking `gateway._call` | 907 |
| `test_capture_adt.py` | round-trip serialization for `Capture` ADT | 119 |
| `test_status_assessment.py` | `assess()` priority and ACTIVE-window clamp | 150 |
| `test_snapshot_queries.py` | CW Logs Insights start/poll helper behavior | 150 |
| `test_dynamic_instrumentation_eval.py` | LLM eval — likely skip on initial port |  |
| `conftest.py` (relevant fixtures) | mock setup | 71 |

The eval test depends on Bedrock and is gated by a marker — defer.

## Logging

The package uses stdlib `logging` (`logger = logging.getLogger(__name__)`),
NOT loguru. The awslabs server uses loguru. We will need to either
(a) leave the package on stdlib logging and let it propagate to loguru's
intercept handler, or (b) convert imports. Stdlib already propagates to the
root logger which loguru reads — so no work needed unless we want pretty
formatted DI logs in the rotating file.

## What relies on the host server

The package deliberately depends on as little of the Telemend host as
possible. Concretely:

- It does NOT import `telemend_mcp.telemend_cli`.
- It does NOT import `telemend_mcp.appsignals.*`.
- It DOES import `from .. import __version__` (just for the user-agent string).

So merging it into the awslabs server only requires:

1. Copying the package directory verbatim into `awslabs/cloudwatch_applicationsignals_mcp_server/dynamic_instrumentation/`.
2. Fixing the `from .. import __version__` import to point at the awslabs package.
3. Calling `register_tools(mcp)` from awslabs `server.py::main()` (or doing the registration inline).
4. Bundling `aws_data/**/*.json` into the wheel (`tool.hatch.build.targets.wheel.artifacts` already supports this).
5. Porting the test files into `tests/` (rename imports from `telemend_mcp.dynamic_instrumentation.*` to the awslabs path).

Open question: do we want the gateway to share the awslabs `applicationsignals_client` (single client, no private model) — or stand up a separate private-model client (today's behavior)? The separate-client approach is the only one that actually works because the public client doesn't know about the private operations.
