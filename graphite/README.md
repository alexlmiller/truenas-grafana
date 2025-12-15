# Graphite Exporter Setup for TrueNAS

TrueNAS has built-in support for sending system metrics via the Graphite protocol. The `graphite_exporter` converts these metrics to Prometheus format.

## What This Provides

TrueNAS's native Graphite metrics include:
- **CPU**: Usage, load averages (1m/5m/15m), temperature per core
- **Memory**: Total, available, ARC size, cache stats
- **Disk**: I/O throughput (read/write), temperatures per disk
- **Network**: Interface traffic (in/out) per interface
- **ZFS**: Pool stats, ARC hit rates
- **UPS**: Battery charge, load, runtime, voltage (if configured)

## Quick Setup

### 1. Install graphite_exporter

```bash
# Download and install (adjust version as needed)
sudo ./install.sh

# Or manually:
GRAPHITE_EXPORTER_VERSION="0.16.0"
wget https://github.com/prometheus/graphite_exporter/releases/download/v${GRAPHITE_EXPORTER_VERSION}/graphite_exporter-${GRAPHITE_EXPORTER_VERSION}.linux-amd64.tar.gz
tar xzf graphite_exporter-${GRAPHITE_EXPORTER_VERSION}.linux-amd64.tar.gz
sudo cp graphite_exporter-${GRAPHITE_EXPORTER_VERSION}.linux-amd64/graphite_exporter /usr/local/bin/
```

### 2. Install Configuration

```bash
# Copy mapping configuration
sudo mkdir -p /etc/graphite_exporter
sudo cp graphite_mapping.conf /etc/graphite_exporter/

# Install systemd service
sudo cp graphite-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now graphite-exporter
```

### 3. Configure TrueNAS

1. Log into TrueNAS web UI
2. Navigate to **System** → **Reporting**
3. Set **Remote Graphite Server Hostname**: Your monitoring server's IP/hostname
4. Set **Graph Age**: 1 (hour)
5. Set **Number of Graph Points**: 1200
6. Click **Save**

TrueNAS will start sending metrics to port 2003 on your monitoring server.

### 4. Verify It's Working

```bash
# Check the service is running
sudo systemctl status graphite-exporter

# Check metrics are being received
curl http://localhost:9108/metrics | grep truenas
```

## Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 2003 | TCP | Graphite receiver (TrueNAS sends here) |
| 9108 | HTTP | Prometheus metrics endpoint |

## Prometheus Scrape Config

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'truenas-graphite'
    static_configs:
      - targets: ['localhost:9108']
        labels:
          job: 'truenas'
```

## Performance Tuning

The mapping configuration includes **drop rules** that filter out unused TrueNAS metrics early, reducing CPU overhead by approximately 50%.

### What Gets Dropped

TrueNAS sends 1,000+ metrics, but dashboards only use a subset. The drop rules filter:

**Cgroup Metrics (~1,060 series):**
- `cgroup_*_pressure` - CPU/IO/memory pressure metrics
- `cgroup_*_stall_time` - Stall duration metrics
- `cgroup_mem_*` - Detailed memory (usage_limit, utilization, pgfaults, writeback)
- `cgroup_io_*` - IO usage, serviced ops
- `cgroup_throttled_*` - CPU throttling metrics

**Interface State Metrics (~150+ series):**
- `net_operstate` - Interface up/down state
- `net_carrier` - Carrier detect state
- `net_duplex` - Full/half duplex state

### What's Kept

Metrics used by the included Grafana dashboard:
- `cgroup_cpu_percent` - Container/service CPU usage
- `cgroup_mem` - Container/service memory usage
- `interface_*` - Network traffic (errors, octets, packets)
- All CPU, memory, disk, ZFS, and UPS metrics

### Re-enabling Dropped Metrics

To re-enable any metric, edit `graphite_mapping.conf` and comment out or remove the corresponding drop rule at the top of the file. For example:

```yaml
# Comment out to re-enable pressure metrics:
# - match: 'servers\..*\.truenas-cgroup_(cpu_full_pressure|...'
#   match_type: "regex"
#   name: "dropped_cgroup_pressure"
#   action: drop
```

Then restart the graphite_exporter:

```bash
sudo systemctl restart graphite-exporter
```

## Troubleshooting

### No metrics appearing

1. Check TrueNAS can reach port 2003:
   ```bash
   # On TrueNAS
   nc -zv <monitoring-server> 2003
   ```

2. Check firewall allows TCP 2003:
   ```bash
   sudo ufw allow 2003/tcp
   # or
   sudo firewall-cmd --add-port=2003/tcp --permanent
   ```

3. Check graphite_exporter logs:
   ```bash
   sudo journalctl -u graphite-exporter -f
   ```

### Metrics have wrong names

The `graphite_mapping.conf` file transforms TrueNAS metric names. If you see raw names like `servers.truenas_local.cpu-0.cpu-user`, the mapping file isn't being loaded correctly.

## Reference

- [graphite_exporter on GitHub](https://github.com/prometheus/graphite_exporter)
- [TrueNAS Reporting Documentation](https://www.truenas.com/docs/scale/scaletutorials/systemsettings/reportingscale/)
