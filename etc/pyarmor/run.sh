#!/bin/bash

# register pyarmor
pip3 install pyarmor==8.2.9
pyarmor reg /workdir/pyarmor-regfile-5235.zip

# run obfuscate script:
cd /workdir
pyarmor -d gen --output ./dist  --enable-bcc  --private foo.py