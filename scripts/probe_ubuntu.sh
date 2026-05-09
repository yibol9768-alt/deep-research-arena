#!/bin/bash
echo "=== distro ==="
lsb_release -a 2>/dev/null
echo
echo "=== /etc + /opt timestamps ==="
ls -ld /etc /opt /opt/deep_reserch 2>/dev/null
echo
echo "=== oldest venv ==="
ls -lt /opt/deep_reserch/.venv-camel/pyvenv.cfg 2>/dev/null
echo
echo "=== uptime / boot ==="
uptime
who -b 2>/dev/null
echo
echo "=== hostname / kernel ==="
hostname
uname -a
echo
echo "=== /etc/wsl.conf ==="
cat /etc/wsl.conf 2>/dev/null || echo "(none)"
