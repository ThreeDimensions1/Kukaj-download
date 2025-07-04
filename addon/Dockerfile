ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install dependencies
RUN apk update && apk add --no-cache \
    python3 \
    python3-dev \
    py3-pip \
    chromium \
    chromium-chromedriver \
    ffmpeg \
    gcc \
    musl-dev \
    linux-headers

# Set up Python environment
ENV PYTHONUNBUFFERED=1
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV CHROME_BIN=/usr/bin/chromium-browser

# Copy requirements and install Python packages
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Copy application files
COPY . /app
WORKDIR /app

# Create downloads directory
RUN mkdir -p /app/downloads

# Make run script executable
COPY run.sh /
RUN chmod a+x /run.sh

EXPOSE 8080

# Start the application
CMD ["/run.sh"] 