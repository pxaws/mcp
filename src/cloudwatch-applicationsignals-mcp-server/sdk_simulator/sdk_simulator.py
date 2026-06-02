"""DI SDK simulator for MCP e2e testing.

Simulates the runtime behavior of the Java/Python DI agent:

1. Publishes status events (READY/ACTIVE) to the Application Signals
   `report_instrumentation_configuration_status` API — same call the real SDK
   makes when it picks up a breakpoint config and confirms install.

2. Writes synthetic snapshot records to the CloudWatch Logs `/telemend/telemetry`
   log group — matching the exact JSON shape the real Java agent emits, so the
   MCP's `search_snapshots_for_status_event` and `get_sample_snapshot_for_breakpoint`
   queries find them and parse them correctly.

This lets the di-e2e-test skill verify the full data path through the MCP
(status query → AWS → response, snapshot query → CloudWatch Logs Insights →
parsing → rendering) without needing a Java/Python sample app or traffic.

Why this exists: conflating MCP correctness with DI-agent runtime behavior
makes tests flaky (poll cadence, JVM warm-up, traffic timing). This simulator
provides deterministic, on-demand data so the e2e test can be deterministic.
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# Reuse the MCP's Application Signals client factory, which loads the bundled
# private service model (aws_data/) and pins the API version. boto3.client(
# "application-signals", ...) on its own does NOT see report_instrumentation_configuration_status.
# This module lives inside the MCP package, so the import resolves directly when
# run via `uv run` from the package root (no sys.path hacking needed).
from awslabs.cloudwatch_applicationsignals_mcp_server.dynamic_instrumentation.aws_clients import (
    get_application_signals_client,
)

LOG_GROUP = "/telemend/telemetry"
LOG_STREAM = "default"

logger = logging.getLogger("di-sdk-simulator")


def _resolve_region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def _ensure_log_stream(logs_client, log_group: str, log_stream: str) -> None:
    """Create log group + stream if they don't exist; idempotent."""
    try:
        logs_client.create_log_group(logGroupName=log_group)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise
    try:
        logs_client.create_log_stream(logGroupName=log_group, logStreamName=log_stream)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise


def _build_snapshot_record(
    service_name: str,
    environment: str,
    location_hash: str,
    snapshot_index: int,
    timestamp_ms: int,
    class_name: str = "MockClass",
    method_name: str = "mockMethod",
    file_path: str = "MockClass.java",
    code_unit: str = "com.amazon.test",
) -> dict:
    """Build one synthetic snapshot envelope matching the Java DI agent's emit shape."""
    time_unix_nano = timestamp_ms * 1_000_000
    snapshot_id = str(uuid.uuid4())
    order_id = f"ORD-SIM{snapshot_index:08X}"
    payment_ref = f"PAY-SIM{snapshot_index:08X}"
    amount_value = 100.0 + (snapshot_index % 50) * 17.5
    return {
        "resource": {
            "attributes": {
                "service.name": service_name,
                "deployment.environment.name": environment,
                "telemetry.sdk.name": "opentelemetry",
                "telemetry.sdk.language": "java",
                "telemetry.sdk.version": "1.57.0",
                "telemetry.distro.name": "opentelemetry-java-instrumentation",
                "telemetry.distro.version": "2.20.0-aws-SNAPSHOT",
                "service.instance.id": "sim-instance-0001",
                "process.runtime.name": "OpenJDK Runtime Environment",
                "process.runtime.version": "17.0.19+0",
            },
            "schemaUrl": "https://opentelemetry.io/schemas/1.24.0",
        },
        "scope": {"name": "aws.dynamic.instrumentation", "version": "1.0"},
        "timeUnixNano": time_unix_nano,
        "observedTimeUnixNano": time_unix_nano,
        "severityNumber": 0,
        "severityText": "",
        "body": {
            "captures": {
                "entry": {
                    "arguments": {
                        "orderId": {
                            "type": "java.lang.String",
                            "size": len(order_id),
                            "value": order_id,
                        },
                        "amount": {
                            "type": "java.lang.Double",
                            "value": str(amount_value),
                        },
                    }
                },
                "return": {
                    "return_value": {
                        "type": f"{code_unit}.{class_name}$MockResult",
                        "fields": {
                            "orderId": {
                                "type": "java.lang.String",
                                "size": len(order_id),
                                "value": order_id,
                            },
                            "paymentRef": {
                                "type": "java.lang.String",
                                "size": len(payment_ref),
                                "value": payment_ref,
                            },
                            "amount": {"type": "java.lang.Double", "value": str(amount_value)},
                            "status": {"type": "java.lang.String", "size": 7, "value": "SUCCESS"},
                        },
                    }
                },
            },
            "stack": [
                {
                    "class": f"{code_unit}.{class_name}",
                    "method": method_name,
                    "file": file_path,
                    "line": 42,
                }
            ],
        },
        "attributes": {
            "aws.di.instrumentation_type": "BREAKPOINT",
            "aws.di.class_name": class_name,
            "aws.di.code_unit": code_unit,
            "aws.di.instrumentation_level": "method",
            "aws.di.duration_ms": 50 + (snapshot_index % 100),
            "aws.di.method_name": method_name,
            "event.name": "aws.dynamic_instrumentation.snapshot",
            "aws.di.location_hash": location_hash,
            "aws.di.file_path": file_path,
            "aws.di.snapshot_id": snapshot_id,
        },
        "flags": 0,
        "traceId": uuid.uuid4().hex,
        "spanId": uuid.uuid4().hex[:16],
    }


_ALLOWED_ERROR_CAUSES = {
    "FILE_NOT_FOUND",
    "METHOD_NOT_FOUND",
    "LINE_NOT_EXECUTABLE",
    "OVERLOADED_METHODS",
    "LANGUAGE_MISMATCH",
    "RUNTIME_ERROR",
}
_ALLOWED_STATUSES = {"READY", "ACTIVE", "ERROR", "DISABLED"}


def _parse_status_token(token: str) -> tuple:
    """Parse a status token like 'READY' or 'ERROR:METHOD_NOT_FOUND'.

    Returns (status, error_cause_or_none). Validates against the API's allowed
    enums so a bad token fails fast instead of producing a server-side rejection.
    """
    if ":" in token:
        status, error_cause = token.split(":", 1)
    else:
        status, error_cause = token, None
    status = status.strip().upper()
    if error_cause is not None:
        error_cause = error_cause.strip().upper()
    if status not in _ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Allowed: {sorted(_ALLOWED_STATUSES)}"
        )
    if error_cause is not None and error_cause not in _ALLOWED_ERROR_CAUSES:
        raise ValueError(
            f"Invalid error cause '{error_cause}'. Allowed: {sorted(_ALLOWED_ERROR_CAUSES)}"
        )
    if error_cause is not None and status != "ERROR":
        raise ValueError(
            f"ErrorCause '{error_cause}' only valid with status=ERROR (got status={status})"
        )
    return status, error_cause


def _report_status_events(
    appsignals_client,
    service: str,
    environment: str,
    location_hash: str,
    status_tokens: list,
) -> list:
    """Submit one or more status events for a breakpoint config.

    Each token in ``status_tokens`` is either a bare status name (``READY``,
    ``ACTIVE``, ``DISABLED``) or ``ERROR:CAUSE`` (e.g.
    ``ERROR:METHOD_NOT_FOUND``). ErrorCause is only appended to ERROR events.

    Uses the same API the real DI agent calls when it picks up a breakpoint
    config and confirms install. The MCP's check_instrumentation_status and
    get_instrumentation_configuration_status tools query these events back.

    Returns the list of normalized configurations submitted (one dict per
    event), so the caller can include them in the JSON summary.
    """
    from datetime import timedelta as _td

    now = datetime.now(timezone.utc)
    configurations = []
    submitted = []
    for i, token in enumerate(status_tokens):
        status, error_cause = _parse_status_token(token)
        # Stagger by 1 second so events have monotonic timestamps; oldest first.
        event_time = now.replace(microsecond=0)
        ts = event_time - _td(seconds=(len(status_tokens) - i - 1))
        cfg = {
            "InstrumentationType": "BREAKPOINT",
            "SignalType": "SNAPSHOT",
            "LocationHash": location_hash,
            "Status": status,
            "Time": ts.isoformat().replace("+00:00", "Z"),
        }
        if error_cause is not None:
            cfg["ErrorCause"] = error_cause
        configurations.append(cfg)
        submitted.append({"status": status, "error_cause": error_cause, "time": cfg["Time"]})

    response = appsignals_client.report_instrumentation_configuration_status(
        Service=service,
        Environment=environment,
        Configurations=configurations,
    )
    unprocessed = response.get("UnprocessedConfigurations", []) or response.get("UnprocessedEvents", [])
    logger.info(
        "Reported %d status events: reported=%d unprocessed=%d",
        len(configurations),
        len(configurations) - len(unprocessed),
        len(unprocessed),
    )
    return submitted


def _emit_snapshots(
    logs_client,
    service: str,
    environment: str,
    location_hash: str,
    count: int,
    class_name: str,
    method_name: str,
    file_path: str,
    code_unit: str,
) -> list:
    """Write `count` snapshot records to /telemend/telemetry. Returns timestamps."""
    _ensure_log_stream(logs_client, LOG_GROUP, LOG_STREAM)
    base_ms = int(time.time() * 1000)
    timestamps = []
    log_events = []
    for i in range(count):
        ts_ms = base_ms + i * 100
        timestamps.append(ts_ms)
        record = _build_snapshot_record(
            service_name=service,
            environment=environment,
            location_hash=location_hash,
            snapshot_index=i,
            timestamp_ms=ts_ms,
            class_name=class_name,
            method_name=method_name,
            file_path=file_path,
            code_unit=code_unit,
        )
        log_events.append({"timestamp": ts_ms, "message": json.dumps(record, separators=(",", ":"))})
    logs_client.put_log_events(
        logGroupName=LOG_GROUP,
        logStreamName=LOG_STREAM,
        logEvents=log_events,
    )
    logger.info("Emitted %d snapshot records to %s/%s", count, LOG_GROUP, LOG_STREAM)
    return timestamps


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Simulate the DI SDK runtime: report status + emit snapshots."
    )
    parser.add_argument("--service", required=True, help="Service name (must match the breakpoint config)")
    parser.add_argument(
        "--environment", required=True, help="Environment name (must match the breakpoint config)"
    )
    parser.add_argument(
        "--location-hash", required=True, help="Breakpoint location_hash (16-char hex)"
    )
    parser.add_argument(
        "--snapshots",
        type=int,
        default=3,
        help="Number of synthetic snapshots to emit (default 3, set 0 to skip)",
    )
    parser.add_argument(
        "--statuses",
        default="READY,ACTIVE",
        help=(
            "Comma-separated status events to publish (default READY,ACTIVE; '' to skip). "
            "Each token is a status name (READY, ACTIVE, DISABLED) or ERROR:CAUSE — e.g. "
            "ERROR:METHOD_NOT_FOUND. Allowed causes: FILE_NOT_FOUND, METHOD_NOT_FOUND, "
            "LINE_NOT_EXECUTABLE, OVERLOADED_METHODS, LANGUAGE_MISMATCH, RUNTIME_ERROR."
        ),
    )
    parser.add_argument("--class-name", default="MockClass", help="Class name in synthetic snapshot")
    parser.add_argument("--method-name", default="mockMethod", help="Method name in synthetic snapshot")
    parser.add_argument(
        "--file-path", default="MockClass.java", help="File path in synthetic snapshot attributes"
    )
    parser.add_argument(
        "--code-unit", default="com.amazon.test", help="Code unit (Java package) in synthetic snapshot"
    )
    parser.add_argument(
        "--region", default=None, help="AWS region (defaults to AWS_REGION env or us-east-1)"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Only print final JSON summary; suppress info logs"
    )
    args = parser.parse_args(argv)

    if not args.quiet:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    region = args.region or _resolve_region()

    if args.region:
        os.environ["AWS_REGION"] = args.region
    appsignals = get_application_signals_client()
    logs = boto3.client("logs", region_name=region)

    summary: dict = {
        "service": args.service,
        "environment": args.environment,
        "location_hash": args.location_hash,
        "region": region,
    }

    statuses = [s.strip() for s in args.statuses.split(",") if s.strip()]
    if statuses:
        submitted = _report_status_events(
            appsignals, args.service, args.environment, args.location_hash, statuses
        )
        summary["status_events_reported"] = submitted
    else:
        summary["status_events_reported"] = []

    if args.snapshots > 0:
        timestamps_ms = _emit_snapshots(
            logs,
            args.service,
            args.environment,
            args.location_hash,
            args.snapshots,
            args.class_name,
            args.method_name,
            args.file_path,
            args.code_unit,
        )
        summary["snapshots_emitted"] = args.snapshots
        # Anchor timestamp the e2e test should pass to snapshot query tools (status_timestamp)
        anchor_dt = datetime.fromtimestamp(timestamps_ms[0] / 1000, tz=timezone.utc)
        summary["snapshot_anchor_timestamp"] = anchor_dt.isoformat().replace("+00:00", "Z")
        summary["snapshot_timestamps_ms"] = timestamps_ms
    else:
        summary["snapshots_emitted"] = 0

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
