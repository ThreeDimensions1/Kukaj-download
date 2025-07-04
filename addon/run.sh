#!/usr/bin/with-contenv bashio

# Get configuration from Home Assistant
PORT=$(bashio::config 'port')
HEADLESS=$(bashio::config 'headless')

# Log startup
bashio::log.info "Starting Kukaj Video Downloader..."
bashio::log.info "Port: ${PORT}"
bashio::log.info "Headless mode: ${HEADLESS}"

# Set environment variables
export PORT=${PORT}
export HEADLESS=${HEADLESS}

# Ensure downloads directory exists and is writable
mkdir -p /app/downloads
chmod 777 /app/downloads

# Start the application
cd /app
python3 app.py 