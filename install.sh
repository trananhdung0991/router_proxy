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

# Set up extroot overlay on x86/x86_64:
#   - Fix GPT backup header to end of disk
#   - Create sda3 (or next free partition) in the free space
#   - Format ext4, copy /overlay, configure fstab extroot
#   - Reboot so next boot mounts the large overlay
# Returns 0 if extroot already active or not x86, exits 1 to reboot.
setup_extroot_x86() {
    ARCH=$(uname -m)
    if [ "$ARCH" != "x86_64" ] && [ "$ARCH" != "i686" ] && [ "$ARCH" != "x86" ]; then
        return 0
    fi

    # Find root device + disk
    ROOT_DEV=$(mount | awk '$3=="/"{print $1}' | head -1)
    case "$ROOT_DEV" in
        /dev/sd[a-z][0-9]*) DISK=${ROOT_DEV%%[0-9]*} ;;
        /dev/vd[a-z][0-9]*) DISK=${ROOT_DEV%%[0-9]*} ;;
        *) return 0 ;;
    esac

    # If overlay is already a separate large partition, nothing to do
    OVERLAY_DEV=$(mount | awk '$3=="/overlay"{print $1}' | head -1)
    if [ -n "$OVERLAY_DEV" ] && [ "$OVERLAY_DEV" != "$ROOT_DEV" ]; then
        OVERLAY_KB=$(df -k /overlay | awk 'NR==2{print $2}')
        if [ "$OVERLAY_KB" -gt 524288 ]; then
            echo "Extroot already active on $OVERLAY_DEV (${OVERLAY_KB}KB), skipping setup"
            return 0
        fi
    fi

    echo "Setting up extroot overlay on $DISK..."

    # Install tools
    if [ "$PKG_MANAGER" = "apk" ]; then
        apk add --allow-untrusted gdisk e2fsprogs block-mount bash 2>/dev/null || true
    else
        opkg install gdisk e2fsprogs block-mount 2>/dev/null || true
    fi

    if ! command -v gdisk > /dev/null 2>&1; then
        echo "Warning: gdisk not available, skipping extroot setup"
        return 0
    fi

    # Determine next free partition number
    LAST_PART=$(gdisk -l "$DISK" 2>/dev/null | awk '/^[[:space:]]*[0-9]/{print $1}' | grep -v '^128$' | sort -n | tail -1)
    OVERLAY_PARTNUM=$((LAST_PART + 1))
    OVERLAY_DEV_NEW="${DISK}${OVERLAY_PARTNUM}"

    # If target partition already exists and is large, it was pre-created — just use it
    if [ -b "$OVERLAY_DEV_NEW" ]; then
        PART_KB=$(( $(cat /sys/class/block/$(basename $OVERLAY_DEV_NEW)/size 2>/dev/null || echo 0) / 2 ))
        if [ "$PART_KB" -gt 524288 ]; then
            echo "$OVERLAY_DEV_NEW already exists and is large, formatting for overlay"
        else
            echo "$OVERLAY_DEV_NEW exists but is small, skip extroot"
            return 0
        fi
    else
        # Fix GPT backup header to end of disk so free space is visible
        echo "Fixing GPT backup header and creating $OVERLAY_DEV_NEW..."
        {
            printf "x\ne\nw\nY\n"
        } | gdisk "$DISK" > /dev/null 2>&1 || true

        # Check free space exists now
        FREE=$(gdisk -l "$DISK" 2>/dev/null | grep "^Total free space" | awk '{print $4}')
        if [ -z "$FREE" ] || [ "$FREE" -lt 1048576 ]; then
            echo "Not enough free space on $DISK for extroot, skipping"
            return 0
        fi

        # Create overlay partition in free space
        {
            printf "n\n%s\n\n\n8300\nw\nY\n" "$OVERLAY_PARTNUM"
        } | gdisk "$DISK" > /dev/null 2>&1

        # Rescan partition table
        partprobe "$DISK" 2>/dev/null || true
        sleep 2

        if [ ! -b "$OVERLAY_DEV_NEW" ]; then
            echo "Warning: $OVERLAY_DEV_NEW not visible after partitioning, skipping extroot"
            return 0
        fi
    fi

    echo "Formatting $OVERLAY_DEV_NEW as ext4..."
    mkfs.ext4 -L overlay "$OVERLAY_DEV_NEW" 2>&1

    echo "Copying current overlay to $OVERLAY_DEV_NEW..."
    mkdir -p /mnt/overlay
    mount "$OVERLAY_DEV_NEW" /mnt/overlay
    tar -C /overlay -cf - . | tar -C /mnt/overlay -xf - 2>/dev/null
    umount /mnt/overlay

    # Get UUID via tune2fs (blkid may not be available)
    OVERLAY_UUID=$(tune2fs -l "$OVERLAY_DEV_NEW" 2>/dev/null | awk '/Filesystem UUID/{print $3}')
    if [ -z "$OVERLAY_UUID" ]; then
        echo "Warning: could not read UUID from $OVERLAY_DEV_NEW"
        OVERLAY_UUID=""
    fi
    echo "Overlay UUID: $OVERLAY_UUID"

    # Configure fstab extroot
    uci -q delete fstab.extroot 2>/dev/null
    uci set fstab.extroot=mount
    uci set fstab.extroot.target=/overlay
    if [ -n "$OVERLAY_UUID" ]; then
        uci set fstab.extroot.uuid="$OVERLAY_UUID"
    else
        uci set fstab.extroot.device="$OVERLAY_DEV_NEW"
    fi
    uci set fstab.extroot.fstype=ext4
    uci set fstab.extroot.options="rw,noatime"
    uci set fstab.extroot.enabled=1
    uci set fstab.extroot.enabled_fsck=0
    uci commit fstab
    /etc/init.d/fstab enable

    echo ""
    echo "=== Extroot overlay configured on $OVERLAY_DEV_NEW ==="
    echo "Rebooting to activate overlay. Re-run install.sh after reboot to continue."
    sleep 3
    reboot
    exit 0
}

setup_extroot_x86

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
    PASSWALL_REPO="https://master.dl.sourceforge.net/project/openwrt-passwall-build/releases/packages-$VERSION_MAJOR_MINOR/$ARCH/passwall2/packages.adb"
    PASSWALL_PKG_REPO="https://master.dl.sourceforge.net/project/openwrt-passwall-build/releases/packages-$VERSION_MAJOR_MINOR/$ARCH/passwall_packages/packages.adb"
    CUSTOMFEEDS="/etc/apk/repositories.d/customfeeds.list"
    mkdir -p /etc/apk/repositories.d
    if ! grep -q "passwall2/packages.adb" "$CUSTOMFEEDS" 2>/dev/null; then
        echo "$PASSWALL_REPO" >> "$CUSTOMFEEDS"
    fi
    if ! grep -q "passwall_packages/packages.adb" "$CUSTOMFEEDS" 2>/dev/null; then
        echo "$PASSWALL_PKG_REPO" >> "$CUSTOMFEEDS"
    fi
    # Remove any stale bare URLs from /etc/apk/repositories
    sed -i '/passwall2/d' /etc/apk/repositories 2>/dev/null || true
    apk update --allow-untrusted 2>/dev/null || true
    if apk info luci-app-passwall2 > /dev/null 2>&1; then
        echo "Passwall2 is already installed"
        # Ensure xray-core is installed even if passwall2 was already present
        apk info xray-core > /dev/null 2>&1 || apk add --allow-untrusted xray-core || true
    else
        # v2ray-geoip + v2ray-geosite are large (~20MB each); mount tmpfs so they
        # don't fill the root partition during install (overlay is large but apk
        # extracts to /usr/share/v2ray on root first if not pre-mounted)
        mkdir -p /usr/share/v2ray
        mount | grep -q '/usr/share/v2ray' || mount -t tmpfs -o size=400M tmpfs /usr/share/v2ray 2>/dev/null || true
        apk add --allow-untrusted luci-app-passwall2 xray-core || echo "Warning: passwall2/xray-core not available via apk, skipping"
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
