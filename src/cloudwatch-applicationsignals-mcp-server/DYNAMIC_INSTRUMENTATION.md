# Dynamic Instrumentation Tools (private beta)

This document covers the dynamic-instrumentation MCP tools while the underlying
AWS Application Signals operations are in **private beta**. It is intended for
internal/dev consumers of the feature branch, not for public release.

> **Status: feature-branch only.** These tools and the bundled private service
> model (`dynamic_instrumentation/aws_data/`) must **not** ship in a public PyPI
> release. See the cleanup checklist below.

## What it adds

11 MCP tools for managing live instrumentation configurations and inspecting
the snapshots they produce:

| Tool | Family | Purpose |
|---|---|---|
| `create_instrumentation` | CRUD | Create a BREAKPOINT/PROBE (code) or WATCHER (endpoint) config |
| `list_instrumentations` | CRUD | List configs for a service/environment |
| `get_instrumentation` | CRUD | Look up one config by code location, watcher endpoint, or location hash |
| `delete_instrumentation` | CRUD | Delete one config |
| `batch_delete_instrumentations_by_scope` | CRUD | Delete all configs for a service+environment |
| `batch_delete_instrumentations_by_arns` | CRUD | Delete configs by explicit ARN list |
| `get_instrumentation_configuration_status` | Status | Raw status event history |
| `check_instrumentation_status` | Status | Consolidated verdict (ACTIVE/READY/ERROR/PENDING) |
| `report_instrumentation_configuration_status` | Status | Write a status event |
| `search_snapshots_for_status_event` | Snapshot | Find snapshots matching a status event |
| `get_sample_snapshot_for_breakpoint` | Snapshot | Pick one representative captured snapshot |

## How it is wired in

- Implementation lives under `awslabs/cloudwatch_applicationsignals_mcp_server/dynamic_instrumentation/`.
- Tools are registered at module top of `server.py` via
  `register_dynamic_instrumentation_tools(mcp)`.
- The package is self-contained: it imports only `__version__` from the parent
  package and otherwise depends on nothing in the awslabs server.

## Private service model

The dynamic-instrumentation operations are not in public botocore yet, so the
package bundles a private service model at
`dynamic_instrumentation/aws_data/application-signals/2024-04-15/service-2.json`.

`dynamic_instrumentation/aws_clients.py` builds a **dedicated** `application-signals`
boto3 client using a *session-scoped* botocore data loader (no `AWS_DATA_PATH`
env mutation) with `api_version="2024-04-15"` pinned. This client is isolated
from the awslabs `applicationsignals_client` used by all other tools — the
bundled model is invisible to existing operations.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DYNAMIC_INSTRUMENTATION_ENDPOINT_URL` | Endpoint override for the dynamic-instrumentation `application-signals` client only | unset (normal AWS resolution) |
| `MCP_DYNAMIC_INSTRUMENTATION_SNAPSHOT_LOG_GROUP` | CloudWatch log group the snapshot tools query | `/telemend/telemetry` |

Region and credentials are resolved the same way as the rest of the server
(`AWS_REGION`, `AWS_PROFILE`, standard credential chain).

## Required IAM permissions

```
application-signals:CreateInstrumentationConfiguration
application-signals:ListInstrumentationConfigurations
application-signals:GetInstrumentationConfiguration
application-signals:DeleteInstrumentationConfiguration
application-signals:BatchDeleteInstrumentationConfigurations
application-signals:GetInstrumentationConfigurationStatus
application-signals:ReportInstrumentationConfigurationStatus
logs:StartQuery
logs:GetQueryResults
```

The account must be allowlisted for the private-beta API. Calls from
non-allowlisted accounts fail with `AccessDeniedException`, which the tools
render into actionable text.

## Cleanup checklist (when the public SDK ships)

This is the one-shot change that makes the feature mergeable to mainline:

1. Bump the `boto3` floor in `pyproject.toml` to the version that ships the
   dynamic-instrumentation operations in public `application-signals` data.
2. Rewrite `dynamic_instrumentation/aws_clients.py` to re-export the parent
   `applicationsignals_client` / `logs_client`:
   ```python
   from ..aws_clients import applicationsignals_client, logs_client

   def get_application_signals_client():
       return applicationsignals_client

   def get_cloudwatch_logs_client():
       return logs_client
   ```
3. Delete the `dynamic_instrumentation/aws_data/` directory.
4. Drop `DYNAMIC_INSTRUMENTATION_ENDPOINT_URL` from docs (the parent client
   already honors `MCP_APPLICATIONSIGNALS_ENDPOINT`).
5. README + CHANGELOG entries; bump version (minor).
6. Run the full test suite — the gateway/tools/renderers never import anything
   from `aws_data/`, so this should pass with no behavior change.
