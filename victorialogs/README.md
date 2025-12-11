# Log Aggregation for TrueNAS

This optional component enables log aggregation from TrueNAS systems.

## Loki vs VictoriaLogs

This guide uses **VictoriaLogs** as the log backend, but **Grafana Loki** works equally well since VictoriaLogs implements the Loki API. Choose based on your preferences:

| Feature | VictoriaLogs | Loki |
|---------|--------------|------|
| Query Language | LogQL (same) | LogQL |
| API | Loki-compatible | Native |
| Resource Usage | Lower | Higher |
| Complexity | Single binary | Multiple components |
| Maturity | Newer | More established |

**To use Loki instead:** Simply change the `loki.write` endpoint URL in the Alloy config from VictoriaLogs to your Loki instance (e.g., `http://localhost:3100/loki/api/v1/push`).

## Overview

TrueNAS can send syslog messages to a central collector. We use Grafana Alloy to receive these logs and forward them to VictoriaLogs (or Loki).

```
TrueNAS ──(syslog/UDP)──> Alloy:6514 ──> VictoriaLogs/Loki ──> Grafana
```

## Components

1. **Grafana Alloy** - Log collector and router
2. **VictoriaLogs** or **Loki** - Log storage (both use LogQL query language)
3. **Grafana** - Visualization

## Setup

### 1. Install VictoriaLogs

```bash
# Download
VERSION="1.40.0"
wget https://github.com/VictoriaMetrics/VictoriaMetrics/releases/download/v${VERSION}/victorialogs-linux-amd64-v${VERSION}.tar.gz
tar xzf victorialogs-linux-amd64-v${VERSION}.tar.gz
sudo mv victoria-logs-prod /usr/local/bin/victorialogs

# Create data directory
sudo mkdir -p /var/lib/victorialogs
sudo useradd -r -s /bin/false victorialogs
sudo chown victorialogs:victorialogs /var/lib/victorialogs

# Create systemd service
sudo tee /etc/systemd/system/victorialogs.service << 'EOF'
[Unit]
Description=VictoriaLogs
After=network.target

[Service]
Type=simple
User=victorialogs
ExecStart=/usr/local/bin/victorialogs \
    -storageDataPath=/var/lib/victorialogs \
    -retentionPeriod=4w \
    -httpListenAddr=:9428
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now victorialogs
```

### 2. Install Grafana Alloy

Follow the [official installation guide](https://grafana.com/docs/alloy/latest/set-up/install/).

### 3. Configure Alloy for TrueNAS Syslog

Create/edit `/etc/alloy/config.alloy`:

```hcl
// Syslog receiver for TrueNAS
loki.source.syslog "truenas" {
  listener {
    address  = "0.0.0.0:6514"
    protocol = "udp"
    labels   = {
      job = "truenas",
    }
  }

  // Parse RFC5424 syslog format
  forward_to = [loki.process.truenas.receiver]
}

// Process and enrich logs
loki.process "truenas" {
  stage.regex {
    expression = "(?P<host>[\\w.-]+)\\s+(?P<app>[\\w-]+)\\[?(?P<pid>\\d*)\\]?:\\s+(?P<message>.*)"
  }

  stage.labels {
    values = {
      host = "",
      app  = "",
    }
  }

  // Detect log level from message
  stage.regex {
    expression = "(?i)(?P<level>error|warn|warning|info|debug|critical|alert)"
  }

  stage.labels {
    values = {
      level = "",
    }
  }

  forward_to = [loki.write.victorialogs.receiver]
}

// Send to VictoriaLogs
loki.write "victorialogs" {
  endpoint {
    url = "http://localhost:9428/insert/loki/api/v1/push"
  }
}
```

Restart Alloy:
```bash
sudo systemctl restart alloy
```

### 4. Configure TrueNAS Syslog

1. Log into TrueNAS web UI
2. Navigate to **System** → **Advanced**
3. Under **Syslog**, configure:
   - **Use FQDN for logging**: Enabled
   - **Syslog Level**: Info (or Warning for less verbose)
   - **Syslog Server**: `<your-monitoring-server>:6514`
   - **Syslog Transport**: UDP
4. Click **Save**

### 5. Add VictoriaLogs Datasource in Grafana

1. Install the VictoriaLogs datasource plugin
2. Add datasource with URL: `http://localhost:9428`
3. Test connection

## Example Queries

### All TrueNAS Logs
```logql
{job="truenas"}
```

### Errors and Warnings Only
```logql
{job="truenas"} | level=~"error|warning"
```

### Replication/Backup Logs
```logql
{job="truenas"} |~ "replication|snapshot|zfs send|zfs recv"
```

### ZFS Events
```logql
{job="truenas", app="zed"}
```

### SMB/CIFS Access
```logql
{job="truenas", app="smbd"}
```

### Filter by Host
```logql
{job="truenas", host="nas-primary"}
```

## Dashboard Integration

The TrueNAS Overview dashboard includes optional log panels. To enable them:

1. Add your VictoriaLogs datasource as `${DS_LOKI}`
2. Import the dashboard
3. The "Logs" section will show relevant logs

## Troubleshooting

### No logs appearing

1. Check TrueNAS can reach Alloy:
   ```bash
   # From TrueNAS
   nc -zvu <monitoring-server> 6514
   ```

2. Check Alloy is receiving:
   ```bash
   sudo journalctl -u alloy -f
   ```

3. Check firewall allows UDP 6514:
   ```bash
   sudo ufw allow 6514/udp
   ```

### Logs not enriched with labels

Check the syslog format matches RFC5424. TrueNAS should send in this format by default.

## Resources

- [VictoriaLogs Documentation](https://docs.victoriametrics.com/victorialogs/)
- [Grafana Alloy Documentation](https://grafana.com/docs/alloy/latest/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/query/)
