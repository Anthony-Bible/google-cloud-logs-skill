# Cloud Logs Skill for Claude Code

A Claude Code skill that enables querying Google Cloud Logging entries directly from your terminal. Search logs, investigate errors, filter by labels, and export log data across GKE, Cloud Run, Compute Engine, and other GCP services with natural language.

## Features

- **Query logs** - Fetch log entries with severity, text, label, and resource filters
- **List log names** - Discover available log names in your GCP project
- **List resource types** - Browse resource types that have recent log entries
- **Label filtering** - Filter by entry labels, resource labels, and JSON payload fields
- **Multiple output formats** - Table, JSON, or CSV output
- **Flexible time ranges** - Duration strings (`1h`, `30m`, `7d`) or ISO timestamps

## Prerequisites

1. **Python 3.10+** installed
2. **[uv](https://docs.astral.sh/uv/)** installed (handles dependencies automatically)
3. **Google Cloud SDK** (`gcloud`) installed
4. **GCP Project** with Cloud Logging API enabled
5. **IAM Permissions** to read Cloud Logging entries (e.g., `roles/logging.viewer`)

### Authentication

Configure application default credentials:

```bash
gcloud auth application-default login
```

Verify with:

```bash
gcloud auth application-default print-access-token
```

## Installation

This skill is distributed as a self-contained directory. Install it so Claude Code can discover and use it.

### Option 1: Clone Directly into Skills (Recommended)

Install globally for all projects:

```bash
git clone git@github.com:Anthony-Bible/google-cloud-logs-skill.git ~/.claude/skills/cloud-logs
```

Or for a specific project:

```bash
git clone git@github.com:Anthony-Bible/google-cloud-logs-skill.git .claude/skills/cloud-logs
```

This makes it easy to pull updates later with `git -C ~/.claude/skills/cloud-logs pull`.

### Option 2: Copy from an Existing Clone

If you already have the repo cloned:

```bash
# User-level (all projects)
mkdir -p ~/.claude/skills
cp -r /path/to/cloud-logs ~/.claude/skills/

# Or project-level
mkdir -p .claude/skills
cp -r /path/to/cloud-logs .claude/skills/
```

The skill directory contains:
- `scripts/cloud_logs.py` - The Python script for querying logs
- `SKILL.md` - Skill metadata and usage reference (used by Claude Code)

That's it! No additional configuration needed — `SKILL.md` is already included.

## Usage

Once installed, just ask Claude Code about GCP logs:

```
> Show me recent errors in project my-gcp-project

> Check pod logs for the production namespace

> Search logs for "connection refused" in the last 6 hours

> List available log names in my project

> Show Cloud Run errors for my-service
```

## Command Reference

### `query` - Query log entries

```bash
uv run scripts/cloud_logs.py query -p PROJECT [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-p, --project` | GCP project ID (required) |
| `-s, --severity` | Minimum severity: `DEBUG`, `INFO`, `NOTICE`, `WARNING`, `ERROR`, `CRITICAL`, `ALERT`, `EMERGENCY` |
| `-r, --resource-type` | Resource type: `k8s_container`, `cloud_run_revision`, `gce_instance`, etc. |
| `-t, --text` | Search text in log payloads |
| `-f, --filter` | Raw Cloud Logging filter expression (repeatable) |
| `-l, --label` | Entry label filter `key=value` — keys without `/` auto-prefix `k8s-pod/` (repeatable) |
| `--resource-label` | Resource label filter `key=value`, e.g., `namespace_name=prod` (repeatable) |
| `--payload-field` | JSON payload field filter `key=value`, e.g., `level=error` (repeatable) |
| `-d, --duration` | Time range: `30m`, `1h`, `7d` (default: `1h`) |
| `--start` / `--end` | Absolute time range (ISO format) |
| `-n, --limit` | Max entries to return (default: 100) |
| `--order` | `asc` or `desc` (default: `desc`, newest first) |
| `--labels` | Show resource/entry labels in table output |
| `-o, --output` | `table` (default), `json`, `csv` |

### `list` - List available log names

```bash
uv run scripts/cloud_logs.py list -p PROJECT
```

### `resources` - List resource types with recent logs

```bash
uv run scripts/cloud_logs.py resources -p PROJECT
```

## Examples

### Find recent errors

```bash
# Errors in the last hour
uv run scripts/cloud_logs.py query -p my-project --severity ERROR

# Critical errors in the last 6 hours
uv run scripts/cloud_logs.py query -p my-project --severity CRITICAL -d 6h -n 50
```

### Search logs by text

```bash
# Search for specific text
uv run scripts/cloud_logs.py query -p my-project --text "connection refused" -d 6h

# Search with severity filter
uv run scripts/cloud_logs.py query -p my-project --text "timeout" --severity WARNING
```

### GKE / Kubernetes logs

```bash
# All container logs for a namespace
uv run scripts/cloud_logs.py query -p my-project -r k8s_container \
  --resource-label namespace_name=production

# Specific pod logs
uv run scripts/cloud_logs.py query -p my-project -r k8s_container \
  --resource-label pod_name=my-pod-abc123 -d 30m

# By app label
uv run scripts/cloud_logs.py query -p my-project -r k8s_container -l app=myapp
```

### Cloud Run logs

```bash
# Cloud Run service logs
uv run scripts/cloud_logs.py query -p my-project -r cloud_run_revision \
  --resource-label service_name=my-service

# Cloud Run errors only
uv run scripts/cloud_logs.py query -p my-project -r cloud_run_revision \
  --severity ERROR -d 1h
```

### Audit logs

```bash
# Admin activity
uv run scripts/cloud_logs.py query -p my-project \
  -f 'logName:"cloudaudit.googleapis.com%2Factivity"' -d 24h

# Data access
uv run scripts/cloud_logs.py query -p my-project \
  -f 'logName:"cloudaudit.googleapis.com%2Fdata_access"' -d 24h
```

### Export data

```bash
# JSON output (for jq processing)
uv run scripts/cloud_logs.py query -p my-project --severity ERROR -o json | \
  jq '.[] | select(.message | contains("timeout"))'

# CSV output
uv run scripts/cloud_logs.py query -p my-project --severity ERROR -o csv > errors.csv
```

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

## Dependencies

The script uses inline metadata so `uv run` automatically installs dependencies:

- `google-cloud-logging>=3.0.0`

No manual `pip install` required when using `uv run`.

## License

Apache 2.0 License.
