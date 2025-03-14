#!/bin/bash

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Set variables
SERVICE_NAME="telegram_bot"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SERVICE_FILE="${SERVICE_NAME}.service"
ENV_FILE="${SCRIPT_DIR}/.env"

# Check for required environment variables
required_vars=(
    "TELEGRAM_BOT_TOKEN"
    "TELEGRAM_API_ID"
    "TELEGRAM_API_HASH"
)

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env file not found at $ENV_FILE"
    echo "Please create .env file with required environment variables:"
    printf '%s\n' "${required_vars[@]}" | sed 's/^/- /'
    exit 1
fi

# Source .env file
source "$ENV_FILE"

# Check for required environment variables
missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    echo "❌ Error: Missing required environment variables:"
    printf '%s\n' "${missing_vars[@]}" | sed 's/^/- /'
    exit 1
fi

# Check if service already exists and stop it
if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo "Service is already running. Stopping it first..."
    systemctl stop ${SERVICE_NAME}
fi

if systemctl is-enabled --quiet ${SERVICE_NAME}; then
    echo "Service is already enabled. Disabling it first..."
    systemctl disable ${SERVICE_NAME}
fi

# Copy service file
echo "Installing service file..."
cp "${SCRIPT_DIR}/${SERVICE_FILE}" /etc/systemd/system/ || {
    echo "Failed to copy service file"
    exit 1
}

# Set proper permissions
chmod 644 /etc/systemd/system/${SERVICE_FILE} || {
    echo "Failed to set service file permissions"
    exit 1
}

# Create symlink to .env file if it doesn't exist
if [ ! -f "/etc/default/${SERVICE_NAME}" ]; then
    ln -s "$ENV_FILE" "/etc/default/${SERVICE_NAME}" || {
        echo "Failed to create environment file symlink"
        exit 1
    }
fi

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload || {
    echo "Failed to reload systemd"
    exit 1
}

# Enable service
echo "Enabling service..."
systemctl enable ${SERVICE_NAME} || {
    echo "Failed to enable service"
    exit 1
}

# Start service
echo "Starting service..."
systemctl start ${SERVICE_NAME} || {
    echo "Failed to start service"
    exit 1
}

# Wait for service to start
echo "Waiting for service to start..."
sleep 5

# Check status
echo "Checking service status..."
if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo "✅ Installation successful! The bot service is now running."
    echo
    echo "Service Status:"
    systemctl status ${SERVICE_NAME} --no-pager
    echo
    echo "Use these commands to manage the service:"
    echo "  sudo systemctl start ${SERVICE_NAME}    # Start the bot"
    echo "  sudo systemctl stop ${SERVICE_NAME}     # Stop the bot"
    echo "  sudo systemctl restart ${SERVICE_NAME}  # Restart the bot"
    echo "  sudo systemctl status ${SERVICE_NAME}   # Check bot status"
    echo
    echo "View logs with:"
    echo "  sudo journalctl -u ${SERVICE_NAME} -f   # Follow logs"
    echo "  sudo journalctl -u ${SERVICE_NAME} -n 50   # Last 50 lines"
    exit 0
else
    echo "❌ Service installation failed or service is not running."
    echo "Check the logs for more information:"
    journalctl -u ${SERVICE_NAME} --no-pager -n 50
    exit 1
fi