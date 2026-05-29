# Telemend Dynamic Instrumentation Package

Last updated: 2026-03-10

This package contains the dynamic instrumentation feature implementation that is hosted inside the shared `telemend_mcp` server.

## What This Package Does

- Implements dynamic instrumentation CRUD, status inspection/reporting, source inspection, and snapshot analysis tools.
- Keeps tool implementation files separate from support code such as rendering, validation, location/capture payload building, and AWS API access.
- Registers its tool surface onto the shared Telemend MCP server through `registration.py`.
- Uses `SignalType=SNAPSHOT` for the dynamic instrumentation APIs in this package.

## Where To Start

- Host MCP server entrypoint: `../server.py`
- Dynamic instrumentation registration entrypoint: `registration.py`
- Shared package constants: `constants.py`

If you want to find the dynamic instrumentation tool implementations quickly, open the `*_tools.py` files first, then check `registration.py` to see the public MCP surface.

## boto3 Client Initialization

Dynamic instrumentation calls the `application-signals` API directly through a
`boto3` client. The service has private operations not yet shipped in the
public botocore data, so the package bundles its own service model under
`aws_data/application-signals/2024-04-15/service-2.json`.

`aws_clients.py` builds a botocore session with a *scoped* data loader —
`session.get_component("data_loader").search_paths.insert(0, AWS_DATA_PATH)` —
so the bundled model is found before the public one. No `AWS_DATA_PATH`
environment variable is set, so this configuration cannot leak to other
processes. The `application-signals` client is then constructed with
`api_version="2024-04-15"` pinned, which protects against future botocore
updates that ship a different version of the service.

The factory exposes two lazy singletons:

- `get_application_signals_client()` — used internally by the
  `application_signals_gateway` module. CRUD and status tools never call this
  directly; they go through the gateway.

Snapshot CloudWatch Logs Insights queries reuse the parent server's shared
`logs_client` (`from .. import aws_clients; aws_clients.logs_client`) rather
than a local Logs client, so they inherit `MCP_LOGS_ENDPOINT` and `AWS_PROFILE`
handling from the rest of the server.

If `DYNAMIC_INSTRUMENTATION_ENDPOINT_URL` is set, the `application-signals`
client honors it as an endpoint override; otherwise normal AWS endpoint
resolution applies.

## application-signals Gateway

`application_signals_gateway.py` is the single seam where dynamic-instrumentation
tools touch botocore. Every CRUD and status tool issues its AWS call through one
of the gateway's typed operations and catches a single exception type,
`gateway.GatewayError`. The gateway then renders that error through the shared
`render_error` helper, which routes `ClientError` instances with tailored
prose to `error_translation.render_client_error` and falls back to
`error_translation.translate_aws_error` for everything else (and for
`ClientError`s where the caller did not pass tailored prose). Tool functions
no longer import `botocore.exceptions` — that contract belongs to the gateway.

## File Map

### Public surface and registration

- `__init__.py`
  Package marker for the nested feature package. It intentionally avoids importing tool modules at import time.
- `registration.py`
  Registers the dynamic instrumentation tool functions onto a shared MCP server object.
- `constants.py`
  Shared runtime constants such as signal type and snapshot log group.
- `aws_clients.py`
  Lazy boto3 client factory for the private-model `application-signals` client
  only. Loads the bundled private service model via a scoped botocore data
  loader and pins the API version to `2024-04-15`. Snapshot Logs queries use the
  parent server's shared `logs_client`, not this factory.
- `application_signals_gateway.py`
  The only module that calls `application-signals` boto3 operations and
  catches `botocore` exceptions. Wraps any failure in `GatewayError` and
  exposes `render_error(...)` so tools can route a single exception type to
  tool-tailored prose.
- `error_translation.py`
  Templates that turn `botocore` exceptions (`ClientError`,
  `EndpointConnectionError`, `NoCredentialsError`, etc.) into the
  human-readable failure text returned by MCP tools. Called by the gateway,
  not by tools.
- `aws_data/application-signals/2024-04-15/service-2.json`
  Bundled service model for `application-signals` private beta APIs. Loaded
  via the scoped botocore data loader configured in `aws_clients.py` — no
  `AWS_DATA_PATH` env mutation and no manual `aws configure add-model` step.

### Tool implementation modules

- `crud_tools.py`
  Tool implementation functions for create/list/get/delete and batch-delete instrumentation flows.
- `status_tools.py`
  Tool implementation functions for explicit status history, consolidated status checks, and status reporting.
- `snapshot_tools.py`
  Tool implementation functions for CloudWatch snapshot search and sample-snapshot discovery.

### Support modules

- `crud_rendering.py`
  Human-readable response formatting for CRUD flows.
- `status_assessment.py`
  Pure-function consolidated status verdict. Owns the ACTIVE-window clamp
  (don't search ACTIVE before `created_at`) and the priority order
  (ACTIVE → READY → ERROR/PENDING). `assess()` takes a `check_status`
  callable so the policy is testable without AWS.
- `status_rendering.py`
  Human-readable response formatting for status flows. Includes
  `render_status_assessment(verdict, ...)`, the single dispatcher routing
  a `Verdict` to one of the three consolidated-status renderers.
- `snapshot_queries.py`
  CloudWatch Logs Insights start/poll helpers.
- `snapshot_parsing.py`
  Snapshot JSON parsing and captured-value preview helpers.
- `snapshot_rendering.py`
  JSON response assembly for snapshot-tool outputs.
- `location.py`
  Location payload builders, location identifier resolution, and location rendering helpers.
- `capture.py`
  Capture payload builders and capture-union parsing helpers.
- `validation.py`
  Input validation and normalization helpers shared across tools.

## Naming Conventions

- `*_tools.py`
  Plain MCP tool implementation functions. Registration lives in `registration.py`.
- `*_rendering.py`
  Response formatting only. These files should not own AWS calls or MCP registration.
- `*_queries.py`
  Backend/API query helpers only.
- `location.py`
  The `Location` ADT (sealed sum: `CodeLocation` | `WatcherLocation` |
  `HashLocation`) plus its parsers (`parse_create_inputs`,
  `parse_lookup_inputs`, `location_from_response`). Tools turn flat MCP
  kwargs into a `Location` here and call `.to_api_payload()` /
  `.to_identifier()` / `.describe()`; renderers turn API response unions
  into a `Location` here and call `.format_details()` / `.level()`.
- `capture.py`
  The `Capture` ADT (sealed sum: `CodeCapture` | `WatcherCapture` |
  `UnknownCapture`) plus `CaptureLimits` and `capture_from_response`. Tools
  build `CodeCapture`/`WatcherCapture` directly and call `.to_api_payload()`;
  renderers parse the API response with `capture_from_response` and read
  fields from the ADT. The `CaptureArguments` "omitted vs. empty list"
  distinction survives the round-trip.
- `validation.py`
  Shared domain helpers used by multiple tool families.
- `aws_clients.py`
  Shared boto3 client plumbing, not MCP tool logic.
- `application_signals_gateway.py`
  The single seam between tools and the `application-signals` boto3 client.
  Tools that need to call AWS go here, not directly to `aws_clients.py`.
- `error_translation.py`
  Shared boto3-exception → human-text templates, called by the gateway.
- `registration.py`
  The only file in this package that should know the complete dynamic instrumentation MCP surface.
- `constants.py`
  Package-wide defaults and identifiers, but not the MCP server object itself.

## Design Rules

- `telemend_mcp/server.py` owns the only live `FastMCP(...)` instance.
- This package must not create its own MCP server object.
- Keep tool implementation files thin.
  Tool files should mostly handle input flow, validation, orchestration, and tool-facing docstrings.
- Keep customer-facing formatting out of tool files when it becomes large.
  Use `*_rendering.py`.
- Keep backend polling/query code out of tool files when it is reusable or verbose.
  Use `*_queries.py`.
- The `Location` ADT in `location.py` is the only place that knows the three
  location flavors (CodeLocation / WatcherLocation / LocationHash). Tools and
  renderers should never inspect raw `Location` / `LocationIdentifier` dicts;
  parse to the ADT first.
- Put shared payload shape logic in `location.py` and `capture.py`.
- Put fail-fast validation in `validation.py` when it is reused across tools.
- Prefer well-scoped files with meaningful naming.

## Current Behavioral Invariants

- Code instrumentation requires explicit `capture_arguments`.
- `WATCHER` participates in CRUD flows but not the code-only status APIs.
- Snapshot search/sample tools return JSON strings, not prose summaries.
- Tool responses intentionally surface actionable error text instead of Python stack traces.
- Dynamic instrumentation tools are registered in `main()` after Telemend sets runtime environment variables.
- `DYNAMIC_INSTRUMENTATION_ENDPOINT_URL` can be set in the MCP server env to force an API endpoint override. If unset, the boto3 clients use normal AWS endpoint resolution.

## How To Navigate By Task

- Add or change a CRUD tool:
  Start in `crud_tools.py`, then check `crud_rendering.py`, `location.py`, `capture.py`, and `validation.py`.
- Add or change a status tool:
  Start in `status_tools.py`, then check `application_signals_gateway.py`, `status_rendering.py`, `location.py`, and `validation.py`.
- Add or change a snapshot tool:
  Start in `snapshot_tools.py`, then check `snapshot_queries.py`, `snapshot_parsing.py`, and `snapshot_rendering.py`.
- Add or change an `application-signals` AWS call:
  Start in `application_signals_gateway.py` (operation seam) or `error_translation.py` (exception → text).
- Change boto3 client construction:
  Start in `aws_clients.py`.
- Change the exposed MCP tool surface:
  Start in `registration.py` and `../server.py`.
- Change package-wide defaults:
  Start in `constants.py`.

## Testing Notes

- Main helper/unit coverage lives in `../tests/test_dynamic_instrumentation_helpers.py`.
- `server.py` process launch is not deeply covered by current tests.
- After changing module boundaries or registration, re-run:
  `python3 -m pytest telemend_mcp/tests/test_dynamic_instrumentation_helpers.py`

## Recommended Reading Order For A New Agent

1. `README.md`
2. `../server.py`
3. `registration.py`
4. `constants.py`
5. The relevant `*_tools.py` file for the feature you are changing
6. The adjacent support files for that tool family
