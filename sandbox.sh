#!/bin/bash
# Launch Claude Code in Docker sandbox

MODE=${1:-"safe"}
CONTAINER_NAME="pr-review-agent-sandbox"

# Determine the command based on mode
if [ "$MODE" = "full" ]; then
    echo "WARNING: Running in full trust mode - all commands allowed"
    CLAUDE_CMD="claude --dangerously-skip-permissions"
elif [ "$MODE" = "shell" ]; then
    echo "Opening container shell (run 'claude' to start Claude Code)"
    CLAUDE_CMD="bash"
else
    echo "Running in safe mode with restricted permissions"
    CLAUDE_CMD="claude"
fi

mkdir -p .claude/profiles

if [ "$MODE" = "full" ]; then
    cp .claude/profiles/full-trust.json .claude/settings.local.json 2>/dev/null || true
else
    cp .claude/profiles/safe-mode.json .claude/settings.local.json 2>/dev/null || true
fi

# Check if container exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    # Container exists - check if it's running
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Attaching to running container..."
        docker exec -it "$CONTAINER_NAME" $CLAUDE_CMD
    else
        echo "Starting stopped container..."
        docker start "$CONTAINER_NAME"
        docker exec -it "$CONTAINER_NAME" $CLAUDE_CMD
    fi
else
    # Container doesn't exist - create it (without --rm for persistence)
    echo "Creating new container..."
    docker compose -f docker-compose.sandbox.yml build
    docker compose -f docker-compose.sandbox.yml run claude-sandbox $CLAUDE_CMD
fi
