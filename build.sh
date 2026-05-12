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
rm -rf install_package
mkdir install_package
cp -r app/dist/* install_package/
echo "Installation package is ready in 'install_package' directory."
mkdir install_package/web
cp -r webUI/web/router-app/dist/* install_package/web/

# Copy service init script
cp router_proxy.init install_package/
chmod +x install_package/router_proxy.init
echo "Service init script copied."

cp install.sh install_package/
chmod +x install_package/install.sh
echo "Installation script copied."

echo "Build script finished."