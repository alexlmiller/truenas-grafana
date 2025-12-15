# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-12-15

### Added
- Drop rules in graphite_mapping.conf to reduce CPU overhead by ~50%
  - Drops ~1,060 unused cgroup metrics (pressure, throttling, detailed memory)
  - Drops ~150+ unused interface state metrics (operstate, carrier, duplex)
  - Keeps metrics used by dashboard (cgroup_cpu_percent, cgroup_mem, interface_*)
- Performance tuning documentation in graphite/README.md

### Changed
- graphite_mapping.conf now processes drop rules first before other mappings

## [1.0.0] - 2025-12-11

### Added
- Initial release
- Custom TrueNAS exporter (`truenas-exporter.py`)
  - Replication task monitoring
  - App state monitoring (TrueNAS Scale)
  - Legacy VM monitoring (bhyve)
  - Incus instance monitoring (TrueNAS 25.04+)
  - Multi-target support
  - YAML configuration
- Graphite exporter setup
  - Install script
  - Mapping configuration for TrueNAS metrics
  - Systemd service file
- Grafana dashboard
  - System overview (load, memory, CPU temp)
  - Replication status
  - Apps, VMs, and Incus instances tables
  - Storage and network panels
  - UPS monitoring
- Prometheus alert rules
  - API unreachable
  - Replication failed/overdue
  - App/VM errors
  - System health (CPU temp, memory, load)
  - UPS battery warnings
- VictoriaLogs/Loki integration
  - Alloy syslog receiver configuration
  - Log enrichment pipeline
- Documentation
  - Architecture overview
  - Complete metrics reference
  - Troubleshooting guide
