#!/usr/bin/env bash
# network.sh – Network block for i3blocks: display default interface IP

# Determine the default interface by looking up a route to 8.8.8.8
iface=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $5; exit}')
if [ -n "$iface" ]; then
    # Extract the IPv4 address (remove the CIDR suffix)
    ip=$(ip addr show "$iface" 2>/dev/null | awk '/inet / { sub(/\/.*/, "", $2); print $2; exit }')
    if [ -n "$ip" ]; then
        printf "Net: %s\n" "$ip"
        printf "%s\n" "$ip"
    else
        printf "Net: no IP\n"
        printf "no IP\n"
    fi
else
    printf "Net: down\n"
    printf "down\n"
fi
