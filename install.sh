#!/bin/sh
# Router Proxy Installation Script for OpenWrt

echo "=== Router Proxy Installation for OpenWrt ==="

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Detect package manager (opkg for <=24.x, apk for >=25.x)
if command -v apk > /dev/null 2>&1; then
    PKG_MANAGER="apk"
    echo "Detected package manager: apk (OpenWrt 25.x+)"
elif command -v opkg > /dev/null 2>&1; then
    PKG_MANAGER="opkg"
    echo "Detected package manager: opkg (OpenWrt 24.x)"
else
    echo "Error: This script is for OpenWrt only (no apk or opkg found)"
    exit 1
fi

# Install Python and dependencies
echo "Installing Python dependencies..."
if [ "$PKG_MANAGER" = "apk" ]; then
    apk update
    apk add python3 python3-pip tinyproxy
    pip3 install flask flask-cors psutil requests
    apk del dnsmasq 2>/dev/null || true
    apk add dnsmasq-full
    apk add kmod-nft-tproxy kmod-nft-socket
else
    opkg update
    opkg install python3 python3-pip tinyproxy
    pip3 install flask flask-cors psutil requests
    opkg remove dnsmasq
    opkg install dnsmasq-full
    opkg install kmod-nft-tproxy kmod-nft-socket
fi
pip3 install pyarmor==8.5.10

# Install Passwall2
echo "Installing Passwall2..."

# Check OpenWrt version
echo "Checking OpenWrt version..."
if [ -f /etc/os-release ]; then
    . /etc/os-release
    RELEASE=$VERSION_ID
    ARCH=$(uname -m)
    echo "Detected OpenWrt $RELEASE on $ARCH architecture"
    VERSION_MAJOR_MINOR=$(echo $RELEASE | cut -d'.' -f1,2)
elif [ -f /etc/openwrt_release ]; then
    . /etc/openwrt_release
    RELEASE=$DISTRIB_RELEASE
    ARCH=$DISTRIB_ARCH
    echo "Detected OpenWrt $RELEASE on $ARCH architecture"
    VERSION_MAJOR_MINOR=$(echo $RELEASE | cut -d'.' -f1,2)
else
    echo "Warning: Could not detect OpenWrt version"
    RELEASE="25.12"
    ARCH="x86_64"
    VERSION_MAJOR_MINOR="25.12"
fi

if [ "$PKG_MANAGER" = "apk" ]; then
    # apk-based: add passwall2 repo and install
    echo "Adding Passwall2 repository for apk..."
    PASSWALL_REPO="https://master.dl.sourceforge.net/project/openwrt-passwall-build/releases/packages-$VERSION_MAJOR_MINOR/$ARCH/passwall2"
    if ! grep -q "passwall2" /etc/apk/repositories 2>/dev/null; then
        echo "$PASSWALL_REPO" >> /etc/apk/repositories
    fi
    apk update 2>/dev/null || true
    if apk info luci-app-passwall2 > /dev/null 2>&1; then
        echo "Passwall2 is already installed, skipping installation"
    else
        apk add luci-app-passwall2 || echo "Warning: luci-app-passwall2 not available via apk, skipping"
    fi
else
    # opkg-based
    echo "Adding Passwall2 repositories for OpenWrt $VERSION_MAJOR_MINOR..."
    wget -O passwall.pub https://master.dl.sourceforge.net/project/openwrt-passwall-build/passwall.pub
    opkg-key add passwall.pub
    if ! grep -q "passwall_packages.*$VERSION_MAJOR_MINOR" /etc/opkg/customfeeds.conf 2>/dev/null; then
        cat <<EOF >> /etc/opkg/customfeeds.conf
src/gz passwall_packages https://master.dl.sourceforge.net/project/openwrt-passwall-build/releases/packages-$VERSION_MAJOR_MINOR/$ARCH/passwall_packages
src/gz passwall2 https://master.dl.sourceforge.net/project/openwrt-passwall-build/releases/packages-$VERSION_MAJOR_MINOR/$ARCH/passwall2
EOF
    else
        echo "Passwall repositories already exist in customfeeds.conf, skipping..."
    fi
    opkg update
    if opkg list-installed | grep -q "luci-app-passwall2"; then
        echo "Passwall2 is already installed, skipping installation"
    else
        opkg install luci-app-passwall2
    fi
fi

echo "Passwall2 installation completed"

# Copy application files
echo "Installing application files..."
mkdir -p /root/router

# Copy all files except install.sh and router_proxy.init
for item in *; do
    if [ "$item" != "install.sh" ] && [ "$item" != "router_proxy.init" ]; then
        cp -r "$item" /root/router/
    fi
done

echo "Application files installed to /root/router/"

# Copy web files
echo "Installing web UI..."
mkdir -p /www/router-app
if [ -d "web" ]; then
    cp -r web/* /www/router-app/
fi

# Install service
echo "Installing service..."
if [ -f "router_proxy.init" ]; then
    cp router_proxy.init /etc/init.d/router_proxy
    chmod +x /etc/init.d/router_proxy
    
    # Enable and start service
    /etc/init.d/router_proxy enable
    /etc/init.d/router_proxy start
else
    echo "Warning: router_proxy.init not found, skipping service installation"
fi

# Configure uhttpd for web UI
echo "Configuring web server..."
uci set uhttpd.router_app=uhttpd
uci set uhttpd.router_app.listen_http='0.0.0.0:8081'
uci set uhttpd.router_app.home='/www/router-app'
uci set uhttpd.router_app.index_page='index.html'
uci commit uhttpd
/etc/init.d/uhttpd restart

# Disable LAN IPv6 to prevent DNS/traffic leaks bypassing passwall2's IPv4-only TPROXY
echo "Disabling LAN IPv6 to prevent leaks..."
uci set dhcp.lan.dhcpv6='disabled'
uci set dhcp.lan.ra='disabled'
uci set dhcp.lan.ndp='disabled'
uci -q delete network.lan.ip6assign
uci -q delete network.lan.ipaddr6
uci commit dhcp
uci commit network
ip -6 addr flush dev br-lan scope global 2>/dev/null
sysctl -w net.ipv6.conf.br-lan.disable_ipv6=1 >/dev/null 2>&1
sysctl -w net.ipv6.conf.br-lan.accept_ra=0 >/dev/null 2>&1
/etc/init.d/odhcpd reload 2>/dev/null
/etc/init.d/dnsmasq reload 2>/dev/null
echo "LAN IPv6 disabled"

echo ""
echo "=== Installation Complete ==="
echo "Python API is running on port 8080"
echo "Web UI is available at http://192.168.1.1:8081"
echo ""
echo "Service commands:"
echo "  /etc/init.d/router_proxy start|stop|restart|status"
echo "  /etc/init.d/router_proxy enable|disable"
