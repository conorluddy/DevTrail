#!/bin/bash

# Log file in the same directory as the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_FILE="$SCRIPT_DIR/log.json"

# Function to display usage
usage() {
    echo "Usage: $0 -m <message> [-t <tags>] [-y]"
    echo "  -m <message>  The log message"
    echo "  -t <tags>     Optional comma-separated tags"
    echo "  -y            Set the log date to yesterday at 18:00"
    exit 1
}

# Initialize variables
MESSAGE=""
TAGS=""
USE_YESTERDAY=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m)
            shift
            MESSAGE="$1"
            ;;
        -t)
            shift
            TAGS="$1"
            ;;
        -y)
            USE_YESTERDAY=true
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
    shift
done


# Check if message is provided
if [ -z "$MESSAGE" ]; then
    echo "Error: Message is required"
    usage
fi

# Get current timestamp or yesterday's timestamp
if [ "$USE_YESTERDAY" = true ]; then
    TIMESTAMP=$(date -u -v-1d -v18H -v0M -v0S +"%Y-%m-%dT%H:%M:%SZ")
else
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
fi
# If using on linux:  TIMESTAMP=$(date -u -d "yesterday 18:00:00" +"%Y-%m-%dT%H:%M:%SZ")

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

echo "Log entry added successfully!"

# Git operations
git -C "$SCRIPT_DIR" add "$LOG_FILE"
git -C "$SCRIPT_DIR" commit -m "Log entry: $MESSAGE"
git -C "$SCRIPT_DIR" push origin main

