# Troubleshooting Guide

Common issues and solutions for the TrueNAS monitoring stack.

## Quick Diagnostics

```bash
# Check all services are running
sudo systemctl status truenas-exporter graphite-exporter prometheus grafana-server

# Check exporter health
curl -s http://localhost:9814/health
curl -s http://localhost:9108/metrics | head -5

# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Check for errors in logs
sudo journalctl -u truenas-exporter --since "1 hour ago" --no-pager
```

---

## Exporter Issues

### API Unreachable

**Symptoms:**
- `truenas_replication_up == 0`
- Alert: "TrueNAS API Unreachable"
- No metrics in Grafana

**Causes & Solutions:**

1. **Wrong API URL**
   ```bash
   # Test API connectivity
   curl -k -H "Authorization: Bearer YOUR_TOKEN" \
     https://truenas.local/api/v2.0/system/info
   ```
   - Verify URL is correct (https, correct hostname/IP)
   - Check if TrueNAS web UI is accessible

2. **Invalid API Token**
   ```bash
   # Check token is correct
   curl -k -H "Authorization: Bearer YOUR_TOKEN" \
     https://truenas.local/api/v2.0/user
   ```
   - Regenerate API token in TrueNAS UI
   - Ensure token has correct permissions

3. **Network/Firewall Issues**
   ```bash
   # Test connectivity
   nc -zv truenas.local 443
   ```
   - Check firewall rules
   - Verify monitoring server can reach TrueNAS

4. **SSL Certificate Issues**
   - Set `verify_ssl: false` in config for self-signed certs
   - Or add TrueNAS CA to system trust store

### No Metrics Appearing

**Symptoms:**
- `/metrics` endpoint returns empty or partial data
- "No data" in Grafana panels

**Solutions:**

1. **Check exporter logs**
   ```bash
   sudo journalctl -u truenas-exporter -f
   ```

2. **Verify config is loaded**
   ```bash
   cat /etc/truenas-exporter/config.yaml
   ```

3. **Test API endpoints manually**
   ```bash
   curl -k -H "Authorization: Bearer TOKEN" \
     https://truenas.local/api/v2.0/replication
   ```

4. **Restart exporter**
   ```bash
   sudo systemctl restart truenas-exporter
   ```

### Replication Metrics Missing

**Possible Causes:**
- No replication tasks configured in TrueNAS
- All tasks are disabled
- Task names contain special characters

**Check:**
```bash
# View raw API response
curl -k -H "Authorization: Bearer TOKEN" \
  https://truenas.local/api/v2.0/replication | jq
```

### App Metrics Missing

**Possible Causes:**
- No apps installed (TrueNAS Scale only)
- Apps API not available (TrueNAS Core)

**Check:**
```bash
curl -k -H "Authorization: Bearer TOKEN" \
  https://truenas.local/api/v2.0/app | jq
```

### VM/Incus Metrics Missing

**Possible Causes:**
- No VMs configured
- Incus API requires TrueNAS 25.04+ (virt/instance endpoint)
- Legacy VMs use different API (vm endpoint)

**Check:**
```bash
# Legacy VMs
curl -k -H "Authorization: Bearer TOKEN" \
  https://truenas.local/api/v2.0/vm | jq

# Incus instances (25.04+)
curl -k -H "Authorization: Bearer TOKEN" \
  https://truenas.local/api/v2.0/virt/instance | jq
```

---

## Graphite Exporter Issues

### No System Metrics (CPU, Memory, etc.)

**Symptoms:**
- Dashboard panels for CPU, memory, disk show "No data"
- Only replication/app metrics visible

**Solutions:**

1. **Check TrueNAS Reporting is configured**
   - TrueNAS UI → System → Reporting
   - Set "Remote Graphite Server" to monitoring server IP

2. **Check port 2003 is open**
   ```bash
   sudo ss -tlnp | grep 2003
   nc -zv localhost 2003
   ```

3. **Check graphite_exporter is receiving**
   ```bash
   curl localhost:9108/metrics | grep -c truenas
   ```

4. **Check firewall**
   ```bash
   sudo ufw allow 2003/tcp
   ```

5. **Verify mapping config is loaded**
   ```bash
   cat /etc/graphite_exporter/graphite_mapping.conf
   ```

### Metrics Have Wrong Names

**Symptoms:**
- Raw metric names like `servers.truenas_local.cpu-0.cpu-user`
- Mapping not applied

**Solution:**
- Ensure mapping config path is correct in service file
- Restart graphite_exporter
- Check for syntax errors in mapping config

---

## Prometheus/Grafana Issues

### Targets Show as "Down"

**Check Prometheus target status:**
```bash
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets'
```

**Common causes:**
- Exporter not running
- Wrong port in scrape config
- Firewall blocking connection

### Dashboard Shows "No Data"

1. **Check datasource is configured**
   - Grafana → Connections → Data sources
   - Verify Prometheus URL

2. **Check variable queries**
   - Dashboard settings → Variables
   - Test variable queries

3. **Check time range**
   - Metrics may not exist for selected time range
   - Try "Last 15 minutes"

4. **Check metric names**
   ```bash
   # Search for metrics in Prometheus
   curl 'http://localhost:9090/api/v1/series?match[]=truenas_replication_up'
   ```

### Alerts Not Firing

1. **Check alert rules are loaded**
   ```bash
   curl http://localhost:9090/api/v1/rules | jq '.data.groups'
   ```

2. **Check Alertmanager**
   ```bash
   curl http://localhost:9093/api/v1/alerts
   ```

3. **Verify alert rule file path**
   ```yaml
   # In prometheus.yml
   rule_files:
     - /etc/prometheus/rules/truenas.rules.yml
   ```

---

## Common Error Messages

### "connection refused"

**Cause:** Service not running or wrong port

**Fix:**
```bash
sudo systemctl status <service>
sudo systemctl start <service>
```

### "certificate verify failed"

**Cause:** SSL verification with self-signed cert

**Fix:**
- Set `verify_ssl: false` in config
- Or import CA certificate

### "401 Unauthorized"

**Cause:** Invalid or expired API token

**Fix:**
1. Regenerate token in TrueNAS UI
2. Update config file
3. Restart exporter

### "timeout"

**Cause:** Network issues or TrueNAS overloaded

**Fix:**
- Check network connectivity
- Verify TrueNAS isn't overloaded
- Increase timeout in exporter (modify Python code if needed)

---

## Performance Issues

### High CPU/Memory on Monitoring Server

**Causes:**
- Too many targets
- Short scrape interval
- Too much data retention

**Solutions:**
- Increase scrape interval (30s instead of 15s)
- Reduce retention period
- Use VictoriaMetrics instead of Prometheus for better efficiency

### Slow Dashboard Loading

**Solutions:**
- Reduce time range
- Add dashboard caching
- Optimize queries (use recording rules)
- Consider using VictoriaMetrics

---

## Log Collection Issues

### No Logs in VictoriaLogs/Loki

1. **Check TrueNAS syslog config**
   - System → Advanced → Syslog
   - Verify server address and port

2. **Check Alloy is receiving**
   ```bash
   sudo journalctl -u alloy -f
   ```

3. **Check UDP port 6514**
   ```bash
   sudo ss -ulnp | grep 6514
   ```

4. **Test from TrueNAS**
   ```bash
   # From TrueNAS shell
   logger -n <monitoring-server> -P 6514 -d "test message"
   ```

---

## Getting Help

If you're still stuck:

1. **Check GitHub Issues:** [github.com/alexlmiller/truenas-grafana/issues](https://github.com/alexlmiller/truenas-grafana/issues)
2. **Open a new issue** with:
   - TrueNAS version
   - Monitoring stack versions
   - Relevant logs
   - Steps to reproduce
