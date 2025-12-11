# Metrics Reference

Complete reference for all metrics exposed by the TrueNAS monitoring stack.

## Custom Exporter Metrics

These metrics are exposed by `truenas-exporter.py` on port 9814.

### Replication Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `truenas_replication_up` | Gauge | `host` | 1 if TrueNAS API is reachable, 0 otherwise |
| `truenas_replication_state` | Gauge | `host`, `task_name`, `task_id` | Task state: 1=FINISHED, 0.5=RUNNING, 0=PENDING, -1=ERROR |
| `truenas_replication_last_run_timestamp` | Gauge | `host`, `task_name`, `task_id` | Unix timestamp of last replication run |
| `truenas_replication_age_seconds` | Gauge | `host`, `task_name`, `task_id` | Seconds since last replication run |
| `truenas_replication_expected_interval_seconds` | Gauge | `host`, `task_name`, `task_id` | Expected interval between runs (from schedule) |
| `truenas_replication_info` | Gauge | `host`, `task_name`, `task_id`, `direction`, `transport`, `source`, `target`, `last_snapshot` | Metadata (always 1) |

**State Values:**
| Value | Meaning |
|-------|---------|
| 1 | FINISHED / SUCCESS |
| 0.5 | RUNNING |
| 0 | PENDING / WAITING |
| -1 | ERROR / FAILED |

**Example Queries:**

```promql
# All replication tasks in error state
truenas_replication_state == -1

# Tasks that haven't run in 2x their expected interval
truenas_replication_age_seconds > (truenas_replication_expected_interval_seconds * 2)

# Time since last successful replication
time() - truenas_replication_last_run_timestamp
```

### App Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `truenas_app_state` | Gauge | `host`, `app` | App state: 1=RUNNING, 0.5=DEPLOYING, 0=STOPPED, -1=CRASHED |
| `truenas_app_info` | Gauge | `host`, `app`, `version`, `train` | App metadata (always 1) |

**State Values:**
| Value | Meaning |
|-------|---------|
| 1 | RUNNING / ACTIVE |
| 0.5 | DEPLOYING |
| 0 | STOPPED |
| -1 | CRASHED |

**Example Queries:**

```promql
# Count of running apps per host
count(truenas_app_state == 1) by (host)

# Crashed apps
truenas_app_state == -1
```

### VM Metrics (Legacy bhyve)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `truenas_vm_state` | Gauge | `host`, `vm`, `vm_id` | VM state: 1=RUNNING, 0=STOPPED, -1=ERROR |
| `truenas_vm_info` | Gauge | `host`, `vm`, `vm_id`, `vcpus`, `memory_mb`, `autostart` | VM metadata (always 1) |

### Incus Instance Metrics (TrueNAS 25.04+)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `truenas_virt_state` | Gauge | `host`, `instance`, `instance_id`, `type` | State: 1=RUNNING, 0=STOPPED, -1=ERROR |
| `truenas_virt_info` | Gauge | `host`, `instance`, `instance_id`, `type`, `cpu`, `memory_mb`, `autostart` | Metadata (always 1) |

**Type Values:**
- `CONTAINER` - LXC container
- `VM` - Incus virtual machine

---

## Graphite Exporter Metrics

These metrics come from TrueNAS's native Graphite output, converted by `graphite_exporter`.

### System Load

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `system_load` | Gauge | `host`, `kind` | System load average |

**kind Values:** `load1`, `load5`, `load15`

```promql
# 1-minute load average
system_load{kind="load1"}
```

### CPU Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `cpu_usage` | Gauge | `host`, `cpu`, `type` | CPU usage percentage |
| `cpu_temperature` | Gauge | `host`, `cpu` | CPU core temperature (°C) |
| `cgroup_cpu_percent` | Gauge | `host`, `cgroup` | Cgroup CPU usage % |

**type Values:** `user`, `system`, `nice`, `idle`, `wait`, `interrupt`, `softirq`, `steal`

```promql
# Average CPU temperature
avg(cpu_temperature) by (host)

# CPU usage (simplified)
cgroup_cpu_percent{cgroup="truenas_cpu_usage"}
```

### Memory Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `memory` | Gauge | `host`, `type` | Memory statistics (bytes) |
| `truenas_meminfo` | Gauge | `host`, `type` | TrueNAS memory info |

**type Values:** `used`, `free`, `cached`, `buffered`, `slab_recl`, `slab_unrecl`

```promql
# Memory usage percentage
100 - (truenas_meminfo{type="available"} / truenas_meminfo{type="total"} * 100)
```

### Disk Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `disk_ops` | Counter | `host`, `disk`, `op` | Disk operations count |
| `disk_octets` | Counter | `host`, `disk`, `direction` | Disk throughput (bytes) |
| `disk_time` | Counter | `host`, `disk`, `op` | Disk operation time |
| `disk_temperature` | Gauge | `host`, `serial` | Disk temperature (°C) |

**direction Values:** `read`, `write`

```promql
# Total disk read throughput
sum(rate(disk_octets{direction="read"}[5m])) by (host)

# Maximum disk temperature
max(disk_temperature) by (host)
```

### Network Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `interface_octets` | Counter | `host`, `interface`, `direction` | Network traffic (bytes) |
| `interface_packets` | Counter | `host`, `interface`, `direction` | Packet count |
| `interface_errors` | Counter | `host`, `interface`, `direction` | Error count |

**direction Values:** `rx`, `tx`

```promql
# Network throughput (bits/s)
rate(interface_octets{interface="eno1"}[5m]) * 8
```

### UPS Metrics (NUT)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ups_charge_percent` | Gauge | `host`, `ups` | Battery charge percentage |
| `ups_load_percent` | Gauge | `host`, `ups` | UPS load percentage |
| `ups_runtime_seconds` | Gauge | `host`, `ups` | Estimated runtime (seconds) |
| `ups_voltage` | Gauge | `host`, `ups`, `type` | Voltage (input/output) |
| `ups_temperature` | Gauge | `host`, `ups` | UPS temperature |

```promql
# UPS battery below 50%
ups_charge_percent < 50

# UPS runtime in minutes
ups_runtime_seconds / 60
```

### Uptime

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `uptime` | Gauge | `host` | System uptime (seconds) |

```promql
# Uptime in days
uptime / 86400
```

---

## ZFS Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `zfs_arc` | Gauge | `host`, `cache`, `type` | ZFS ARC statistics |
| `zfs_arc_v2` | Gauge | `host`, `metric` | ZFS ARC v2 stats |

```promql
# ARC hit rate (if available)
zfs_arc{cache="hits"} / (zfs_arc{cache="hits"} + zfs_arc{cache="misses"}) * 100
```

---

## Useful PromQL Queries

### Dashboard Queries

```promql
# System overview
system_load{kind="load1", host="$host"}
max(cpu_temperature{host="$host"})
100 - (truenas_meminfo{host="$host", type="available"} / truenas_meminfo{host="$host", type="total"} * 100)

# Replication status (worst state)
min(truenas_replication_state{host="$host"})

# Count of healthy apps
count(truenas_app_state{host="$host"} == 1)

# Total disk I/O
sum(rate(disk_octets{host="$host", direction="read"}[5m]))
sum(rate(disk_octets{host="$host", direction="write"}[5m]))
```

### Alerting Queries

```promql
# API down for more than 2 minutes
truenas_replication_up == 0

# Any replication in error state
truenas_replication_state == -1

# Replication overdue
truenas_replication_age_seconds > (truenas_replication_expected_interval_seconds * 2)

# High CPU temperature
max(cpu_temperature) by (host) > 75

# Low UPS battery
ups_charge_percent < 20

# High system load
system_load{kind="load1"} > 8
```

### Capacity Planning

```promql
# Memory trend (7-day prediction)
predict_linear(truenas_meminfo{type="available"}[7d], 86400 * 30)

# Disk I/O patterns
avg_over_time(rate(disk_octets{direction="write"}[5m])[7d:1h])
```
