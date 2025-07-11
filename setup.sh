#!/bin/bash

# Kukaj.fi Video Downloader Setup Script

echo "Kukaj.fi Video Downloader Setup"
echo "================================"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip3 first."
    exit 1
fi

echo "✅ pip3 found"

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Python dependencies installed successfully"
else
    echo "❌ Failed to install Python dependencies"
    exit 1
fi

# Check if Chrome is installed
if command -v google-chrome &> /dev/null; then
    echo "✅ Google Chrome found"
elif command -v chromium-browser &> /dev/null; then
    echo "✅ Chromium browser found"
elif command -v chromium &> /dev/null; then
    echo "✅ Chromium found"
else
    echo "⚠️  Chrome/Chromium not found. Please install Chrome or Chromium browser."
    echo "   The script will try to work but might fail."
fi

# Check if FFmpeg is installed
if command -v ffmpeg &> /dev/null; then
    echo "✅ FFmpeg found: $(ffmpeg -version | head -n 1)"
else
    echo "⚠️  FFmpeg not found. Install it for better download performance:"
    echo "   macOS: brew install ffmpeg"
    echo "   Linux: sudo apt install ffmpeg"
    echo "   The script will use Python fallback method."
fi

echo ""
echo "Setup complete! 🎉"
echo ""
echo "Usage:"
echo "  python3 kukaj_downloader.py <url>                    # Downloads .m3u8 file"
echo "  python3 kukaj_downloader.py <url> --mp4             # Downloads and converts to MP4"
echo "  python3 kukaj_downloader.py <url> -o <filename>     # Custom output filename"
echo ""
echo "Examples:"
echo "  python3 kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04"
echo "  python3 kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04 --mp4"
echo "  python3 kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04 -o episode.m3u8"
echo ""
echo "To test the setup, run:"
echo "  python3 test_downloader.py" 