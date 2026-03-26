---
name: cloud-logs
description: Query and filter Google Cloud Logging entries using the cloud_logs.py tool. Use when users ask about GCP logs, Cloud Logging, Kubernetes/GKE pod logs, Cloud Run logs, audit logs, error investigation, or need to search/export log entries. Triggers on requests like "show me recent errors", "check pod logs", "search logs for timeout", "list available logs", "audit log activity", or any Google Cloud Logging queries.
---

# Cloud Logs

Query GCP Cloud Logging API using the bundled `cloud_logs.py` script.

## Prerequisites

Requires GCP authentication. Verify with:
```bash
gcloud auth application-default print-access-token
```

If not authenticated:
```bash
gcloud auth application-default login
```

## Quick Reference

```bash
# Run with uv (handles dependencies automatically)
uv run scripts/cloud_logs.py <command> [options]

# Commands
query       # Query log entries
list        # List available log names
resources   # List resource types with recent logs
```

## Common Workflows

### Find recent errors

```bash
# Errors in the last hour
uv run scripts/cloud_logs.py query -p PROJECT --severity ERROR

# Critical errors in the last 6 hours
uv run scripts/cloud_logs.py query -p PROJECT --severity CRITICAL -d 6h -n 50
```

### Search logs by text

```bash
# Search for specific text across all log types
uv run scripts/cloud_logs.py query -p PROJECT --text "connection refused" -d 6h

# Search with severity filter
uv run scripts/cloud_logs.py query -p PROJECT --text "timeout" --severity WARNING
```

### Filter by labels

```bash
# By k8s pod label (keys without / auto-prefix k8s-pod/)
uv run scripts/cloud_logs.py query -p PROJECT -r k8s_container -l app=httpbin

# By resource label (namespace, cluster, pod name, etc.)
uv run scripts/cloud_logs.py query -p PROJECT -r k8s_container \
  --resource-label namespace_name=production

# By JSON payload field
uv run scripts/cloud_logs.py query -p PROJECT --payload-field level=error

# Combine multiple label filters
uv run scripts/cloud_logs.py query -p PROJECT -r k8s_container \
  -l app=myapp --resource-label namespace_name=production --severity ERROR

# Entry label with full key (contains /, used as-is)
uv run scripts/cloud_logs.py query -p PROJECT \
  -l logging.gke.io/top_level_controller_name=my-deployment
```

### GKE / Kubernetes logs

```bash
# All container logs for a namespace
uv run scripts/cloud_logs.py query -p PROJECT -r k8s_container \
  --resource-label namespace_name=production

# Specific pod logs
uv run scripts/cloud_logs.py query -p PROJECT -r k8s_container \
  --resource-label pod_name=my-pod-abc123 -d 30m

# By app label
uv run scripts/cloud_logs.py query -p PROJECT -r k8s_container -l app=myapp

# Node logs
uv run scripts/cloud_logs.py query -p PROJECT -r k8s_node -d 1h
```

### Cloud Run logs

```bash
# Cloud Run service logs
uv run scripts/cloud_logs.py query -p PROJECT -r cloud_run_revision \
  --resource-label service_name=my-service

# Cloud Run errors only
uv run scripts/cloud_logs.py query -p PROJECT -r cloud_run_revision \
  --severity ERROR -d 1h
```

### Audit logs

```bash
# Admin activity audit logs
uv run scripts/cloud_logs.py query -p PROJECT \
  -f 'logName:"cloudaudit.googleapis.com%2Factivity"' -d 24h

# Data access audit logs
uv run scripts/cloud_logs.py query -p PROJECT \
  -f 'logName:"cloudaudit.googleapis.com%2Fdata_access"' -d 24h
```

### Explore available logs

```bash
# List all log names in the project
uv run scripts/cloud_logs.py list -p PROJECT

# List resource types that have recent logs
uv run scripts/cloud_logs.py resources -p PROJECT
```

### Export data

```bash
# JSON output (for jq processing)
uv run scripts/cloud_logs.py query -p PROJECT --severity ERROR -o json | \
  jq '.[] | select(.message | contains("timeout"))'

# CSV output
uv run scripts/cloud_logs.py query -p PROJECT --severity ERROR -o csv > errors.csv
```

## Key Options

| Option | Description |
|--------|-------------|
| `-p, --project` | GCP project ID (required) |
| `-s, --severity` | Minimum severity: DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL, ALERT, EMERGENCY |
| `-r, --resource-type` | Resource type: `k8s_container`, `cloud_run_revision`, `gce_instance`, etc. |
| `-t, --text` | Search text in log payloads |
| `-f, --filter` | Raw filter expression (repeatable) |
| `-l, --label` | Entry label filter `key=value`. Keys without `/` auto-prefix `k8s-pod/` (repeatable) |
| `--resource-label` | Resource label filter `key=value`, e.g. `namespace_name=prod` (repeatable) |
| `--payload-field` | JSON payload field filter `key=value`, e.g. `level=error` (repeatable) |
| `-d, --duration` | Time range: `30m`, `1h`, `7d` (default: 1h) |
| `--start` / `--end` | Absolute time range (ISO format) |
| `-n, --limit` | Max entries to return (default: 100) |
| `--order` | `asc` or `desc` (default: desc, newest first) |
| `--labels` | Show resource/entry labels in table output |
| `-o, --output` | `table` (default), `json`, `csv` |

## Common Resource Types

| Resource Type | Description |
|---------------|-------------|
| `k8s_container` | GKE container (pod) logs |
| `k8s_node` | GKE node logs |
| `k8s_cluster` | GKE cluster-level logs |
| `cloud_run_revision` | Cloud Run revision logs |
| `cloud_function` | Cloud Functions logs |
| `gce_instance` | Compute Engine VM logs |
| `gae_app` | App Engine logs |
| `cloud_sql_database` | Cloud SQL logs |
