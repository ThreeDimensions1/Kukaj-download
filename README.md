# Kukaj Video Downloader

A Python script to download videos from kukaj domains (kukaj.fi, kukaj.io, kukaj.in, etc.) that are loaded as .m3u8 files via JavaScript.

## Features

- Handles JavaScript-loaded .m3u8 files with automatic delay handling
- Multiple extraction methods for finding .m3u8 URLs
- FFmpeg integration for high-quality downloads
- Fallback Python-based download method
- Automatic filename generation from URL
- Headless browser operation
- **Multi-domain support**: Automatically converts kukaj.io, kukaj.in, and other subdomains to kukaj.fi for compatibility

## Prerequisites

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install FFmpeg (Recommended)

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)

### 3. Install Chrome/Chromium Browser

The script uses Chrome WebDriver, so you need Chrome or Chromium browser installed.

## Usage

### Web Interface (Recommended)

A beautiful web interface is available for easier use:

```bash
python3 start_web.py
```

Then open your browser to: `http://localhost:8080`

**Features:**
- Modern, responsive interface
- Real-time download progress
- Automatic file list refresh (no manual refresh needed!)
- File management and download
- WebSocket-based live updates

### Command Line Interface

#### Basic Usage (Downloads .m3u8 file)

```bash
python kukaj_downloader.py <kukaj.fi_url>
```

#### Download as MP4

```bash
python kukaj_downloader.py <kukaj.fi_url> --mp4
```

#### With Custom Output Filename

```bash
python kukaj_downloader.py <kukaj.fi_url> -o <output_filename>
python kukaj_downloader.py <kukaj.fi_url> --mp4 -o <output_filename>
```

#### Examples

```bash
# Download .m3u8 file with automatic filename
python kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04

# Download and convert to MP4
python kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04 --mp4

# Works with other kukaj subdomains (automatically converted to kukaj.fi)
python kukaj_downloader.py https://serial.kukaj.io/hra-na-olihen/S03E04 --mp4
python kukaj_downloader.py https://serial.kukaj.in/hra-na-olihen/S03E04 

# Download .m3u8 with custom filename
python kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04 -o episode_S03E04.m3u8

# Download and convert to MP4 with custom filename
python kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04 --mp4 -o episode_S03E04.mp4

# Run with browser GUI visible (for debugging)
python kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04 --no-headless
```

#### Command Line Options

- `--mp4`: Convert to MP4 format (default: download .m3u8 file)
- `-o`, `--output`: Specify output filename
- `--no-headless`: Run browser with GUI visible (for debugging)
- `--help`: Show help message

## How It Works

1. **Page Loading**: Uses Selenium WebDriver to load the kukaj.fi page
2. **JavaScript Execution**: Waits for JavaScript to load the video (2-5 seconds delay)
3. **URL Extraction**: Searches for .m3u8 URLs using multiple methods:
   - Network performance logs
   - Page source analysis
   - Video element inspection
   - Source element checking
   - JavaScript execution to find video sources
4. **Download**: Based on the selected mode:
   - **Default (.m3u8)**: Downloads the .m3u8 playlist file directly
   - **MP4 mode (--mp4)**: Downloads and converts to MP4 using:
     - FFmpeg (preferred - faster and more reliable)
     - Python-based segment download (fallback)

## Troubleshooting

### Common Issues

1. **ChromeDriver execution error** (NEW FIX!)
   - If you see "Exec format error" or "Invalid ChromeDriver path", run:
   ```bash
   python3 fix_chromedriver.py
   ```
   This utility clears the WebDriver cache and reinstalls ChromeDriver properly.

2. **No .m3u8 URLs found**
   - The page might need more time to load
   - Check if the URL is correct and accessible
   - Some pages might have anti-bot protection
   - The script now has enhanced fallback mechanisms for difficult extractions

3. **FFmpeg not found**
   - Install FFmpeg using the instructions above
   - The script will automatically fallback to Python download

4. **Chrome driver issues**
   - The script automatically downloads ChromeDriver
   - Make sure Chrome/Chromium is installed
   - Use the `fix_chromedriver.py` utility if you encounter path issues

5. **Download fails**
   - Check your internet connection
   - The video might be geo-blocked
   - Try again as the issue might be temporary

### Debug Mode

To see what's happening during extraction, you can modify the script to run in non-headless mode:

```python
# In the script, change:
with KukajDownloader(headless=False) as downloader:
```

This will show the browser window so you can see what's happening.

## Notes

- The script respects the website's loading delays
- Downloaded videos are saved in MP4 format
- The script handles various .m3u8 playlist formats
- Large videos might take some time to download

## Legal Notice

This tool is for educational purposes only. Make sure you have permission to download content and respect the website's terms of service and copyright laws. 