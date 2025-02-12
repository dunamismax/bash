#!/usr/bin/env bash
# memory.sh – Memory usage block for i3blocks

awk '
  /MemTotal/ { total = $2 }
  /MemAvailable/ { avail = $2 }
  END {
    used = total - avail;
    pct = (used / total) * 100;
    # Print full text and short text
    printf "Mem: %.1f%%\n", pct;
    printf "%.0f%%\n", pct;
  }
' /proc/meminfo
