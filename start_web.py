#!/usr/bin/env python3
"""
Simple startup script for Kukaj Video Downloader Web Interface
"""

import os
import sys
import webbrowser
import threading
import time

def open_browser():
    """Open browser after a short delay"""
    time.sleep(1.5)  # Wait for server to start
    webbrowser.open('http://localhost:8080')

def main():
    print("🚀 Starting Kukaj Video Downloader Web Interface")
    print("=" * 50)
    
    # Check if we're in a virtual environment
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("⚠️  Warning: Not in a virtual environment")
        print("   Consider running: source venv/bin/activate")
    
    # Check if required packages are installed
    try:
        import flask
        import flask_socketio
        from kukaj_downloader import KukajDownloader
        print("✅ All dependencies found")
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Run: pip install -r requirements.txt")
        return 1
    
    # Import and run the Flask app
    try:
        from app import app, socketio
        print("📍 Web interface will be available at: http://localhost:8080")
        print("🎬 Ready to download videos!")
        print("🌐 Opening browser...")
        print("=" * 50)
        
        # Open browser in a separate thread
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()
        
        # Run the app
        socketio.run(app, debug=False, host='0.0.0.0', port=8080)
        
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main()) 