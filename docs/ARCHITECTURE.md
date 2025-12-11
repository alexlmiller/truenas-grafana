# Architecture

This document describes how the TrueNAS monitoring components work together.

## Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              TrueNAS System                                │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  REST API    │  │   Graphite   │  │   Syslog     │  │   SNMP       │   │
│  │  Port 443    │  │  (outbound)  │  │  (outbound)  │  │  (optional)  │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────────────┘   │
│         │                 │                 │                              │
└─────────┼─────────────────┼─────────────────┼──────────────────────────────┘
          │                 │                 │
          │ HTTPS           │ TCP:2003        │ UDP:6514
          │                 │                 │
          ▼                 ▼                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          Monitoring Server                                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐     │
│  │ truenas-exporter │    │ graphite_exporter│    │   Grafana Alloy  │     │
│  │    Port 9814     │    │ 2003→9108        │    │    Port 6514     │     │
│  │                  │    │                  │    │                  │     │
│  │ Metrics:         │    │ Metrics:         │    │ Forwards to:     │     │
│  │ - Replication    │    │ - CPU/Memory     │    │ - VictoriaLogs   │     │
│  │ - Apps           │    │ - Disk I/O       │    │ - Loki           │     │
│  │ - VMs            │    │ - Network        │    │                  │     │
│  │ - Incus          │    │ - UPS            │    │                  │     │
│  └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘     │
│           │                       │                       │                │
│           │ :9814/metrics         │ :9108/metrics         │                │
│           │                       │                       │                │
│           ▼                       ▼                       ▼                │
│  ┌────────────────────────────────────────────┐  ┌──────────────────┐     │
│  │              Prometheus / VictoriaMetrics  │  │  VictoriaLogs    │     │
│  │                    Port 9090 / 8428        │  │   Port 9428      │     │
│  │                                            │  │                  │     │
│  │  - Scrapes metrics every 15s              │  │  - Stores logs   │     │
│  │  - Evaluates alert rules                  │  │  - Loki-compat   │     │
│  │  - Long-term storage                      │  │  - 4 week retain │     │
│  └────────────────────┬───────────────────────┘  └────────┬─────────┘     │
│                       │                                    │               │
│                       │ Query                              │ Query         │
│                       ▼                                    ▼               │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                           Grafana                                    │  │
│  │                          Port 3000                                   │  │
│  │                                                                      │  │
│  │  ┌─────────────────────────────────────────────────────────────┐    │  │
│  │  │                   TrueNAS Overview Dashboard                 │    │  │
│  │  │  ┌─────────┬─────────┬─────────┬─────────┬─────────┬──────┐ │    │  │
│  │  │  │  Load   │ Memory  │CPU Temp │ Replic. │   UPS   │Uptime│ │    │  │
│  │  │  └─────────┴─────────┴─────────┴─────────┴─────────┴──────┘ │    │  │
│  │  │  ┌───────────────────────────────────────────────────────┐  │    │  │
│  │  │  │  System Performance: Load / CPU / Memory timeseries   │  │    │  │
│  │  │  └───────────────────────────────────────────────────────┘  │    │  │
│  │  │  ┌───────────────────────────────────────────────────────┐  │    │  │
│  │  │  │  Service Status: Replication / Apps / VMs tables      │  │    │  │
│  │  │  └───────────────────────────────────────────────────────┘  │    │  │
│  │  │  ┌───────────────────────────────────────────────────────┐  │    │  │
│  │  │  │  Storage & Network / UPS Power / Logs panels          │  │    │  │
│  │  │  └───────────────────────────────────────────────────────┘  │    │  │
│  │  └─────────────────────────────────────────────────────────────┘    │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Metrics Flow

1. **TrueNAS Custom Exporter** (`truenas-exporter.py`)
   - Polls TrueNAS REST API every scrape interval (default: 15s)
   - Endpoints: `/api/v2.0/replication`, `/api/v2.0/app`, `/api/v2.0/vm`, `/api/v2.0/virt/instance`
   - Exposes Prometheus metrics on port 9814

2. **Graphite Exporter** (`graphite_exporter`)
   - TrueNAS pushes Graphite metrics to port 2003
   - Transforms to Prometheus format using mapping rules
   - Exposes on port 9108

3. **Prometheus/VictoriaMetrics**
   - Scrapes both exporters every 15 seconds
   - Evaluates alert rules
   - Stores time-series data

4. **Grafana**
   - Queries Prometheus for dashboard visualization
   - Renders panels and tables

### Logs Flow (Optional)

1. **TrueNAS** sends syslog messages (UDP 6514)
2. **Grafana Alloy** receives and processes logs
3. **VictoriaLogs** stores logs (Loki-compatible API)
4. **Grafana** queries logs for dashboard panels

## Component Details

### TrueNAS Exporter

The custom Python exporter is the core component for TrueNAS-specific metrics.

**Features:**
- Multi-target support (monitor multiple NAS systems)
- No external dependencies (Python stdlib only)
- Configurable via YAML
- Health check endpoint (`/health`)

**API Endpoints Used:**

| Endpoint | Data |
|----------|------|
| `GET /api/v2.0/replication` | Replication tasks, state, schedule |
| `GET /api/v2.0/app` | Docker Compose apps |
| `GET /api/v2.0/vm` | Legacy bhyve VMs |
| `GET /api/v2.0/virt/instance` | Incus containers/VMs (25.04+) |

### Graphite Exporter

Converts TrueNAS's native Graphite metrics to Prometheus format.

**Metric Sources:**
- CPU: Usage per core, temperature
- Memory: Total, available, ARC
- Disk: I/O throughput, temperatures
- Network: Interface traffic
- UPS: NUT metrics (if configured)

### Alert Rules

Pre-configured Prometheus alert rules cover:

| Category | Alerts |
|----------|--------|
| Replication | API unreachable, task failed, overdue |
| Apps/VMs | Crashed, error state |
| System | High temp, high load, high memory |
| UPS | Low battery, on battery, low runtime |

## Security Considerations

### API Token Security

- Store API tokens securely (not in version control)
- Use minimal permissions (read-only where possible)
- Rotate tokens periodically

### Network Security

- Run exporters on internal/private network
- Use firewall rules to restrict access
- Consider TLS for Prometheus scraping

### File Permissions

```bash
# Config file should be readable only by service user
sudo chown prometheus:prometheus /etc/truenas-exporter/config.yaml
sudo chmod 600 /etc/truenas-exporter/config.yaml
```

## Scaling Considerations

### Multiple TrueNAS Systems

One exporter instance can monitor multiple TrueNAS systems. Configure multiple targets in the YAML config.

### High Availability

For critical monitoring:
- Run redundant Prometheus instances
- Use VictoriaMetrics cluster mode
- Configure alertmanager HA

### Performance

- Default scrape interval: 15 seconds
- Adjust based on your needs
- Graphite metrics have ~15s resolution from TrueNAS
