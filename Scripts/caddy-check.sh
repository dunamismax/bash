#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# caddy_check.sh - A simple troubleshooting script to check Caddy's status
#                  and gather untruncated logs.
# -----------------------------------------------------------------------------
# Description:
#   1) Verifies whether Caddy service is active.
#   2) Displays a detailed status report from systemctl.
#   3) Shows Caddy's full journal logs (untruncated).
#   4) Optionally, if /var/log/caddy/caddy.log exists, prints its contents as well.
#
# Usage:
#   ./caddy_check.sh
#   (Run as root or via sudo to ensure full journal access if needed.)
#
# -----------------------------------------------------------------------------
set -Eeuo pipefail

trap 'echo "[ERROR] Script failed at line $LINENO. See above for details." >&2' ERR

# Optional: If your system logs to /var/log/caddy/caddy.log, set this path
CADDY_LOG_FILE="/var/log/caddy/caddy.log"

echo "============================="
echo "  Caddy Service Check Script"
echo "============================="
echo

# 1) Check if systemd recognizes the caddy service
if ! systemctl list-unit-files | grep -q "^caddy.service"; then
  echo "[INFO] caddy.service not found among systemd unit files."
  echo "       Is Caddy installed and managed by systemd on this system?"
  exit 1
fi

# 2) Display systemctl status
echo "---------- systemctl caddy status ----------"
systemctl status caddy.service || true
echo "--------------------------------------------"
echo

# 3) Display full journal logs for caddy (untruncated)
echo "---------- journalctl caddy logs (full) ----------"
# --no-pager: don’t page the output
# --no-limit: show all lines (untruncated)
journalctl -u caddy.service --no-pager --no-limit || true
echo "--------------------------------------------------"
echo

# 4) If a dedicated caddy log file exists, show the last few hundred lines
if [[ -f "$CADDY_LOG_FILE" ]]; then
  echo "---------- /var/log/caddy/caddy.log (untruncated) ----------"
  cat "$CADDY_LOG_FILE"
  echo "------------------------------------------------------------"
else
  echo "[INFO] No dedicated caddy log file found at $CADDY_LOG_FILE."
fi

echo
echo "[INFO] Caddy service check completed."