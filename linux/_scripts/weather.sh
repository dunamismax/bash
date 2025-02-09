#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: weather.sh
# Description: An advanced interactive weather information fetcher that auto‐
#              detects your location (via IP geolocation), retrieves current
#              weather data from the OpenWeatherMap API, and displays it in a
#              beautifully formatted Nord‑themed output. The script refreshes
#              data on demand.
#
# API Key (hardcoded): 833ee325c85a770fa1ed977927563495
#
# Usage:
#   ./nord_weather.sh
#
# Requirements:
#   • curl, jq
#
# Author: Your Name | License: MIT
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'echo -e "${NORD11}An error occurred at line ${LINENO}.${NC}"; exit 1' ERR

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escapes)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light Gray (text)
NORD7='\033[38;2;143;188;187m'   # Teal (success/info)
NORD8='\033[38;2;136;192;208m'   # Accent Blue (headings)
NORD11='\033[38;2;191;97;106m'   # Red (errors)
NORD14='\033[38;2;163;190;140m'  # Green (labels/values)
NC='\033[0m'                    # Reset Color

# ------------------------------------------------------------------------------
# Global Variables
# ------------------------------------------------------------------------------
API_KEY="833ee325c85a770fa1ed977927563495"
# Default units: metric (°C, m/s). Change to imperial for °F, mph.
UNITS="metric"

# ------------------------------------------------------------------------------
# Function: fetch_location
# Description: Auto-detects the user's zip code using IP geolocation.
# ------------------------------------------------------------------------------
fetch_location() {
    # Use ip-api.com to determine location; requires jq.
    local geo_json
    geo_json=$(curl -s "http://ip-api.com/json")
    local status
    status=$(echo "$geo_json" | jq -r '.status')
    if [[ "$status" != "success" ]]; then
        echo -e "${NORD11}Failed to detect location via IP geolocation.${NC}"
        exit 1
    fi
    ZIP=$(echo "$geo_json" | jq -r '.zip')
    CITY=$(echo "$geo_json" | jq -r '.city')
    REGION=$(echo "$geo_json" | jq -r '.regionName')
    COUNTRY=$(echo "$geo_json" | jq -r '.country')
}

# ------------------------------------------------------------------------------
# Function: fetch_weather
# Description: Retrieves current weather data from OpenWeatherMap API using the
#              detected ZIP code.
# ------------------------------------------------------------------------------
fetch_weather() {
    fetch_location
    # OpenWeatherMap API endpoint using ZIP code (assumed US)
    local url="http://api.openweathermap.org/data/2.5/weather?zip=${ZIP},us&appid=${API_KEY}&units=${UNITS}"
    weather_json=$(curl -s "$url")
    local cod
    cod=$(echo "$weather_json" | jq -r '.cod')
    if [[ "$cod" != "200" ]]; then
        local message
        message=$(echo "$weather_json" | jq -r '.message')
        echo -e "${NORD11}Error fetching weather data: $message${NC}"
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# Function: display_weather
# Description: Formats and displays the current weather information using the Nord
#              theme.
# ------------------------------------------------------------------------------
display_weather() {
    # Extract weather details from JSON using jq.
    local city country temp feels humidity pressure wind_speed wind_deg desc
    city=$(echo "$weather_json" | jq -r '.name')
    country=$(echo "$weather_json" | jq -r '.sys.country')
    temp=$(echo "$weather_json" | jq -r '.main.temp')
    feels=$(echo "$weather_json" | jq -r '.main.feels_like')
    humidity=$(echo "$weather_json" | jq -r '.main.humidity')
    pressure=$(echo "$weather_json" | jq -r '.main.pressure')
    wind_speed=$(echo "$weather_json" | jq -r '.wind.speed')
    wind_deg=$(echo "$weather_json" | jq -r '.wind.deg')
    desc=$(echo "$weather_json" | jq -r '.weather[0].description')

    # Display the header.
    clear
    echo -e "${NORD8}============================================${NC}"
    echo -e "${NORD8}         Current Weather in ${city}, ${ZIP} (${country})         ${NC}"
    echo -e "${NORD8}============================================${NC}"
    echo

    # Display weather details.
    printf "${NORD14}Location:       ${NC}%s, %s, %s\n" "$city" "$REGION" "$country"
    printf "${NORD14}Temperature:    ${NC}%s °C\n" "$temp"
    printf "${NORD14}Feels Like:     ${NC}%s °C\n" "$feels"
    printf "${NORD14}Humidity:       ${NC}%s%%\n" "$humidity"
    printf "${NORD14}Pressure:       ${NC}%s hPa\n" "$pressure"
    printf "${NORD14}Wind:           ${NC}%s m/s at %s°\n" "$wind_speed" "$wind_deg"
    printf "${NORD14}Condition:      ${NC}%s\n" "$(echo "$desc" | sed 's/\b\(.\)/\u\1/g')"
    echo
    echo -e "${NORD8}============================================${NC}"
}

# ------------------------------------------------------------------------------
# Function: interactive_loop
# Description: Provides an interactive menu to refresh weather data or exit.
# ------------------------------------------------------------------------------
interactive_loop() {
    while true; do
        fetch_weather
        display_weather
        echo -e "${NORD13}Press ${NORD14}[R]${NORD13} to refresh, ${NORD14}[Q]${NORD13} to quit.${NC}"
        read -rp "Your choice: " choice
        case "${choice,,}" in
            r)
                continue ;;
            q)
                echo -e "${NORD14}Goodbye!${NC}"
                exit 0 ;;
            *)
                echo -e "${NORD12}Invalid option. Please press 'R' to refresh or 'Q' to quit.${NC}"
                sleep 1 ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
main() {
    # Check dependencies: curl and jq.
    if ! command -v curl &>/dev/null; then
        echo -e "${NORD11}Error: curl is not installed. Please install curl and try again.${NC}"
        exit 1
    fi
    if ! command -v jq &>/dev/null; then
        echo -e "${NORD11}Error: jq is not installed. Please install jq and try again.${NC}"
        exit 1
    fi

    interactive_loop
}

# ------------------------------------------------------------------------------
# Execute Main if Script is Run Directly
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi