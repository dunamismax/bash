#!/usr/bin/env bash
# cpu.sh – Simple CPU usage block for i3blocks

# Try using mpstat (requires sysstat package)
if command -v mpstat >/dev/null 2>&1; then
    usage=$(mpstat 1 1 | awk '/Average/ {print 100 - $12}')
else
    # Fallback using top; note that this method may be less precise
    usage=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
fi

# Print full text and short text (both showing the usage percentage)
printf "CPU: %.1f%%\n" "$usage"
printf "%.0f%%\n" "$usage"
