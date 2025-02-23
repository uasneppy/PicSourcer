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

# Check if service already exists
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

# Check status
echo "Checking service status..."
systemctl status ${SERVICE_NAME}

# Verify service is running
if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo "✅ Installation successful! The bot will now start automatically with the system."
    echo
    echo "Use these commands to manage the service:"
    echo "  sudo systemctl start ${SERVICE_NAME}    # Start the bot"
    echo "  sudo systemctl stop ${SERVICE_NAME}     # Stop the bot"
    echo "  sudo systemctl restart ${SERVICE_NAME}  # Restart the bot"
    echo "  sudo systemctl status ${SERVICE_NAME}   # Check bot status"
    exit 0
else
    echo "❌ Service installation failed. Please check the logs above for errors."
    exit 1
fi