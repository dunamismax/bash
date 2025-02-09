#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: docker_manager.sh
# Description: An advanced interactive Docker container and Docker Compose
#              manager that lets you list, start, stop, remove, and inspect
#              containers and images, and also manage Docker Compose projects.
#              The interface is fully interactive with Nord‑themed color coding
#              and progress bars.
#
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./advanced_docker_manager.sh
#
# Requirements:
#   • Docker and docker-compose must be installed.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'echo -e "\n${NORD11}An error occurred at line ${LINENO}.${NC}"; exit 1' ERR

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escapes)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark Background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light Gray (Text)
NORD7='\033[38;2;143;188;187m'   # Teal (Success/Info)
NORD8='\033[38;2;136;192;208m'   # Accent Blue (Headings)
NORD11='\033[38;2;191;97;106m'   # Red (Errors)
NORD12='\033[38;2;208;135;112m'  # Orange (Warnings)
NORD14='\033[38;2;163;190;140m'  # Green (Labels/Values)
NC='\033[0m'                    # Reset Color

# ------------------------------------------------------------------------------
# Global Arrays
# ------------------------------------------------------------------------------
declare -a container_ids
declare -A image_ids

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
print_header() {
    local title="${1:-Advanced Docker Manager}"
    clear
    echo -e "${NORD8}============================================${NC}"
    echo -e "${NORD8}  ${title}  ${NC}"
    echo -e "${NORD8}============================================${NC}"
}

print_divider() {
    echo -e "${NORD8}--------------------------------------------${NC}"
}

progress_bar() {
    local message="$1"
    local duration="${2:-3}"
    local steps=50
    local sleep_time=$(echo "$duration / $steps" | bc -l)
    echo -ne "${NORD8}${message} ["
    for ((i=0; i<steps; i++)); do
        echo -ne "█"
        sleep "$sleep_time"
    done
    echo -e "]${NC}"
}

# ------------------------------------------------------------------------------
# Docker Container Manager Functions
# ------------------------------------------------------------------------------
list_docker_containers() {
    container_ids=()
    local containers
    mapfile -t containers < <(docker ps -a --format "{{.ID}} {{.Names}} {{.Status}} {{.Image}}")
    if [[ ${#containers[@]} -eq 0 ]]; then
        echo -e "${NORD12}No Docker containers found.${NC}"
        return 1
    fi
    local i=1
    for entry in "${containers[@]}"; do
        local id
        id=$(echo "$entry" | awk '{print $1}')
        local name
        name=$(echo "$entry" | awk '{print $2}')
        local image
        image=$(echo "$entry" | awk '{print $NF}')
        local status_raw
        status_raw=$(echo "$entry" | cut -d' ' -f3-)
        local status
        if echo "$status_raw" | grep -q "Up"; then
            status="${NORD14}${status_raw}${NC}"
        else
            status="${NORD12}${status_raw}${NC}"
        fi
        printf "${NORD8}[%d]${NC} ${NORD4}%s${NC} => %s (Image: %s)\n" "$i" "$name" "$status" "$image"
        container_ids[i]="$id"
        ((i++))
    done
}

start_container() {
    list_docker_containers
    read -rp "Enter container number to start: " num
    if [[ -z "${container_ids[num]:-}" ]]; then
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi
    local id="${container_ids[num]}"
    progress_bar "Starting container" 3
    docker start "$id" && echo -e "${NORD14}Container started successfully.${NC}" || echo -e "${NORD11}Failed to start container.${NC}"
    read -rp "Press Enter to continue..." dummy
}

stop_container() {
    list_docker_containers
    read -rp "Enter container number to stop: " num
    if [[ -z "${container_ids[num]:-}" ]]; then
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi
    local id="${container_ids[num]}"
    progress_bar "Stopping container" 3
    docker stop "$id" && echo -e "${NORD14}Container stopped successfully.${NC}" || echo -e "${NORD11}Failed to stop container.${NC}"
    read -rp "Press Enter to continue..." dummy
}

remove_container() {
    list_docker_containers
    read -rp "Enter container number to remove: " num
    if [[ -z "${container_ids[num]:-}" ]]; then
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi
    local id="${container_ids[num]}"
    progress_bar "Removing container" 3
    docker rm "$id" && echo -e "${NORD14}Container removed successfully.${NC}" || echo -e "${NORD11}Failed to remove container.${NC}"
    read -rp "Press Enter to continue..." dummy
}

inspect_container() {
    list_docker_containers
    read -rp "Enter container number to inspect: " num
    if [[ -z "${container_ids[num]:-}" ]]; then
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi
    local id="${container_ids[num]}"
    docker inspect "$id" | less
}

container_manager_menu() {
    while true; do
        print_header "Docker Container Manager"
        echo -e "${NORD14}[1]${NC} List Containers"
        echo -e "${NORD14}[2]${NC} Start Container"
        echo -e "${NORD14}[3]${NC} Stop Container"
        echo -e "${NORD14}[4]${NC} Remove Container"
        echo -e "${NORD14}[5]${NC} Inspect Container"
        echo -e "${NORD14}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " choice
        case "$choice" in
            1)
                list_docker_containers
                read -rp "Press Enter to continue..." dummy
                ;;
            2)
                start_container
                ;;
            3)
                stop_container
                ;;
            4)
                remove_container
                ;;
            5)
                inspect_container
                ;;
            0)
                break
                ;;
            *)
                echo -e "${NORD12}Invalid option. Please try again.${NC}"
                sleep 1
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# Docker Image Manager Functions
# ------------------------------------------------------------------------------
list_docker_images() {
    local images
    mapfile -t images < <(docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}")
    if [[ ${#images[@]} -eq 0 ]]; then
        echo -e "${NORD12}No Docker images found.${NC}"
        return 1
    fi
    local i=1
    image_ids=()
    for entry in "${images[@]}"; do
        local repo_tag
        repo_tag=$(echo "$entry" | awk '{print $1}')
        local id
        id=$(echo "$entry" | awk '{print $2}')
        printf "${NORD8}[%d]${NC} %s (ID: %s)\n" "$i" "$repo_tag" "$id"
        image_ids[$i]="$id"
        ((i++))
    done
}

remove_docker_image() {
    list_docker_images
    read -rp "Enter image number to remove: " num
    if [[ -z "${image_ids[$num]:-}" ]]; then
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi
    local id="${image_ids[$num]}"
    progress_bar "Removing image" 3
    docker rmi "$id" && echo -e "${NORD14}Image removed successfully.${NC}" || echo -e "${NORD11}Failed to remove image.${NC}"
    read -rp "Press Enter to continue..." dummy
}

pull_docker_image() {
    read -rp "Enter image name (e.g., ubuntu:latest): " img
    if [[ -z "$img" ]]; then
        echo -e "${NORD12}Image name cannot be empty.${NC}"
        return 1
    fi
    progress_bar "Pulling image" 5
    docker pull "$img" && echo -e "${NORD14}Image pulled successfully.${NC}" || echo -e "${NORD11}Failed to pull image.${NC}"
    read -rp "Press Enter to continue..." dummy
}

image_manager_menu() {
    while true; do
        print_header "Docker Image Manager"
        echo -e "${NORD14}[1]${NC} List Docker Images"
        echo -e "${NORD14}[2]${NC} Remove Docker Image"
        echo -e "${NORD14}[3]${NC} Pull Docker Image"
        echo -e "${NORD14}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " choice
        case "$choice" in
            1)
                list_docker_images
                read -rp "Press Enter to continue..." dummy
                ;;
            2)
                remove_docker_image
                ;;
            3)
                pull_docker_image
                ;;
            0)
                break
                ;;
            *)
                echo -e "${NORD12}Invalid option. Please try again.${NC}"
                sleep 1
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# Docker Compose Manager Functions
# ------------------------------------------------------------------------------
docker_compose_manager() {
    read -rp "Enter the directory containing docker-compose.yml: " compose_dir
    if [[ ! -f "${compose_dir}/docker-compose.yml" ]]; then
        echo -e "${NORD12}docker-compose.yml not found in ${compose_dir}.${NC}"
        return 1
    fi
    pushd "$compose_dir" >/dev/null || return 1
    while true; do
        print_header "Docker Compose Manager"
        echo -e "${NORD14}Project Directory: ${compose_dir}${NC}"
        print_divider
        echo -e "${NORD14}[1]${NC} docker-compose up (detached)"
        echo -e "${NORD14}[2]${NC} docker-compose down"
        echo -e "${NORD14}[3]${NC} docker-compose build"
        echo -e "${NORD14}[4]${NC} docker-compose logs"
        echo -e "${NORD14}[5]${NC} docker-compose restart"
        echo -e "${NORD14}[0]${NC} Return to Main Menu"
        read -rp "Enter your choice: " dc_choice
        case "$dc_choice" in
            1)
                progress_bar "Bringing services up" 5
                docker-compose up -d || echo -e "${NORD11}Failed to start services.${NC}"
                ;;
            2)
                progress_bar "Taking services down" 3
                docker-compose down || echo -e "${NORD11}Failed to take services down.${NC}"
                ;;
            3)
                progress_bar "Building services" 5
                docker-compose build || echo -e "${NORD11}Failed to build services.${NC}"
                ;;
            4)
                docker-compose logs --tail=20
                read -rp "Press Enter to continue..." dummy
                ;;
            5)
                progress_bar "Restarting services" 3
                docker-compose restart || echo -e "${NORD11}Failed to restart services.${NC}"
                ;;
            0)
                break
                ;;
            *)
                echo -e "${NORD12}Invalid selection.${NC}"
                sleep 1
                ;;
        esac
    done
    popd >/dev/null || return 1
}

# ------------------------------------------------------------------------------
# Main Menu
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        print_header "Advanced Docker Manager"
        echo -e "${NORD14}[1]${NC} Docker Container Manager"
        echo -e "${NORD14}[2]${NC} Docker Image Manager"
        echo -e "${NORD14}[3]${NC} Docker Compose Manager"
        echo -e "${NORD14}[q]${NC} Quit"
        print_divider
        read -rp "Enter your choice: " main_choice
        case "${main_choice,,}" in
            1) container_manager_menu ;;
            2) image_manager_menu ;;
            3) docker_compose_manager ;;
            q) echo -e "${NORD14}Goodbye!${NC}"; exit 0 ;;
            *) echo -e "${NORD12}Invalid selection. Please try again.${NC}"; sleep 1 ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
main() {
    # Check prerequisites: docker and docker-compose.
    if ! command -v docker &>/dev/null; then
        echo -e "${NORD11}Docker is not installed. Please install Docker and try again.${NC}"
        exit 1
    fi
    if ! command -v docker-compose &>/dev/null; then
        echo -e "${NORD11}docker-compose is not installed. Please install docker-compose and try again.${NC}"
        exit 1
    fi

    main_menu
}

# ------------------------------------------------------------------------------
# Execute Main if Script is Run Directly
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi