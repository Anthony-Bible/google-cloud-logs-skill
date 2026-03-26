#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "google-cloud-logging>=3.0.0",
# ]
# ///
"""
Google Cloud Logging Query Tool

Query and filter log entries from Google Cloud Logging API.
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Optional


from google.cloud import logging as cloud_logging
from google.cloud.logging_v2 import DESCENDING, ASCENDING
from google.cloud.logging_v2.entries import TextEntry, StructEntry, ProtobufEntry


def parse_duration(duration_str: str) -> timedelta:
    """Parse duration string like '1h', '30m', '7d' into timedelta."""
    unit = duration_str[-1].lower()
    value = int(duration_str[:-1])

    if unit == 'm':
        return timedelta(minutes=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'd':
        return timedelta(days=value)
    else:
        raise ValueError(f"Unknown duration unit: {unit}. Use 'm', 'h', or 'd'")


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO format timestamp string into datetime."""
    ts_str = ts_str.strip()

    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(ts_str.replace("Z", "+0000"), fmt.replace("Z", "%z"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    raise ValueError(f"Unable to parse timestamp: {ts_str}")


SEVERITY_LEVELS = [
    "DEFAULT", "DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY",
]


def parse_label_expr(expr: str) -> tuple[str, str]:
    """Parse a key=value label expression."""
    if "=" not in expr:
        print(f"Invalid label expression: {expr} (expected key=value)", file=sys.stderr)
        sys.exit(1)
    key, value = expr.split("=", 1)
    return key.strip(), value.strip()


def build_filter(
    severity: Optional[str] = None,
    log_name: Optional[str] = None,
    resource_type: Optional[str] = None,
    text_search: Optional[str] = None,
    filters: Optional[list[str]] = None,
    labels: Optional[list[str]] = None,
    resource_labels: Optional[list[str]] = None,
    payload_fields: Optional[list[str]] = None,
    duration: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> str:
    """Build a Cloud Logging filter string from components."""
    parts = []

    # Time range
    now = datetime.now(timezone.utc)
    if start:
        start_time = parse_timestamp(start)
        parts.append(f'timestamp >= "{start_time.isoformat()}"')
        if end:
            end_time = parse_timestamp(end)
            parts.append(f'timestamp <= "{end_time.isoformat()}"')
    else:
        duration = duration or "1h"
        delta = parse_duration(duration)
        start_time = now - delta
        parts.append(f'timestamp >= "{start_time.isoformat()}"')

    # Severity
    if severity:
        sev = severity.upper()
        if sev in SEVERITY_LEVELS:
            parts.append(f"severity >= {sev}")
        else:
            print(f"Unknown severity: {severity}", file=sys.stderr)
            print(f"Available: {', '.join(SEVERITY_LEVELS)}", file=sys.stderr)
            sys.exit(1)

    # Log name
    if log_name:
        parts.append(f'logName="{log_name}"')

    # Resource type
    if resource_type:
        parts.append(f'resource.type="{resource_type}"')

    # Entry labels (--label key=value)
    # Auto-prefix k8s-pod/ if key has no slash (convenience for k8s pod labels)
    if labels:
        for expr in labels:
            key, value = parse_label_expr(expr)
            if "/" not in key:
                key = f"k8s-pod/{key}"
            parts.append(f'labels."{key}"="{value}"')

    # Resource labels (--resource-label key=value)
    if resource_labels:
        for expr in resource_labels:
            key, value = parse_label_expr(expr)
            parts.append(f'resource.labels.{key}="{value}"')

    # JSON payload fields (--payload-field key=value)
    if payload_fields:
        for expr in payload_fields:
            key, value = parse_label_expr(expr)
            parts.append(f'jsonPayload.{key}="{value}"')

    # Text search (use global search which covers all payload types)
    if text_search:
        parts.append(f'"{text_search}"')

    # Raw filter expressions
    if filters:
        parts.extend(filters)

    return "\n".join(parts)


def extract_message(entry) -> str:
    """Extract the log message from an entry."""
    if isinstance(entry, TextEntry):
        return entry.payload or ""
    elif isinstance(entry, StructEntry):
        payload = entry.payload or {}
        if isinstance(payload, dict):
            msg = payload.get("message") or payload.get("msg") or payload.get("textPayload", "")
            if msg:
                return str(msg)
            return json.dumps(payload, default=str)
        return str(payload)
    elif isinstance(entry, ProtobufEntry):
        payload = entry.payload or {}
        if isinstance(payload, dict):
            method = payload.get("methodName", "")
            resource = payload.get("resourceName", "")
            if method:
                return f"{method} {resource}".strip()
            return json.dumps(payload, default=str)
        return str(payload)
    return ""


def extract_labels(entry) -> dict:
    """Extract resource and entry labels."""
    labels = {}
    if entry.resource and entry.resource.labels:
        labels.update(dict(entry.resource.labels))
    if entry.labels:
        labels.update(dict(entry.labels))
    return labels


def entry_to_dict(entry) -> dict:
    """Convert a log entry to a serializable dict."""
    result = {
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else "",
        "severity": entry.severity or "DEFAULT",
        "log_name": entry.log_name or "",
        "resource_type": entry.resource.type if entry.resource else "",
        "message": extract_message(entry),
        "labels": extract_labels(entry),
    }

    if isinstance(entry, StructEntry) and isinstance(entry.payload, dict):
        result["json_payload"] = entry.payload
    elif isinstance(entry, ProtobufEntry) and isinstance(entry.payload, dict):
        result["proto_payload"] = entry.payload

    if entry.http_request:
        result["http_request"] = {
            "method": getattr(entry.http_request, "request_method", ""),
            "url": getattr(entry.http_request, "request_url", ""),
            "status": getattr(entry.http_request, "status", ""),
            "latency": getattr(entry.http_request, "latency", ""),
        }

    if entry.trace:
        result["trace"] = entry.trace
    if entry.span_id:
        result["span_id"] = entry.span_id

    return result


def query_logs(
    project_id: str,
    severity: Optional[str] = None,
    log_name: Optional[str] = None,
    resource_type: Optional[str] = None,
    text_search: Optional[str] = None,
    filters: Optional[list[str]] = None,
    entry_labels: Optional[list[str]] = None,
    resource_labels: Optional[list[str]] = None,
    payload_fields: Optional[list[str]] = None,
    duration: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 100,
    order: str = "desc",
    output_format: str = "table",
    show_labels: bool = False,
) -> None:
    """Query log entries from Cloud Logging."""
    client = cloud_logging.Client(project=project_id)

    filter_str = build_filter(
        severity=severity,
        log_name=log_name,
        resource_type=resource_type,
        text_search=text_search,
        filters=filters,
        labels=entry_labels,
        resource_labels=resource_labels,
        payload_fields=payload_fields,
        duration=duration,
        start=start,
        end=end,
    )

    order_by = DESCENDING if order == "desc" else ASCENDING

    if output_format == "table":
        print(f"Querying logs...", file=sys.stderr)
        print(f"  Project:  {project_id}", file=sys.stderr)
        print(f"  Filter:   {filter_str}", file=sys.stderr)
        print(f"  Limit:    {limit}", file=sys.stderr)
        print(f"  Order:    {order}", file=sys.stderr)
        print("-" * 60, file=sys.stderr)

    try:
        entries = list(client.list_entries(
            filter_=filter_str,
            order_by=order_by,
            max_results=limit,
            resource_names=[f"projects/{project_id}"],
        ))

        if output_format == "json":
            output_json(entries)
        elif output_format == "csv":
            output_csv(entries)
        else:
            output_table(entries, show_labels)

        if output_format == "table":
            print(f"\nTotal: {len(entries)} entries", file=sys.stderr)

    except Exception as e:
        print(f"Error querying logs: {e}", file=sys.stderr)
        sys.exit(1)


def output_json(entries: list) -> None:
    """Output log entries as JSON."""
    output = [entry_to_dict(e) for e in entries]
    print(json.dumps(output, indent=2, default=str))


def output_csv(entries: list) -> None:
    """Output log entries as CSV."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "severity", "resource_type", "log_name", "message"])

    for entry in entries:
        writer.writerow([
            entry.timestamp.isoformat() if entry.timestamp else "",
            entry.severity or "DEFAULT",
            entry.resource.type if entry.resource else "",
            entry.log_name or "",
            extract_message(entry),
        ])

    print(output.getvalue(), end="")


def format_severity(severity: str) -> str:
    """Format severity with fixed width."""
    return (severity or "DEFAULT")[:8].ljust(8)


def output_table(entries: list, show_labels: bool = False) -> None:
    """Output log entries as formatted table."""
    if not entries:
        print("No log entries found matching the query.")
        return

    for entry in entries:
        ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S") if entry.timestamp else "?"
        sev = format_severity(entry.severity)
        resource = entry.resource.type if entry.resource else "?"
        msg = extract_message(entry)

        # Truncate message for table display
        if len(msg) > 200:
            msg = msg[:197] + "..."

        print(f"{ts}  {sev}  [{resource}]  {msg}")

        if show_labels:
            labels = extract_labels(entry)
            if labels:
                label_parts = [f"{k}={v}" for k, v in sorted(labels.items())[:5]]
                print(f"  labels: {', '.join(label_parts)}")


def list_logs(project_id: str, prefix: Optional[str] = None) -> None:
    """List available log names in the project."""
    client = cloud_logging.Client(project=project_id)

    print(f"Listing logs for project: {project_id}", file=sys.stderr)
    if prefix:
        print(f"Filtering by prefix: {prefix}", file=sys.stderr)
    print("-" * 60, file=sys.stderr)

    try:
        count = 0
        for log_name in client.list_entries(
            filter_='timestamp >= "' + (datetime.now(timezone.utc) - timedelta(days=1)).isoformat() + '"',
            max_results=1000,
            resource_names=[f"projects/{project_id}"],
        ):
            pass

        # Use the logging API to list logs
        from google.cloud.logging_v2.services.logging_service_v2 import LoggingServiceV2Client
        log_client = LoggingServiceV2Client()
        logs = log_client.list_logs(parent=f"projects/{project_id}")

        for log_name in logs:
            if prefix and prefix not in log_name:
                continue
            count += 1
            # Extract short name
            short_name = log_name.split("/logs/")[-1] if "/logs/" in log_name else log_name
            print(f"{short_name}")
            print(f"  Full: {log_name}")
            print()

        print(f"Total: {count} logs", file=sys.stderr)

    except Exception as e:
        print(f"Error listing logs: {e}", file=sys.stderr)
        sys.exit(1)


def list_resource_types(project_id: str) -> None:
    """List resource types that have recent log entries."""
    client = cloud_logging.Client(project=project_id)

    print(f"Discovering resource types with recent logs...", file=sys.stderr)
    print("-" * 60, file=sys.stderr)

    try:
        now = datetime.now(timezone.utc)
        filter_str = f'timestamp >= "{(now - timedelta(hours=24)).isoformat()}"'

        entries = client.list_entries(
            filter_=filter_str,
            max_results=500,
            resource_names=[f"projects/{project_id}"],
        )

        resource_types = {}
        for entry in entries:
            rt = entry.resource.type if entry.resource else "unknown"
            if rt not in resource_types:
                resource_types[rt] = {"count": 0, "labels": set()}
            resource_types[rt]["count"] += 1
            if entry.resource and entry.resource.labels:
                resource_types[rt]["labels"].update(entry.resource.labels.keys())

        for rt in sorted(resource_types.keys()):
            info = resource_types[rt]
            print(f"{rt}")
            print(f"  Sample count (last 24h): ~{info['count']}")
            if info["labels"]:
                print(f"  Labels: {', '.join(sorted(info['labels']))}")
            print()

        print(f"Total: {len(resource_types)} resource types", file=sys.stderr)

    except Exception as e:
        print(f"Error listing resource types: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Query Google Cloud Logging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Query recent errors (last hour)
  %(prog)s query -p my-project --severity ERROR

  # Search for text in logs
  %(prog)s query -p my-project --text "connection refused" -d 6h

  # GKE pod logs by k8s label (auto-prefixes k8s-pod/)
  %(prog)s query -p my-project -r k8s_container -l app=httpbin

  # GKE pod logs by namespace (resource label)
  %(prog)s query -p my-project -r k8s_container \\
    --resource-label namespace_name=production

  # Filter by JSON payload field
  %(prog)s query -p my-project --payload-field level=error

  # Combine label filters
  %(prog)s query -p my-project -r k8s_container \\
    -l app=myapp --resource-label namespace_name=production --severity ERROR

  # Entry label with full key (contains /)
  %(prog)s query -p my-project \\
    -l logging.gke.io/top_level_controller_name=my-deployment

  # Cloud Run request logs
  %(prog)s query -p my-project --resource-type cloud_run_revision \\
    --severity WARNING -d 30m

  # Audit logs
  %(prog)s query -p my-project \\
    -f 'logName:"cloudaudit.googleapis.com"' -d 24h

  # JSON output for jq processing
  %(prog)s query -p my-project --severity ERROR -o json | \\
    jq '.[] | select(.message | contains("timeout"))'

  # CSV export
  %(prog)s query -p my-project --severity ERROR -o csv > errors.csv

  # List available logs
  %(prog)s list -p my-project

  # List resource types with recent logs
  %(prog)s resources -p my-project
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Query command
    query_parser = subparsers.add_parser("query", help="Query log entries")
    query_parser.add_argument(
        "-p", "--project", required=True,
        help="GCP project ID",
    )
    query_parser.add_argument(
        "--severity", "-s",
        help="Minimum severity level: DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL, ALERT, EMERGENCY",
    )
    query_parser.add_argument(
        "--log-name",
        help='Full log name (e.g., projects/my-project/logs/cloudaudit.googleapis.com%%2Factivity)',
    )
    query_parser.add_argument(
        "--resource-type", "-r",
        help="Resource type (e.g., k8s_container, cloud_run_revision, gce_instance)",
    )
    query_parser.add_argument(
        "--text", "-t",
        help="Search text in log payloads",
    )
    query_parser.add_argument(
        "-f", "--filter", action="append", dest="filters",
        help="Raw filter expression (can be specified multiple times)",
    )

    # Label filter options
    label_group = query_parser.add_argument_group("label filters")
    label_group.add_argument(
        "-l", "--label", action="append", dest="entry_labels",
        help="Entry label filter as key=value. Keys without / are auto-prefixed with k8s-pod/ (repeatable)",
    )
    label_group.add_argument(
        "--resource-label", action="append", dest="resource_labels",
        help="Resource label filter as key=value, e.g. namespace_name=production (repeatable)",
    )
    label_group.add_argument(
        "--payload-field", action="append", dest="payload_fields",
        help="JSON payload field filter as key=value, e.g. level=error (repeatable)",
    )

    # Time options
    time_group = query_parser.add_argument_group("time options")
    time_group.add_argument(
        "-d", "--duration", default=None,
        help="Time range (e.g., 30m, 1h, 7d). Default: 1h",
    )
    time_group.add_argument(
        "--start",
        help="Start time in ISO format",
    )
    time_group.add_argument(
        "--end",
        help="End time in ISO format (defaults to now)",
    )

    # Output options
    out_group = query_parser.add_argument_group("output options")
    out_group.add_argument(
        "-o", "--output", choices=["table", "json", "csv"], default="table",
        help="Output format. Default: table",
    )
    out_group.add_argument(
        "-n", "--limit", type=int, default=100,
        help="Maximum number of entries to return. Default: 100",
    )
    out_group.add_argument(
        "--order", choices=["asc", "desc"], default="desc",
        help="Sort order by timestamp. Default: desc (newest first)",
    )
    out_group.add_argument(
        "--labels", action="store_true",
        help="Show resource and entry labels in table output",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List available log names")
    list_parser.add_argument(
        "-p", "--project", required=True,
        help="GCP project ID",
    )
    list_parser.add_argument(
        "--prefix",
        help="Filter logs containing this string",
    )

    # Resources command
    res_parser = subparsers.add_parser("resources", help="List resource types with recent logs")
    res_parser.add_argument(
        "-p", "--project", required=True,
        help="GCP project ID",
    )

    args = parser.parse_args()

    if args.command == "query":
        query_logs(
            project_id=args.project,
            severity=args.severity,
            log_name=args.log_name,
            resource_type=args.resource_type,
            text_search=args.text,
            filters=args.filters,
            entry_labels=args.entry_labels,
            resource_labels=args.resource_labels,
            payload_fields=args.payload_fields,
            duration=args.duration,
            start=args.start,
            end=args.end,
            limit=args.limit,
            order=args.order,
            output_format=args.output,
            show_labels=args.labels,
        )
    elif args.command == "list":
        list_logs(
            project_id=args.project,
            prefix=args.prefix,
        )
    elif args.command == "resources":
        list_resource_types(
            project_id=args.project,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
