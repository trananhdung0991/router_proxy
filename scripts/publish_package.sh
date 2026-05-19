#!/bin/bash
# Publish a built OTA package to the license server.
# Requires: ADMIN_TOKEN env var, dist/router_proxy-<version>.tar.gz + .manifest.json
#
# Usage:
#   ADMIN_TOKEN=xxx ./scripts/publish_package.sh [version] [server_url]
#   If [version] omitted, uses VERSION file.
#   server_url defaults to https://routerlic.xproxy.io

set -e

cd "$(dirname "$0")/.."

VERSION="${1:-$(cat VERSION | tr -d '[:space:]')}"
SERVER_URL="${2:-https://routerlic.xproxy.io}"

if [ -z "$ADMIN_TOKEN" ]; then
    echo "ERROR: ADMIN_TOKEN env var not set"
    exit 1
fi

TARBALL="dist/router_proxy-${VERSION}.tar.gz"
MANIFEST="dist/router_proxy-${VERSION}.manifest.json"

if [ ! -f "$TARBALL" ] || [ ! -f "$MANIFEST" ]; then
    echo "ERROR: missing $TARBALL or $MANIFEST — run build.sh first"
    exit 1
fi

echo "Publishing $TARBALL to $SERVER_URL ..."
curl -fsS -X POST "$SERVER_URL/api/admin/publish-package" \
    -H "X-Admin-Token: $ADMIN_TOKEN" \
    -F "manifest=@${MANIFEST};type=application/json" \
    -F "package=@${TARBALL};type=application/gzip"
echo ""
echo "Published."
