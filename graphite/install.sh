#!/bin/bash
# Install graphite_exporter for TrueNAS monitoring
# Usage: sudo ./install.sh [version]

set -e

VERSION="${1:-0.16.0}"
ARCH="$(uname -m)"

case "$ARCH" in
    x86_64)  ARCH="amd64" ;;
    aarch64) ARCH="arm64" ;;
    armv7l)  ARCH="armv7" ;;
    *)
        echo "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

DOWNLOAD_URL="https://github.com/prometheus/graphite_exporter/releases/download/v${VERSION}/graphite_exporter-${VERSION}.linux-${ARCH}.tar.gz"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/graphite_exporter"

echo "==> Installing graphite_exporter v${VERSION} (${ARCH})"

# Download
TMPDIR=$(mktemp -d)
cd "$TMPDIR"

echo "==> Downloading from ${DOWNLOAD_URL}"
wget -q --show-progress "$DOWNLOAD_URL" -O graphite_exporter.tar.gz

# Extract
echo "==> Extracting..."
tar xzf graphite_exporter.tar.gz

# Install binary
echo "==> Installing to ${INSTALL_DIR}"
sudo cp graphite_exporter-*/graphite_exporter "$INSTALL_DIR/"
sudo chmod +x "${INSTALL_DIR}/graphite_exporter"

# Create config directory
echo "==> Creating config directory"
sudo mkdir -p "$CONFIG_DIR"

# Copy mapping config if it exists in current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/graphite_mapping.conf" ]; then
    echo "==> Installing mapping configuration"
    sudo cp "${SCRIPT_DIR}/graphite_mapping.conf" "${CONFIG_DIR}/"
fi

# Cleanup
cd /
rm -rf "$TMPDIR"

echo "==> Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Copy graphite_mapping.conf to ${CONFIG_DIR}/ (if not already done)"
echo "  2. Install the systemd service: sudo cp graphite-exporter.service /etc/systemd/system/"
echo "  3. Enable and start: sudo systemctl enable --now graphite-exporter"
echo "  4. Configure TrueNAS: System -> Reporting -> Remote Graphite Server"
echo ""
echo "Verify installation:"
echo "  ${INSTALL_DIR}/graphite_exporter --version"
