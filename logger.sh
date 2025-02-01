#!/bin/bash

# Set the target directory where the log file and Git repository are located
TARGET_DIR="/Users/conor/Development/DevTrail"

# Log file in the target directory
LOG_FILE="$TARGET_DIR/log.json"

# Colors and formatting
BOLD='\033[1m'
GREEN='\033[0;32m'
NC='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to display usage
usage() {
    echo -e "${BOLD}Usage: devlog${NC}"
    echo "Run this command to start the interactive logging process."
    exit 1
}

# Function to display a styled header
display_header() {
    echo -e "\n${BOLD}${NC}======= DevTrail Logger =======${NC}\n"
}

# Function to prompt for message and tags
prompt_for_log() {
    echo -e "${BOLD}Enter log message ${YELLOW}(or 'q' to quit)${NC}:"
    read -e MESSAGE
    if [[ "$MESSAGE" == "q" ]]; then
        echo -e "\n${YELLOW}Exiting logger.${NC}"
        exit 0
    fi
    echo -e "${BOLD}Enter tags ${YELLOW}(comma-separated, press enter for none)${NC}:"
    read -e TAGS
}

# Function to display last log timestamp
display_last_log() {
    if [ -f "$LOG_FILE" ]; then
        LAST_LOG=$(jq -r '.logs[-1].timestamp' "$LOG_FILE")
        if [ "$LAST_LOG" != "null" ]; then
            FORMATTED_DATE=$(date -jf "%Y-%m-%dT%H:%M:%SZ" "$LAST_LOG" "+%H:%M %d/%m/%Y")
            echo -e "${BOLD}Last log:${NC} ${GREEN}$FORMATTED_DATE${NC}"
        else
            echo -e "${YELLOW}No previous logs found.${NC}"
        fi
    else
        echo -e "${YELLOW}No log file found.${NC}"
    fi
    echo -e "${NC}-----------------------------------${NC}"
}

# Main loop
while true; do
    clear
    display_header
    display_last_log

    # Reset variables
    MESSAGE=""
    TAGS=""

    # Prompt for log details
    prompt_for_log

    # Check if message is provided
    if [ -z "$MESSAGE" ]; then
        echo -e "\n${RED}Error: Message is required${NC}"
        sleep 2
        continue
    fi

    # Get current timestamp
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Prepare the new log entry
    NEW_ENTRY=$(cat <<EOF
{
  "timestamp": "$(echo $TIMESTAMP | sed 's/"/\\"/g')",
  "message": $(printf '%s' "$MESSAGE" | jq -Rs .),
  "tags": [$(echo $TAGS | sed 's/[[:space:]]*,[[:space:]]*/","/g; s/^/"/; s/$/"/')]
}
EOF
    )

    # Initialize log file if it doesn't exist or is empty
    if [ ! -s "$LOG_FILE" ]; then
        echo '{"logs":[]}' > "$LOG_FILE"
    fi

    # Add the new entry to the log file
    TMP_FILE=$(mktemp)
    jq --argjson new_entry "$NEW_ENTRY" '.logs += [$new_entry]' "$LOG_FILE" > "$TMP_FILE" && mv "$TMP_FILE" "$LOG_FILE"

    # Git operations
    if git -C "$TARGET_DIR" rev-parse --is-inside-work-tree > /dev/null 2>&1; then
        git -C "$TARGET_DIR" add "$LOG_FILE"
        git -C "$TARGET_DIR" commit -m "Log entry: $MESSAGE"
        git -C "$TARGET_DIR" push origin main
        echo -e "\n${GREEN}Log entry added and pushed to repository.${NC}"
    else
        echo -e "\n${RED}Error: Target directory is not a Git repository. Git operations failed.${NC}"
    fi

    echo -e "${NC}-----------------------------------${NC}"
    echo -e "${YELLOW}Screen will refresh in 2 seconds...${NC}"
    sleep 2
done