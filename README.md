# TrueNAS Grafana Monitoring

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Complete monitoring solution for TrueNAS systems using Prometheus and Grafana.

![Dashboard Preview](docs/images/dashboard-preview.png)

## Features

- **Replication Monitoring** - Track ZFS replication task status, age, and failures
- **App Monitoring** - Monitor Docker Compose apps (TrueNAS Scale)
- **VM Monitoring** - Track legacy bhyve VMs and Incus instances (TrueNAS 25.04+)
- **System Metrics** - CPU, memory, load, disk I/O, network via Graphite
- **UPS Monitoring** - Battery status, runtime, voltage (via NUT)
- **Alerting** - Pre-configured alert rules for common issues
- **Log Aggregation** - Optional VictoriaLogs/Loki integration

## Quick Start

### 1. Install the TrueNAS Exporter

```bash
# Clone the repository
git clone https://github.com/alexlmiller/truenas-grafana.git
cd truenas-grafana

# Install the exporter
sudo mkdir -p /opt/truenas-exporter /etc/truenas-exporter
sudo cp exporter/truenas-exporter.py /opt/truenas-exporter/
sudo chmod +x /opt/truenas-exporter/truenas-exporter.py

# Create configuration
sudo cp exporter/config.example.yaml /etc/truenas-exporter/config.yaml
sudo nano /etc/truenas-exporter/config.yaml  # Add your API token

# Install and start service
sudo cp exporter/truenas-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now truenas-exporter

# Verify it's working
curl http://localhost:9814/metrics
```

### 2. Configure TrueNAS API Token

1. Log into TrueNAS web UI
2. Go to top-right user menu → **API Keys**
3. Click **Add** to create a new API key
4. Name it (e.g., "prometheus-exporter")
5. Copy the token and add it to `/etc/truenas-exporter/config.yaml`

### 3. (Optional) Install Graphite Exporter

For system metrics (CPU, memory, disk I/O, etc.):

```bash
# Install
cd graphite
sudo ./install.sh

# Configure
sudo cp graphite_mapping.conf /etc/graphite_exporter/
sudo cp graphite-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now graphite-exporter

# Configure TrueNAS: System → Reporting → Remote Graphite Server
# Set hostname to your monitoring server IP
```

### 4. Configure Prometheus

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'truenas'
    static_configs:
      - targets: ['localhost:9814']  # Custom exporter
      - targets: ['localhost:9108']  # Graphite exporter (optional)
```

### 5. Import Grafana Dashboard

1. In Grafana, go to **Dashboards** → **Import**
2. Upload `grafana/dashboards/truenas-overview.json`
3. Select your Prometheus datasource
4. Click **Import**

## Architecture

```
┌─────────────┐     ┌─────────────────────────────────────────┐
│   TrueNAS   │     │           Monitoring Server             │
├─────────────┤     ├─────────────────────────────────────────┤
│             │     │                                         │
│  API ───────┼────►│  truenas-exporter:9814 ─────┐          │
│  (REST)     │     │  (replication, apps, VMs)    │          │
│             │     │                              ▼          │
│             │     │                         Prometheus      │
│  Graphite ──┼────►│  graphite_exporter:9108 ────►  or      │
│  (native)   │     │  (CPU, mem, disk, net)   VictoriaMetrics│
│             │     │                              │          │
│             │     │                              ▼          │
│  Syslog ────┼────►│  Alloy:6514 ──► VictoriaLogs │          │
│  (optional) │     │  (logs)                      │          │
│             │     │                              ▼          │
└─────────────┘     │                          Grafana        │
                    └─────────────────────────────────────────┘
```

## Components

| Component | Port | Purpose |
|-----------|------|---------|
| truenas-exporter | 9814 | Custom metrics (replication, apps, VMs) |
| graphite_exporter | 2003, 9108 | TrueNAS Graphite → Prometheus |
| Prometheus | 9090 | Metrics storage & alerting |
| Grafana | 3000 | Visualization |
| VictoriaLogs | 9428 | Log storage (optional) |
| Alloy | 6514 | Syslog receiver (optional) |

## Metrics Reference

See [docs/METRICS.md](docs/METRICS.md) for complete metrics documentation.

### Custom Exporter Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `truenas_replication_up` | Gauge | 1 if API reachable |
| `truenas_replication_state` | Gauge | Task state (1=OK, -1=ERROR) |
| `truenas_replication_age_seconds` | Gauge | Time since last run |
| `truenas_app_state` | Gauge | App state (1=RUNNING, -1=CRASHED) |
| `truenas_vm_state` | Gauge | VM state (1=RUNNING, 0=STOPPED) |
| `truenas_virt_state` | Gauge | Incus instance state |

### Graphite Metrics (via graphite_exporter)

| Metric | Description |
|--------|-------------|
| `system_load` | System load averages |
| `cpu_temperature` | CPU temperature per core |
| `truenas_meminfo` | Memory statistics |
| `disk_temperature` | Disk temperatures |
| `interface_octets` | Network traffic |
| `ups_charge_percent` | UPS battery level |

## Alerting

Pre-configured alerts in `prometheus/alerts/truenas.rules.yml`:

- **TrueNASAPIUnreachable** - API connectivity lost
- **TrueNASReplicationFailed** - Replication task failed
- **TrueNASReplicationOverdue** - Replication hasn't run on schedule
- **TrueNASAppCrashed** - Docker app crashed
- **TrueNASHighCPUTemp** - CPU temperature warning
- **TrueNASLowUPSBattery** - UPS battery critical

## Compatibility

| TrueNAS Version | Support |
|-----------------|---------|
| TrueNAS Scale 24.04+ | Full |
| TrueNAS Scale 25.04+ | Full (including Incus) |
| TrueNAS Core | Partial (no apps/Incus) |

## Configuration

### Multi-Target Monitoring

Monitor multiple TrueNAS systems from one exporter:

```yaml
# /etc/truenas-exporter/config.yaml
listen_port: 9814

targets:
  - name: "nas-primary"
    api_url: "https://nas-primary.local"
    api_token: "TOKEN_1"
    verify_ssl: false

  - name: "nas-backup"
    api_url: "https://nas-backup.local"
    api_token: "TOKEN_2"
    verify_ssl: false
```

### SSL Verification

For self-signed certificates, set `verify_ssl: false`. For production with valid certificates:

```yaml
targets:
  - name: "nas"
    api_url: "https://nas.example.com"
    api_token: "YOUR_TOKEN"
    verify_ssl: true
```

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues.

### Quick Checks

```bash
# Check exporter is running
curl http://localhost:9814/health

# Check metrics are being scraped
curl http://localhost:9814/metrics | head -50

# Check Prometheus target status
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="truenas")'
```

## Contributing

Contributions welcome! Please read the contributing guidelines first.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [prometheus/graphite_exporter](https://github.com/prometheus/graphite_exporter) - Graphite to Prometheus bridge
- [TrueNAS](https://www.truenas.com/) - The excellent NAS platform
- [VictoriaMetrics](https://victoriametrics.com/) - Fast and efficient metrics storage
