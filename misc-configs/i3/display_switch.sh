#!/bin/bash

# Check if the external monitor is connected
if xrandr | grep -q "^DisplayPort-1 connected"; then
    # If external monitor is connected, turn off eDP and use DisplayPort-1
    xrandr --output eDP --off --output DisplayPort-1 --auto
else
    # If external monitor is not connected, use eDP
    xrandr --output eDP --auto --output DisplayPort-1 --off
fi