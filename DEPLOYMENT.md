# Router Proxy - OpenWrt Deployment Guide

## Quick Start

### 1. Build on PC
```bash
cd /home/dung/wp/router_proxy_pj/project/router_proxy

# Build WebUI
cd webUI/web/router-app
npm run build
cd ../../..

# Build application
./build.sh --openwrt
```

### 2. Copy to OpenWrt
```bash
scp -r install_package root@192.168.1.1:/tmp/
```

### 3. Install on OpenWrt
```bash
ssh root@192.168.1.1
cd /tmp/install_package
chmod +x install.sh
./install.sh
```

## Service Management

### Start/Stop Service
```bash
/etc/init.d/router_proxy start
/etc/init.d/router_proxy stop
/etc/init.d/router_proxy restart
/etc/init.d/router_proxy status
```

### Enable/Disable Auto-start
```bash
/etc/init.d/router_proxy enable   # Start on boot
/etc/init.d/router_proxy disable  # Don't start on boot
```

### View Logs
```bash
logread | grep router_proxy
```

## Access Points

- **API**: http://192.168.1.1:8080
- **Web UI**: http://192.168.1.1:8081

## Manual Installation Steps

If the automatic installer doesn't work:

### Install Dependencies
```bash
opkg update
opkg install python3 python3-pip
pip3 install flask flask-cors psutil
```

### Copy Application
```bash
mkdir -p /root/router_proxy
cp -r * /root/router_proxy/
```

### Install Service
```bash
cp router_proxy.init /etc/init.d/router_proxy
chmod +x /etc/init.d/router_proxy
/etc/init.d/router_proxy enable
/etc/init.d/router_proxy start
```

### Configure Web Server
```bash
mkdir -p /www/router-app
cp -r web/* /www/router-app/

uci set uhttpd.router_app=uhttpd
uci set uhttpd.router_app.listen_http='0.0.0.0:8081'
uci set uhttpd.router_app.home='/www/router-app'
uci set uhttpd.router_app.index_page='index.html'
uci commit uhttpd
/etc/init.d/uhttpd restart
```

## Troubleshooting

### Check if service is running
```bash
ps | grep python3
netstat -tulpn | grep :8080
```

### View service status
```bash
/etc/init.d/router_proxy status
```

### Restart service
```bash
/etc/init.d/router_proxy restart
```

### Check logs
```bash
logread -f | grep router_proxy
```

### Manual start (for debugging)
```bash
cd /root/router_proxy
python3 main.py
```

## Uninstall

```bash
/etc/init.d/router_proxy stop
/etc/init.d/router_proxy disable
rm -rf /root/router_proxy
rm -rf /www/router-app
rm /etc/init.d/router_proxy
uci delete uhttpd.router_app
uci commit uhttpd
/etc/init.d/uhttpd restart
```

## Update Deployment

```bash
# On PC
./build.sh --openwrt
scp -r install_package root@192.168.1.1:/tmp/

# On OpenWrt
ssh root@192.168.1.1
/etc/init.d/router_proxy stop
cd /tmp/install_package
cp -r router pyarmor_runtime_005235 main.py resource_path.py /root/router_proxy/
cp -r web/* /www/router-app/
/etc/init.d/router_proxy start
```
