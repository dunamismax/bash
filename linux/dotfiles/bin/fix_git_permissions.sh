#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

# Directory containing your repositories
BASE_DIR="/home/sawyer/github"

# Desired permissions
DIR_PERMISSIONS="755"  # Directories: rwx for owner, rx for group/others
FILE_PERMISSIONS="644" # Files: rw for owner, r for group/others

# --------------------------------------
# FUNCTIONS
# --------------------------------------

# Function to set permissions on a .git directory
fix_git_permissions() {
    local git_dir="$1"
    echo "Setting permissions for $git_dir"

    # Set permissions for the .git directory itself
    chmod "$DIR_PERMISSIONS" "$git_dir"

    # Set permissions for subdirectories inside .git
    find "$git_dir" -type d -exec chmod "$DIR_PERMISSIONS" {} \;

    # Set permissions for files inside .git
    find "$git_dir" -type f -exec chmod "$FILE_PERMISSIONS" {} \;

    echo "Permissions fixed for $git_dir"
}

# --------------------------------------
# SCRIPT START
# --------------------------------------

# Ensure BASE_DIR exists
if [[ ! -d "$BASE_DIR" ]]; then
    echo "Error: Base directory $BASE_DIR does not exist."
    exit 1
fi

echo "Starting permission fixes in $BASE_DIR..."

# Iterate through each subfolder in BASE_DIR
for repo in "$BASE_DIR"/*; do
    # Check if the subfolder contains a .git directory
    if [[ -d "$repo/.git" ]]; then
        fix_git_permissions "$repo/.git"
    else
        echo "Skipping $repo (not a git repository)"
    fi
done

echo "Permission fixes completed for all repositories in $BASE_DIR."

exit 0
