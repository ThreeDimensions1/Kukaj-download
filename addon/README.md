# Kukaj Video Downloader Add-on

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Supports aarch64 Architecture](https://img.shields.io/badge/aarch64-yes-green.svg)
![Supports amd64 Architecture](https://img.shields.io/badge/amd64-yes-green.svg)
![Supports armhf Architecture](https://img.shields.io/badge/armhf-yes-green.svg)
![Supports armv7 Architecture](https://img.shields.io/badge/armv7-yes-green.svg)
![Supports i386 Architecture](https://img.shields.io/badge/i386-yes-green.svg)

## About

Download videos from kukaj.fi with support for both M3U8 and MP4 formats. This add-on provides a beautiful web interface for downloading videos from the Kukaj streaming platform.

## Features

- 🎬 Download videos from kukaj.fi and other kukaj domains
- 📱 Beautiful responsive web interface
- 🎥 Support for both M3U8 and MP4 formats
- 📊 Real-time download progress
- 📁 Download history management
- 🔄 Automatic file cleanup
- 🌐 Multi-domain support (kukaj.io, kukaj.in, etc.)

## Installation

1. Add this repository to your Home Assistant add-on store
2. Install the "Kukaj Video Downloader" add-on
3. Configure the add-on (see configuration section below)
4. Start the add-on
5. Access the web interface through the "Web UI" button

## Configuration

```yaml
port: 8080
headless: true
```

### Option: `port`

The port the web interface will run on.

### Option: `headless`

Run Chrome in headless mode (without GUI). Set to `false` for debugging.

## Usage

1. Open the web interface from the add-on page
2. Enter a kukaj.fi video URL
3. Choose your preferred format (M3U8 or MP4)
4. Click "Download Video"
5. Monitor progress in real-time
6. Access downloaded files from the history section

## Supported URLs

- https://kukaj.fi/...
- https://serial.kukaj.fi/...
- https://kukaj.io/...
- https://kukaj.in/...
- And other kukaj domains

## Integration with Home Assistant

The add-on exposes a REST API that can be used with Home Assistant automations:

```yaml
# Example automation
automation:
  - alias: "Download Video"
    trigger:
      platform: webhook
      webhook_id: download_video
    action:
      service: rest_command.download_kukaj_video
      data:
        url: "{{ trigger.data.url }}"
        format: "mp4"
```

## Support

For issues and feature requests, please visit the [GitHub repository](https://github.com/yourusername/kukaj-downloader).

## License

This add-on is released under the MIT License. 