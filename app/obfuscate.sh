#!/bin/bash
set -e

function on_error {
    echo "Error occurred in command: $BASH_COMMAND"
    exit 1
}

trap on_error ERR

echo "Registration pyarmor"
pyarmor reg ../etc/pyarmor/pyarmor-regfile-5235.zip

rm -rf ./dist
pyarmor -d gen --output ./dist --enable-bcc --obf-code 2 --recursive main.py resource_path.py router  2>&1 | tee pyarmor_log.log

if [ "$(cat pyarmor_log.log | grep -c "ERROR ")" -gt 0 ]; then
    echo "PyArmor obfuscation failed!"
    exit 1
fi

echo "Obfuscation completed successfully!"
