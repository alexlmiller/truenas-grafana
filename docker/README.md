# Docker Deployment

Run both TrueNAS exporters in a single container using Docker Compose.

## Quick Start

```bash
# 1. Create configuration
cp exporter/config.example.yaml config.yaml

# 2. Edit config.yaml with your TrueNAS API token
nano config.yaml

# 3. Start the container
docker-compose up -d

# 4. Verify it's running
curl http://localhost:9814/health
curl http://localhost:9108/metrics | head
```

## Ports

| Port | Service | Purpose |
|------|---------|---------|
| 9814 | truenas-exporter | Custom metrics (replication, apps, VMs) |
| 2003 | graphite_exporter | Graphite receiver (TrueNAS sends here) |
| 9108 | graphite_exporter | Prometheus metrics (CPU, memory, disk, network, UPS) |

## Configuration

### TrueNAS Exporter Config

Mount your `config.yaml` to `/etc/truenas-exporter/config.yaml`:

```yaml
# config.yaml
listen_port: 9814

targets:
  - name: "nas-primary"
    api_url: "https://truenas.local"
    api_token: "YOUR_API_TOKEN_HERE"
    verify_ssl: false
```

### TrueNAS Graphite Setup

Configure TrueNAS to send Graphite metrics to your Docker host:

1. TrueNAS UI → **System** → **Reporting**
2. Set **Remote Graphite Server**: `<docker-host-ip>`
3. Save

TrueNAS will send metrics to port 2003.

## Prometheus Scrape Config

Add both exporters to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'truenas'
    static_configs:
      - targets: ['<docker-host>:9814']  # Custom exporter

  - job_name: 'truenas-graphite'
    static_configs:
      - targets: ['<docker-host>:9108']  # Graphite exporter
```

## Building Manually

```bash
# Build the image
docker build -t truenas-exporter .

# Run without compose
docker run -d \
  --name truenas-exporter \
  -p 9814:9814 \
  -p 2003:2003 \
  -p 9108:9108 \
  -v $(pwd)/config.yaml:/etc/truenas-exporter/config.yaml:ro \
  truenas-exporter
```

## Logs

```bash
# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs truenas-exporter | grep truenas-exporter
docker-compose logs truenas-exporter | grep graphite
```

## Troubleshooting

### No metrics from truenas-exporter

1. Check config is mounted correctly:
   ```bash
   docker-compose exec truenas-exporter cat /etc/truenas-exporter/config.yaml
   ```

2. Test API connectivity from container:
   ```bash
   docker-compose exec truenas-exporter python3 -c "
   import urllib.request, ssl
   ctx = ssl.create_default_context()
   ctx.check_hostname = False
   ctx.verify_mode = ssl.CERT_NONE
   req = urllib.request.Request('https://truenas.local/api/v2.0/system/info',
       headers={'Authorization': 'Bearer YOUR_TOKEN'})
   print(urllib.request.urlopen(req, context=ctx).read()[:100])
   "
   ```

### No metrics from graphite_exporter

1. Check TrueNAS can reach port 2003:
   ```bash
   # From TrueNAS shell
   nc -zv <docker-host> 2003
   ```

2. Check metrics are being received:
   ```bash
   curl localhost:9108/metrics | grep -c truenas
   ```

### Container won't start

Check logs for errors:
```bash
docker-compose logs
```

Common issues:
- Missing `config.yaml` file
- Invalid YAML syntax in config
- Port already in use
