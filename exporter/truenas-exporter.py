#!/usr/bin/env python3
"""
TrueNAS Exporter - Prometheus metrics for TrueNAS health monitoring

A standalone Python exporter that scrapes TrueNAS APIs and exposes
Prometheus-compatible metrics for monitoring:

Replication metrics:
- truenas_replication_up: 1 if API is reachable
- truenas_replication_state: Task state (1=FINISHED, 0.5=RUNNING, 0=PENDING, -1=ERROR)
- truenas_replication_last_run_timestamp: Unix timestamp of last run
- truenas_replication_age_seconds: Seconds since last successful run
- truenas_replication_expected_interval_seconds: Expected interval from schedule
- truenas_replication_info: Metadata labels (direction, transport, last_snapshot)

App metrics:
- truenas_app_state: App state (1=RUNNING, 0.5=DEPLOYING, 0=STOPPED, -1=CRASHED)
- truenas_app_info: App metadata (version, train)

VM metrics:
- truenas_vm_state: VM state (1=RUNNING, 0=STOPPED, -1=ERROR)
- truenas_vm_info: VM metadata (vcpus, memory)

Incus instance metrics (TrueNAS 25.04+):
- truenas_virt_state: Instance state (1=RUNNING, 0=STOPPED, -1=ERROR)
- truenas_virt_info: Instance metadata (type, cpu, memory)

Usage:
    ./truenas-exporter.py --config /etc/truenas-exporter/config.yaml
    ./truenas-exporter.py --config config.yaml --port 9814

Repository: https://github.com/levlaz/truenas-grafana
License: MIT
"""

import argparse
import json
import logging
import os
import re
import ssl
import sys
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.error import URLError, HTTPError

__version__ = "1.0.0"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# State mapping for replication metrics
REPLICATION_STATE_MAP = {
    "FINISHED": 1,
    "SUCCESS": 1,
    "RUNNING": 0.5,
    "PENDING": 0,
    "WAITING": 0,
    "ERROR": -1,
    "FAILED": -1,
}

# State mapping for app metrics
APP_STATE_MAP = {
    "RUNNING": 1,
    "ACTIVE": 1,
    "DEPLOYING": 0.5,
    "STOPPED": 0,
    "CRASHED": -1,
}

# State mapping for VM metrics
VM_STATE_MAP = {
    "RUNNING": 1,
    "STOPPED": 0,
    "ERROR": -1,
}

# State mapping for Incus instance metrics (virt/instance API)
VIRT_STATE_MAP = {
    "RUNNING": 1,
    "STOPPED": 0,
    "FROZEN": 0,
    "ERROR": -1,
}


def parse_yaml_simple(content):
    """
    Simple YAML parser for config files.
    Supports basic structures: scalars, lists, and nested dicts.
    No external dependencies required.
    """
    result = {}
    current_list = None
    current_list_key = None
    current_dict = None
    indent_stack = [(0, result)]

    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # Calculate indentation
        indent = len(line) - len(line.lstrip())

        # Pop stack to find correct parent
        while len(indent_stack) > 1 and indent <= indent_stack[-1][0]:
            indent_stack.pop()

        current_parent = indent_stack[-1][1]

        # Handle list items
        if stripped.startswith("- "):
            item_content = stripped[2:].strip()

            # Check if parent key exists for this list
            if current_list_key and current_list_key in current_parent:
                target_list = current_parent[current_list_key]
            else:
                # Find the last key that was set
                if isinstance(current_parent, dict):
                    keys = list(current_parent.keys())
                    if keys:
                        last_key = keys[-1]
                        if not isinstance(current_parent[last_key], list):
                            current_parent[last_key] = []
                        target_list = current_parent[last_key]
                        current_list_key = last_key
                    else:
                        i += 1
                        continue
                else:
                    i += 1
                    continue

            # Parse the list item
            if ":" in item_content:
                # It's a dict item in the list
                item_dict = {}
                # Parse first key-value
                key, _, value = item_content.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value:
                    # Handle boolean
                    if value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    item_dict[key] = value
                else:
                    item_dict[key] = None

                # Look ahead for more keys at same indent + 2
                j = i + 1
                item_indent = indent + 2
                while j < len(lines):
                    next_line = lines[j]
                    next_stripped = next_line.strip()
                    if not next_stripped or next_stripped.startswith("#"):
                        j += 1
                        continue
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent < item_indent or next_stripped.startswith("- "):
                        break
                    if ":" in next_stripped:
                        k, _, v = next_stripped.partition(":")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if v.lower() == "true":
                            v = True
                        elif v.lower() == "false":
                            v = False
                        elif v.isdigit():
                            v = int(v)
                        item_dict[k] = v
                    j += 1
                target_list.append(item_dict)
                i = j
                continue
            else:
                # Simple scalar in list
                target_list.append(item_content.strip('"').strip("'"))
                i += 1
                continue

        # Handle key: value pairs
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()

            if value:
                # Scalar value
                value = value.strip('"').strip("'")
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                current_parent[key] = value
                current_list_key = None
            else:
                # Could be a list or nested dict
                # Look ahead to determine
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    next_stripped = next_line.strip()
                    if next_stripped.startswith("- "):
                        # It's a list
                        current_parent[key] = []
                        current_list_key = key
                    else:
                        # It's a nested dict
                        current_parent[key] = {}
                        indent_stack.append((indent + 2, current_parent[key]))
                        current_list_key = None
                else:
                    current_parent[key] = None

        i += 1

    return result


def load_config(config_path):
    """Load configuration from YAML file."""
    try:
        with open(config_path, "r") as f:
            content = f.read()
        config = parse_yaml_simple(content)
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        sys.exit(1)


def fetch_api(target, endpoint):
    """Fetch data from TrueNAS API endpoint."""
    url = f"{target['api_url']}/api/v2.0/{endpoint}"

    # Create SSL context
    ssl_context = ssl.create_default_context()
    if not target.get("verify_ssl", False):
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {target['api_token']}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except (URLError, HTTPError) as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


def fetch_replication_tasks(target):
    """Fetch replication tasks from TrueNAS API."""
    return fetch_api(target, "replication")


def fetch_apps(target):
    """Fetch apps from TrueNAS API."""
    return fetch_api(target, "app")


def fetch_vms(target):
    """Fetch VMs from TrueNAS API."""
    return fetch_api(target, "vm")


def fetch_virt_instances(target):
    """Fetch Incus containers/VMs from TrueNAS 25.04+ API."""
    return fetch_api(target, "virt/instance")


def parse_cron_to_seconds(schedule):
    """
    Parse TrueNAS schedule to expected interval in seconds.
    Returns None if cannot determine interval.

    Schedule format from API:
    {
        "minute": "0",
        "hour": "*",
        "dom": "*",
        "month": "*",
        "dow": "*"
    }
    """
    if not schedule:
        return None

    minute = schedule.get("minute", "*")
    hour = schedule.get("hour", "*")
    dom = schedule.get("dom", "*")
    dow = schedule.get("dow", "*")

    # Every N minutes: */N
    if isinstance(minute, str) and minute.startswith("*/"):
        try:
            return int(minute[2:]) * 60
        except ValueError:
            pass

    # Hourly: minute is fixed, hour is *
    if minute != "*" and hour == "*" and dom == "*":
        return 3600  # 1 hour

    # Daily: hour is fixed, dom is *
    if hour != "*" and dom == "*" and dow == "*":
        return 86400  # 24 hours

    # Weekly: dow is fixed
    if dow != "*":
        return 604800  # 7 days

    # Default: assume daily if cannot parse
    return 86400


def escape_label_value(value):
    """Escape special characters in Prometheus label values."""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def generate_replication_metrics(targets):
    """Generate Prometheus metrics for replication tasks."""
    lines = []

    # Help and type declarations
    lines.append("# HELP truenas_replication_up 1 if TrueNAS API is reachable")
    lines.append("# TYPE truenas_replication_up gauge")
    lines.append("# HELP truenas_replication_state Replication task state (1=FINISHED, 0.5=RUNNING, 0=PENDING, -1=ERROR)")
    lines.append("# TYPE truenas_replication_state gauge")
    lines.append("# HELP truenas_replication_last_run_timestamp Unix timestamp of last replication run")
    lines.append("# TYPE truenas_replication_last_run_timestamp gauge")
    lines.append("# HELP truenas_replication_age_seconds Seconds since last replication run")
    lines.append("# TYPE truenas_replication_age_seconds gauge")
    lines.append("# HELP truenas_replication_expected_interval_seconds Expected interval between replications based on schedule")
    lines.append("# TYPE truenas_replication_expected_interval_seconds gauge")
    lines.append("# HELP truenas_replication_info Replication task metadata")
    lines.append("# TYPE truenas_replication_info gauge")

    now = time.time()

    for target in targets:
        host = escape_label_value(target["name"])
        tasks, error = fetch_replication_tasks(target)

        if error:
            # API unreachable
            lines.append(f'truenas_replication_up{{host="{host}"}} 0')
            logger.warning(f"Failed to fetch replication tasks from {host}: {error}")
            continue

        lines.append(f'truenas_replication_up{{host="{host}"}} 1')

        for task in tasks:
            task_name = escape_label_value(task.get("name", "unknown"))
            task_id = task.get("id", 0)
            direction = escape_label_value(task.get("direction", "UNKNOWN"))
            transport = escape_label_value(task.get("transport", "UNKNOWN"))
            enabled = task.get("enabled", False)

            # Skip disabled tasks
            if not enabled:
                continue

            # Get state info
            state_info = task.get("state", {}) or {}
            state = state_info.get("state", "UNKNOWN")
            state_value = REPLICATION_STATE_MAP.get(state, -1)

            # Get last run timestamp (milliseconds to seconds)
            datetime_info = state_info.get("datetime", {}) or {}
            last_run_ms = datetime_info.get("$date", 0)
            last_run_ts = last_run_ms / 1000 if last_run_ms else 0

            # Calculate age
            age_seconds = now - last_run_ts if last_run_ts > 0 else -1

            # Get last snapshot
            last_snapshot = escape_label_value(state_info.get("last_snapshot", "none") or "none")

            # Get source datasets for labeling
            source_datasets = task.get("source_datasets", [])
            source = escape_label_value(",".join(source_datasets) if source_datasets else "unknown")
            target_dataset = escape_label_value(task.get("target_dataset", "unknown"))

            # Get expected interval from periodic snapshot tasks
            periodic_tasks = task.get("periodic_snapshot_tasks", [])
            expected_interval = None
            for pt in periodic_tasks:
                schedule = pt.get("schedule", {})
                interval = parse_cron_to_seconds(schedule)
                if interval:
                    if expected_interval is None or interval < expected_interval:
                        expected_interval = interval

            # If no periodic tasks, try to get from task's own schedule
            if expected_interval is None:
                task_schedule = task.get("schedule", {})
                expected_interval = parse_cron_to_seconds(task_schedule)

            # Default to daily if still unknown
            if expected_interval is None:
                expected_interval = 86400

            # Common labels
            labels = f'host="{host}",task_name="{task_name}",task_id="{task_id}"'

            # Emit metrics
            lines.append(f"truenas_replication_state{{{labels}}} {state_value}")
            lines.append(f"truenas_replication_last_run_timestamp{{{labels}}} {last_run_ts}")
            lines.append(f"truenas_replication_age_seconds{{{labels}}} {age_seconds}")
            lines.append(f"truenas_replication_expected_interval_seconds{{{labels}}} {expected_interval}")

            # Info metric with additional labels
            info_labels = f'{labels},direction="{direction}",transport="{transport}",source="{source}",target="{target_dataset}",last_snapshot="{last_snapshot}"'
            lines.append(f"truenas_replication_info{{{info_labels}}} 1")

    return lines


def generate_app_metrics(targets):
    """Generate Prometheus metrics for TrueNAS apps."""
    lines = []

    # Help and type declarations
    lines.append("# HELP truenas_app_state App state (1=RUNNING, 0.5=DEPLOYING, 0=STOPPED, -1=CRASHED)")
    lines.append("# TYPE truenas_app_state gauge")
    lines.append("# HELP truenas_app_info App metadata")
    lines.append("# TYPE truenas_app_info gauge")

    for target in targets:
        host = escape_label_value(target["name"])
        apps, error = fetch_apps(target)

        if error or apps is None:
            # API error - skip apps for this host
            continue

        for app in apps:
            app_name = escape_label_value(app.get("name", "unknown"))
            state = app.get("state", "UNKNOWN").upper()
            state_value = APP_STATE_MAP.get(state, -1)

            # Get app metadata
            version = escape_label_value(app.get("version", "unknown"))
            train = escape_label_value(app.get("metadata", {}).get("train", "unknown"))

            # Common labels
            labels = f'host="{host}",app="{app_name}"'

            # Emit metrics
            lines.append(f"truenas_app_state{{{labels}}} {state_value}")

            # Info metric with additional labels
            info_labels = f'{labels},version="{version}",train="{train}"'
            lines.append(f"truenas_app_info{{{info_labels}}} 1")

    return lines


def generate_vm_metrics(targets):
    """Generate Prometheus metrics for TrueNAS VMs."""
    lines = []

    # Help and type declarations
    lines.append("# HELP truenas_vm_state VM state (1=RUNNING, 0=STOPPED, -1=ERROR)")
    lines.append("# TYPE truenas_vm_state gauge")
    lines.append("# HELP truenas_vm_info VM metadata")
    lines.append("# TYPE truenas_vm_info gauge")

    for target in targets:
        host = escape_label_value(target["name"])
        vms, error = fetch_vms(target)

        if error or vms is None:
            # API error - skip VMs for this host
            continue

        for vm in vms:
            vm_name = escape_label_value(vm.get("name", "unknown"))
            vm_id = vm.get("id", 0)

            # Get VM status
            status = vm.get("status", {}) or {}
            state = status.get("state", "UNKNOWN").upper()
            state_value = VM_STATE_MAP.get(state, -1)

            # Get VM specs
            vcpus = vm.get("vcpus", 0)
            memory = vm.get("memory", 0)  # in MB
            autostart = vm.get("autostart", False)

            # Common labels
            labels = f'host="{host}",vm="{vm_name}",vm_id="{vm_id}"'

            # Emit metrics
            lines.append(f"truenas_vm_state{{{labels}}} {state_value}")

            # Info metric with additional labels
            autostart_str = "true" if autostart else "false"
            info_labels = f'{labels},vcpus="{vcpus}",memory_mb="{memory}",autostart="{autostart_str}"'
            lines.append(f"truenas_vm_info{{{info_labels}}} 1")

    return lines


def generate_virt_metrics(targets):
    """Generate Prometheus metrics for TrueNAS Incus instances (containers/VMs)."""
    lines = []

    # Help and type declarations
    lines.append("# HELP truenas_virt_state Incus instance state (1=RUNNING, 0=STOPPED, -1=ERROR)")
    lines.append("# TYPE truenas_virt_state gauge")
    lines.append("# HELP truenas_virt_info Incus instance metadata")
    lines.append("# TYPE truenas_virt_info gauge")

    for target in targets:
        host = escape_label_value(target["name"])
        instances, error = fetch_virt_instances(target)

        if error or instances is None:
            # API error or not available (older TrueNAS) - skip
            continue

        for inst in instances:
            inst_name = escape_label_value(inst.get("name", "unknown"))
            inst_id = escape_label_value(inst.get("id", "unknown"))
            inst_type = escape_label_value(inst.get("type", "CONTAINER"))  # CONTAINER or VM

            # Get instance status
            state = inst.get("status", "UNKNOWN").upper()
            state_value = VIRT_STATE_MAP.get(state, -1)

            # Get instance specs
            cpu = inst.get("cpu", "")
            memory = inst.get("memory", 0)  # in bytes
            memory_mb = memory // (1024 * 1024) if memory else 0
            autostart = inst.get("autostart", False)

            # Common labels
            labels = f'host="{host}",instance="{inst_name}",instance_id="{inst_id}",type="{inst_type}"'

            # Emit metrics
            lines.append(f"truenas_virt_state{{{labels}}} {state_value}")

            # Info metric with additional labels
            autostart_str = "true" if autostart else "false"
            info_labels = f'{labels},cpu="{cpu}",memory_mb="{memory_mb}",autostart="{autostart_str}"'
            lines.append(f"truenas_virt_info{{{info_labels}}} 1")

    return lines


def generate_metrics(targets):
    """Generate all Prometheus metrics."""
    lines = []
    lines.extend(generate_replication_metrics(targets))
    lines.extend(generate_app_metrics(targets))
    lines.extend(generate_vm_metrics(targets))
    lines.extend(generate_virt_metrics(targets))
    return "\n".join(lines) + "\n"


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Prometheus metrics endpoint."""

    def __init__(self, targets, *args, **kwargs):
        self.targets = targets
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/metrics":
            metrics = generate_metrics(self.targets)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(metrics.encode("utf-8"))
        elif self.path == "/health" or self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        elif self.path == "/":
            # Landing page with links
            html = f"""<!DOCTYPE html>
<html>
<head><title>TrueNAS Exporter</title></head>
<body>
<h1>TrueNAS Exporter v{__version__}</h1>
<p><a href="/metrics">Metrics</a></p>
<p><a href="/health">Health Check</a></p>
<p>Monitoring {len(self.targets)} TrueNAS host(s)</p>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Use our logger instead of stderr
        logger.debug(f"{self.address_string()} - {format % args}")


def create_handler(targets):
    """Create a handler class with targets bound."""
    def handler(*args, **kwargs):
        MetricsHandler(targets, *args, **kwargs)
    return handler


def main():
    parser = argparse.ArgumentParser(
        description="TrueNAS Exporter - Prometheus metrics for TrueNAS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --config /etc/truenas-exporter/config.yaml
  %(prog)s --config config.yaml --port 9814
  %(prog)s --config config.yaml --debug

Repository: https://github.com/levlaz/truenas-grafana
        """,
    )
    parser.add_argument(
        "--config", "-c",
        required=True,
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="Port to listen on (overrides config file)",
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load configuration
    config = load_config(args.config)

    # Get targets
    targets = config.get("targets", [])
    if not targets:
        logger.error("No targets configured in config file")
        sys.exit(1)

    # Determine port
    port = args.port or config.get("listen_port", 9814)

    # Create handler with targets
    handler_class = type(
        "BoundMetricsHandler",
        (MetricsHandler,),
        {"__init__": lambda self, *a, **kw: MetricsHandler.__init__(self, targets, *a, **kw)},
    )

    # Start server
    server = HTTPServer(("0.0.0.0", port), handler_class)
    logger.info(f"TrueNAS Exporter v{__version__} listening on port {port}")
    logger.info(f"Monitoring {len(targets)} TrueNAS host(s): {', '.join(t['name'] for t in targets)}")
    logger.info(f"Metrics available at http://localhost:{port}/metrics")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
