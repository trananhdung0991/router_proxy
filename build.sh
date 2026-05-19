#!/bin/bash
set -e

function on_error {
    echo "Error occurred in command: $BASH_COMMAND"
    exit 1
}
trap on_error ERR
opkg update
opkg install python3 python3-pip gcc
pip3 install pyarmor==8.5.10
echo "Building Router Proxy Application with PyArmor"
cd "$(dirname "$0")/app"
./obfuscate.sh
echo "Build completed successfully!"  
cd ..

# Read version
VERSION=$(cat VERSION | tr -d '[:space:]')
if [ -z "$VERSION" ]; then
    echo "ERROR: VERSION file is empty"
    exit 1
fi
echo "Building version: $VERSION"

rm -rf install_package
mkdir install_package
cp -r app/dist/* install_package/
echo "Installation package is ready in 'install_package' directory."
mkdir install_package/web
cp -r webUI/web/router-app/dist/* install_package/web/

# Write VERSION into payload
echo "$VERSION" > install_package/VERSION
echo "$VERSION" > install_package/web/VERSION

# Bundle UPDATE_SIGNING_KEY into payload (if provided) so router can verify
# signatures from license server. Should be the same secret as server-side.
if [ -n "$UPDATE_SIGNING_KEY" ]; then
    echo "$UPDATE_SIGNING_KEY" > install_package/UPDATE_SIGNING_KEY
fi

# Copy service init script
cp router_proxy.init install_package/
chmod +x install_package/router_proxy.init
echo "Service init script copied."

cp install.sh install_package/
chmod +x install_package/install.sh
echo "Installation script copied."

# === OTA update tarball (payload only, no install.sh / init script) ===
echo "Building OTA update tarball..."
rm -rf dist
mkdir -p dist
TARBALL="dist/router_proxy-${VERSION}.tar.gz"
STAGE="dist/_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
for item in main.py resource_path.py router pyarmor_runtime_005235 web VERSION UPDATE_SIGNING_KEY; do
    if [ -e "install_package/$item" ]; then
        cp -a "install_package/$item" "$STAGE/"
    fi
done

tar -C "$STAGE" -czf "$TARBALL" .
rm -rf "$STAGE"

SHA256=$(sha256sum "$TARBALL" | awk '{print $1}')
SIZE=$(stat -c%s "$TARBALL" 2>/dev/null || stat -f%z "$TARBALL")
echo "$SHA256  $(basename "$TARBALL")" > "dist/router_proxy-${VERSION}.sha256"

SIGNATURE=""
if [ -n "$UPDATE_SIGNING_KEY" ]; then
    SIGNATURE=$(printf "%s|%s|%s" "$VERSION" "$SHA256" "$SIZE" \
        | openssl dgst -sha256 -hmac "$UPDATE_SIGNING_KEY" -hex 2>/dev/null \
        | awk '{print $NF}')
fi

cat > "dist/router_proxy-${VERSION}.manifest.json" <<EOF
{
  "product": "router_proxy",
  "channel": "stable",
  "version": "${VERSION}",
  "filename": "router_proxy-${VERSION}.tar.gz",
  "sha256": "${SHA256}",
  "size": ${SIZE},
  "signature": "${SIGNATURE}",
  "notes": ""
}
EOF

echo ""
echo "=== Build artifacts ==="
ls -lh dist/
echo ""
echo "Tarball : $TARBALL"
echo "SHA-256 : $SHA256"
echo "Size    : $SIZE bytes"
if [ -z "$SIGNATURE" ]; then
    echo "WARN: UPDATE_SIGNING_KEY env not set — manifest 'signature' is empty."
    echo "      Re-run with: UPDATE_SIGNING_KEY=xxx bash build.sh"
fi

echo "Build script finished."