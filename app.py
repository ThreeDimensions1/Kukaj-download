#!/usr/bin/env python3
"""
Kukaj Video Downloader - Web Interface
Beautiful web UI for downloading videos from kukaj domains
"""

import os
import threading
import time
import atexit
import shutil
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
# Fix Socket.IO imports to ensure room parameter is recognized
from flask_socketio import SocketIO, emit, join_room, leave_room, rooms, disconnect
from kukaj_downloader import KukajDownloader, normalize_kukaj_url
from datetime import datetime
import json
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kukaj_downloader_secret_key'
# Improve Socket.IO configuration for better cross-device sync
socketio = SocketIO(app, 
                   cors_allowed_origins="*", 
                   ping_timeout=60,
                   ping_interval=25,
                   async_mode='threading')

# Download directory
DOWNLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'download_history.json')

# Store active downloads
active_downloads = {}
download_history = []

# Global download lock to prevent multiple simultaneous downloads
global_download_lock = threading.Lock()
current_download_session = None
download_start_time = None

def setup_downloads_directory():
    """Create and clean the downloads directory"""
    if os.path.exists(DOWNLOADS_DIR):
        # Clean the directory
        shutil.rmtree(DOWNLOADS_DIR)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    print(f"📁 Downloads directory ready: {DOWNLOADS_DIR}")

def cleanup_downloads_directory():
    """Clean up downloads directory on exit"""
    if os.path.exists(DOWNLOADS_DIR):
        try:
            shutil.rmtree(DOWNLOADS_DIR)
            print("🧹 Downloads directory cleaned")
        except Exception as e:
            print(f"⚠️ Error cleaning downloads directory: {e}")

def load_history():
    """Load download history from JSON file"""
    global download_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                download_history = json.load(f)
        else:
            download_history = []
    except Exception as e:
        print(f"⚠️ Error loading history: {e}")
        download_history = []

def save_history():
    """Save download history to JSON file"""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(download_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving history: {e}")

def add_to_history(url, filename, success=True, convert_to_mp4=False, source=None):
    """Add download to history"""
    global download_history
    # Extract movie/series name from URL
    from urllib.parse import urlparse
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip('/').split('/')
    
    # Generate display name
    if len(path_parts) >= 1 and path_parts[-1]:
        if len(path_parts) >= 2 and path_parts[-2] not in ['film', 'serial']:
            # For series URLs like /series-name/S01E01
            display_name = f"{path_parts[-2]} - {path_parts[-1]}"
        else:
            # For film URLs like /matrix
            display_name = path_parts[-1]
    else:
        display_name = "Unknown"
    
    # Clean display name
    display_name = re.sub(r'[_-]', ' ', display_name).title()
    
    # Remove any existing entry with the same URL to avoid duplicates
    download_history = [entry for entry in download_history if entry.get('url') != url]
    
    history_entry = {
        'url': url,
        'filename': filename,
        'display_name': display_name,
        'date': datetime.now().isoformat(),
        'success': success,
        'convert_to_mp4': convert_to_mp4,
        'source': source,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    download_history.insert(0, history_entry)  # Add to beginning
    
    # Keep only last 50 entries
    if len(download_history) > 50:
        download_history = download_history[:50]
    
    save_history()

# Initialize on startup
setup_downloads_directory()
load_history()

# Register cleanup function
atexit.register(cleanup_downloads_directory)

class WebDownloader(KukajDownloader):
    """Extended downloader with web interface integration"""
    
    def __init__(self, session_id, headless=True):
        self.session_id = session_id
        self.error_count = 0
        self.max_errors = 5
        try:
            super().__init__(headless)
        except Exception as e:
            self.emit_progress(f"❌ Failed to initialize browser: {str(e)}", "error")
            raise
    
    def emit_progress(self, message, status="info"):
        """Emit progress updates to the web interface"""
        try:
            # Emit to the specific client session
            socketio.emit(
                'download_progress',
                {
                    'message': message,
                    'status': status,
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                },
                room=self.session_id,
            )

            # Broadcast to all clients for the mini-status panel
            socketio.emit(
                'download_progress_global',
                {
                    'message': message,
                    'status': status,
                    'session_id': self.session_id,
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                },
            )

            # Basic error-counter logic
            if status == "error":
                self.error_count += 1
                if self.error_count >= self.max_errors:
                    socketio.emit(
                        'download_error_global',
                        {
                            'message': 'Too many errors, download aborted',
                            'session_id': self.session_id,
                        },
                    )
                    raise Exception("Maximum error count reached")
        except Exception as e:
            print(f"❌ Failed to emit progress: {e}")
    
    def close(self):
        """Override close with better error handling and force cleanup"""
        try:
            self.emit_progress("🧹 Cleaning up browser resources...", "info")
            super().close()
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
        
        # Force cleanup for ARM devices - always cleanup to prevent state pollution
        try:
            import subprocess
            import platform
            if 'arm' in platform.machine().lower() or 'aarch64' in platform.machine().lower():
                print("🔧 Force cleaning up Firefox processes on ARM device...")
                subprocess.run(['pkill', '-f', 'firefox'], stderr=subprocess.DEVNULL, timeout=5)
                # Also clean up any remaining playwright processes
                subprocess.run(['pkill', '-f', 'playwright'], stderr=subprocess.DEVNULL, timeout=5)
                # Give processes time to clean up
                time.sleep(2)
        except Exception as cleanup_err:
            print(f"⚠️ Force cleanup failed: {cleanup_err}")
    
    def reinitialize_browser(self):
        """Reinitialize browser to prevent state pollution"""
        try:
            self.emit_progress("🔄 Reinitializing browser for reliability...", "info")
            # Close existing browser
            self.close()
            # Wait a moment for cleanup
            time.sleep(1)
            # Reinitialize
            super().__init__(headless=True)
            self.emit_progress("✅ Browser reinitialized successfully", "info")
            return True
        except Exception as e:
            self.emit_progress(f"❌ Browser reinitialization failed: {str(e)}", "error")
            return False
    
    def download_video(self, url, output_filename=None, convert_to_mp4=False, source=None):
        """Override to add progress updates"""
        max_retries = 2
        retry_count = 0
        browser_reinitialized = False
        
        while retry_count <= max_retries:
            try:
                if retry_count > 0:
                    self.emit_progress(f"🔄 Retry attempt {retry_count}/{max_retries}...", "warning")
                    
                    # Reinitialize browser on ARM devices for better reliability
                    if retry_count == 1 and not browser_reinitialized:
                        import platform
                        if 'arm' in platform.machine().lower() or 'aarch64' in platform.machine().lower():
                            if self.reinitialize_browser():
                                browser_reinitialized = True
                            else:
                                self.emit_progress("⚠️ Browser reinitialization failed, continuing with existing browser", "warning")
                
                self.emit_progress("🔄 Starting download process...", "info")
            
                # Normalize the URL
                normalized_url, was_changed = normalize_kukaj_url(url)
                if was_changed:
                    self.emit_progress(f"🔄 URL normalized from {url}", "info")
                    self.emit_progress(f"📍 Using: {normalized_url}", "success")
                    url = normalized_url

                # Extract media URLs (m3u8 or mp4)
                self.emit_progress("🔍 Extracting video URLs...", "info")
                # Use the parent class method to avoid recursion
                media_urls = super().extract_media_urls(url, source)
            
                if not media_urls:
                    if retry_count < max_retries:
                        retry_count += 1
                        self.emit_progress(f"⚠️ No video URLs found, retrying... ({retry_count}/{max_retries})", "warning")
                        time.sleep(3)  # Wait before retry
                        continue
                    else:
                        # Only attempt TAP fallback after ALL retries have failed
                        if source and source.upper() == 'TAP':
                            self.emit_progress("⚠️ TAP failed after all retries, attempting MON fallback (m3u8 → mp4)...", "warning")
                            # Use the parent class method to avoid recursion
                            media_urls = super().extract_media_urls(url, 'MON')
                            if media_urls:
                                # Force convert_to_mp4 for fallback
                                convert_to_mp4 = True
                                # Ensure we have an output filename with .mp4 extension
                                if not output_filename:
                                    from urllib.parse import urlparse
                                    parsed_url = urlparse(url)
                                    path_parts = parsed_url.path.strip('/').split('/')
                                    if len(path_parts) >= 2:
                                        base_name = f"{path_parts[-2]}_{path_parts[-1]}"
                                    else:
                                        base_name = path_parts[-1] if path_parts else 'video'
                                    import re
                                    base_name = re.sub(r'[^\w\-_.]', '_', base_name)
                                    output_filename = os.path.join(DOWNLOADS_DIR, f"{base_name}.mp4")
                        
                        if not media_urls:
                            self.emit_progress("❌ No video URLs found after all retries and fallback attempts", "error")
                            return False
                
                # If we got here, we have media URLs
                self.emit_progress(f"✅ Found {len(media_urls)} video URL(s)", "success")

                # Prefer .m3u8 over .mp4
                preferred_order = [
                    lambda u: u.lower().endswith('.m3u8'),
                    lambda u: '.m3u8' in u.lower(),
                    lambda u: u.lower().endswith('.mp4'),
                    lambda u: '.mp4' in u.lower(),
                ]
                media_urls.sort(key=lambda u: next((i for i, f in enumerate(preferred_order) if f(u)), 999))
                media_url = media_urls[0]
                
                # Streamtape (TAP) – prefer the generic get_video link over the raw .mp4 (to avoid CORS / Referer issues)
                if source and source.upper() == 'TAP':
                    # 1️⃣ prefer the generic get_video link (works reliably in browsers)
                    get_link = next((u for u in media_urls if 'streamtape.com/get_video' in u), None)
                    if get_link:
                        media_url = get_link
                    else:
                        # 2️⃣ fallback to raw .mp4 if we have nothing else
                        direct_mp4 = next((u for u in media_urls if u.lower().endswith('.mp4')), None)
                        if direct_mp4:
                            media_url = direct_mp4
                
                # Break out of retry loop if we got here successfully
                break
                
            except Exception as e:
                if retry_count < max_retries:
                    retry_count += 1
                    self.emit_progress(f"❌ Error: {str(e)}, retrying... ({retry_count}/{max_retries})", "warning")
                    time.sleep(3)  # Wait before retry
                    continue
                else:
                    self.emit_progress(f"❌ Fatal error after all retries: {str(e)}", "error")
                    return False
            
        # ------------------------------------------------------------
        # Decide whether to download server-side or just send link
        # ------------------------------------------------------------
        try:
            if convert_to_mp4:
                # Server-side download/conversion (used for MON fallback)
                self.emit_progress("📥 Downloading + converting to MP4...", "info")
                success = self._download_with_progress_mp4(media_url, output_filename)
                if success:
                    self.emit_progress(f"🎉 Download completed: {output_filename}", "success")
                    # Notify front-end with link to the newly stored mp4 so other devices can grab it
                    # Safely handle basename with None check
                    file_basename = os.path.basename(output_filename) if output_filename else "video.mp4"
                    file_link = f"/api/download-file/{file_basename}"
                    # Send to specific session
                    socketio.emit(
                        'media_url', 
                        {
                            'url': file_link,
                            'type': 'mp4'
                        }, 
                        to=self.session_id
                    )
                    # Also broadcast to all clients for sync
                    socketio.emit('media_url_global', {
                        'url': file_link,
                        'type': 'mp4',
                        'session_id': self.session_id
                    })
                else:
                    self.emit_progress("❌ Download failed", "error")
                return success
            else:
                # LINK-ONLY MODE – send URL to front-end
                lower_url = media_url.lower()
                file_type = 'mp4' if ('.mp4' in lower_url or 'streamtape.com' in lower_url or 'tapecontent' in lower_url) else 'm3u8'
                # Send to specific session
                socketio.emit(
                    'media_url', 
                    {
                        'url': media_url,
                        'type': file_type
                    }, 
                    to=self.session_id
                )
                # Also broadcast to all clients for sync
                socketio.emit('media_url_global', {
                    'url': media_url,
                    'type': file_type,
                    'session_id': self.session_id
                })

                self.emit_progress("🔗 Download link ready", "success")
                return True
                
        except Exception as e:
            self.emit_progress(f"❌ Error: {str(e)}", "error")
            return False
    
    def _download_with_progress_mp4(self, m3u8_url, output_filename):
        """Download MP4 with smooth frame-by-frame progress tracking"""
        try:
            import subprocess
            import re
            import time
            
            self.emit_progress("🎬 Converting to MP4... (0%)", "info")
            
            import json
            total_frames: int | None = None
            duration: float | None = None

            probe_cmd = [
                'ffprobe', '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams', '-show_format', m3u8_url
            ]
            try:
                probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=15)
                if probe.returncode == 0 and probe.stdout:
                    meta = json.loads(probe.stdout)
                    # duration from format
                    duration = float(meta.get('format', {}).get('duration', 0)) or None
                    # pick first video stream
                    for st in meta.get('streams', []):
                        if st.get('codec_type') == 'video':
                            if st.get('nb_frames') and st['nb_frames'] != '0':
                                total_frames = int(st['nb_frames'])
                                break
                            # else compute from avg_frame_rate
                            afr = st.get('avg_frame_rate') or st.get('r_frame_rate')
                            if afr and afr != '0/0' and duration:
                                try:
                                    num, den = afr.split('/')
                                    fps = float(num) / float(den) if float(den) != 0 else 0
                                    if fps:
                                        total_frames = int(duration * fps)
                                except Exception:
                                    pass
                            break
            except Exception:
                pass

            if total_frames:
                self.emit_progress(f"🎬 Converting to MP4... (estimated {total_frames} frames)", "info")
            else:
                total_frames = 5000  # fallback
                self.emit_progress("🎬 Converting to MP4... (estimating progress)", "info")
            
            # Prepare ffmpeg command with detailed progress
            cmd = [
                'ffmpeg',
                '-i', m3u8_url,
                '-c', 'copy',
                '-bsf:a', 'aac_adtstoasc',
                '-y',
                '-progress', 'pipe:1',
                '-nostats',
                '-loglevel', 'error',
                output_filename
            ]
            
            # Start FFmpeg process
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True,
                universal_newlines=True
            )
            
            current_frame = 0
            last_emitted_progress = -1
            
            # Read progress output line by line
            try:
                if process.stdout:
                    for line in process.stdout:
                        line = line.strip()
                        
                        # Parse frame progress with better regex
                        if line.startswith('frame='):
                            frame_match = re.search(r'frame=\s*(\d+)', line)
                            if frame_match:
                                current_frame = int(frame_match.group(1))
                                
                                # Calculate progress - ensure smooth increments
                                if total_frames > 0:
                                    # Dynamically enlarge total_frames if we underestimated
                                    if current_frame > total_frames:
                                        # Assume at least 20% more frames remain
                                        total_frames = int(current_frame * 1.2)
                                    progress = min(int((current_frame / total_frames) * 100), 99)
                                    
                                    # Emit progress for EVERY percentage increase (smooth 1%, 2%, 3%...)
                                    if progress > last_emitted_progress:
                                        self.emit_progress(f"🎬 Converting to MP4... ({progress}%) - {current_frame}/{total_frames} frames", "info")
                                        last_emitted_progress = progress
                                    # Also emit every 25 frames to catch small videos
                                    elif current_frame % 25 == 0 and current_frame > 0:
                                        self.emit_progress(f"🎬 Converting to MP4... ({progress}%) - {current_frame}/{total_frames} frames", "info")
                                else:
                                    # Fallback without total frames - show incremental progress
                                    if current_frame % 50 == 0 and current_frame > 0:
                                        # Estimate progress based on frame count
                                        estimated_progress = min(int(current_frame / 3000 * 100), 95)  # More aggressive estimation
                                        self.emit_progress(f"🎬 Converting to MP4... ({estimated_progress}%) - {current_frame} frames", "info")
                                        last_emitted_progress = estimated_progress
                        
                        # Parse time progress as backup
                        elif line.startswith('out_time_ms=') and duration:
                            try:
                                time_ms = int(line.split('=')[1])
                                time_seconds = time_ms / 1000000  # Convert microseconds to seconds
                                if duration > 0:
                                    time_progress = min(int((time_seconds / duration) * 100), 99)
                                    if time_progress > last_emitted_progress:
                                        self.emit_progress(f"🎬 Converting to MP4... ({time_progress}%) - {time_seconds:.1f}s/{duration:.1f}s", "info")
                                        last_emitted_progress = time_progress
                            except (ValueError, ZeroDivisionError):
                                pass
                        
                        # Check completion
                        elif line.startswith('progress=end'):
                            self.emit_progress("🎬 Converting to MP4... (100%)", "info")
                            break
                            
            except Exception as e:
                self.emit_progress(f"⚠️ Progress parsing error: {str(e)}", "warning")
            
            # Wait for process completion
            process.wait()
            
            if process.returncode == 0:
                if last_emitted_progress < 100:
                    self.emit_progress("🎬 Converting to MP4... (100%)", "info")
                return True
            else:
                # Handle errors
                try:
                    stderr_output = ""
                    if process.stderr:
                        stderr_output = process.stderr.read()
                except:
                    stderr_output = ""
                    
                error_msg = stderr_output.strip() if stderr_output else "Unknown FFmpeg error"
                self.emit_progress(f"❌ FFmpeg error: {error_msg}", "error")
                
                # Try fallback method
                self.emit_progress("🔄 Trying Python fallback method...", "warning")
                return self.download_with_python(m3u8_url, output_filename)
                
        except FileNotFoundError:
            self.emit_progress("❌ FFmpeg not found, trying Python method...", "warning")
            return self.download_with_python(m3u8_url, output_filename)
        except Exception as e:
            self.emit_progress(f"❌ MP4 conversion error: {str(e)}", "error")
            return False
    
    def _download_with_progress_m3u8(self, m3u8_url, output_filename):
        """Download .m3u8 file with progress updates"""
        try:
            import requests
            response = requests.get(m3u8_url, stream=True)
            response.raise_for_status()
            
            with open(output_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return True
        except Exception as e:
            self.emit_progress(f"❌ .m3u8 download error: {str(e)}", "error")
            return False

    def _download_direct_mp4(self, mp4_url, output_filename):
        """Stream an MP4 file with simple percentage progress updates (no FFmpeg)."""
        try:
            import requests, math, os
            from urllib.parse import urlparse
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
                "Accept": "*/*",
                "Referer": "https://streamtape.com/" if "streamtape" in mp4_url or "tapecontent" in mp4_url else urlparse(mp4_url).scheme + "://" + urlparse(mp4_url).hostname,
            }

            self.emit_progress("📥 Downloading MP4... (0%)", "info")

            with requests.get(mp4_url, stream=True, timeout=60, headers=headers) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                last_pct = -1

                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_filename), exist_ok=True)

                with open(output_filename, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1 MB
                        if chunk:
                            f.write(chunk)
                            if total:
                                downloaded += len(chunk)
                                pct = int(downloaded / total * 100)
                                if pct >= last_pct + 5:
                                    self.emit_progress(f"📥 Downloading MP4... ({pct}%)", "info")
                                    last_pct = pct

            self.emit_progress("📥 Downloading MP4... (100%)", "info")
            return True
        except Exception as e:
            self.emit_progress(f"❌ MP4 download error: {str(e)}", "error")
            return False

    def download_with_python(self, m3u8_url, output_filename):
        """Download and convert using Python libraries (fallback method)"""
        try:
            import requests
            import m3u8
            from urllib.parse import urljoin
            
            self.emit_progress("🔄 Using Python fallback method...", "info")
            
            # Load and parse m3u8 playlist
            playlist = m3u8.load(m3u8_url)
            
            if not playlist.segments:
                self.emit_progress("❌ No segments found in m3u8 playlist", "error")
                return False
            
            total_segments = len(playlist.segments)
            
            # Download segments and combine
            with open(output_filename, 'wb') as output_file:
                for i, segment in enumerate(playlist.segments):
                    segment_url = urljoin(m3u8_url, segment.uri)
                    
                    # Calculate progress
                    progress = int((i / total_segments) * 100)
                    self.emit_progress(f"🔄 Downloading segment {i+1}/{total_segments} ({progress}%)", "info")
                    
                    response = requests.get(segment_url, stream=True)
                    response.raise_for_status()
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        output_file.write(chunk)
            
            self.emit_progress("✅ Python download completed", "success")
            return True
            
        except Exception as e:
            self.emit_progress(f"❌ Python download error: {str(e)}", "error")
            return False

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/download', methods=['POST'])
def start_download():
    """Start a download process"""
    global current_download_session, download_start_time
    
    data = request.json
    url = data.get('url', '').strip()
    output_filename = data.get('filename', '').strip()
    convert_to_mp4 = data.get('convert_to_mp4', False)
    source = data.get('source') or None
    session_id = data.get('session_id')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    if not session_id:
        return jsonify({'error': 'Session ID is required'}), 400
    
    # Validate URL
    if 'kukaj.' not in url:
        return jsonify({'error': 'Please provide a valid kukaj URL'}), 400
    
    # Global download lock - only one download at a time across all devices
    with global_download_lock:
        if current_download_session is not None:
            # Check if the existing download is still active (timeout after 10 minutes)
            if download_start_time and (datetime.now() - download_start_time).total_seconds() < 600:
                return jsonify({
                    'error': 'Another download is already in progress. Please wait.',
                    'active_session': current_download_session,
                    'start_time': download_start_time.isoformat()
                }), 409
            else:
                # Clean up stale download
                current_download_session = None
                download_start_time = None
        
        # Set this session as the active download
        current_download_session = session_id
        download_start_time = datetime.now()
        
        # Broadcast download start to all connected clients
        socketio.emit('download_state_changed', {
            'downloading': True,
            'session_id': session_id,
            'url': url,
            'filename': output_filename,
            'source': source,
            'start_time': download_start_time.isoformat()
        })
    
    # Start download in background thread
    def download_thread():
        global current_download_session, download_start_time
        try:
            active_downloads[session_id] = {
                'url': url,
                'filename': output_filename,
                'convert_to_mp4': convert_to_mp4,
                'source': source,
                'start_time': datetime.now()
            }
            
            with WebDownloader(session_id, headless=True) as downloader:
                success = downloader.download_video(url, output_filename, convert_to_mp4, source)
                
                # Add to history
                actual_filename = output_filename
                if not actual_filename:
                    # Generate the same filename logic as in the downloader
                    from urllib.parse import urlparse
                    parsed_url = urlparse(url)
                    path_parts = parsed_url.path.strip('/').split('/')
                    
                    # Better filename generation
                    if len(path_parts) >= 1 and path_parts[-1]:
                        # For URLs like /matrix or /series/S01E01
                        if len(path_parts) >= 2 and path_parts[-2] not in ['film', 'serial']:
                            # For series URLs like /series-name/S01E01
                            base_name = f"{path_parts[-2]}_{path_parts[-1]}"
                        else:
                            # For film URLs like /matrix
                            base_name = path_parts[-1]
                    else:
                        base_name = "downloaded_video"
                    
                    # Clean up filename (remove special characters)
                    import re
                    base_name = re.sub(r'[^\\w\-_.]', '_', base_name)
                    
                    # Decide extension – if convert_to_mp4 OR preferred source appears to be mp4, save as mp4
                    if convert_to_mp4 or (source and source.upper() in ['TAP']):
                        ext = 'mp4'
                    else:
                        ext = 'm3u8'
                    actual_filename = f"{base_name}.{ext}"
                
                add_to_history(url, os.path.basename(actual_filename) if actual_filename else None, success, convert_to_mp4, source)
                
                # Clean up
                if session_id in active_downloads:
                    del active_downloads[session_id]
                
                # Emit to specific session and also broadcast to all clients
                # Send just the filename, not the full path
                filename_only = os.path.basename(actual_filename) if actual_filename else None

                # Emit 'download_complete' only if server actually created a file
                file_created = False
                if filename_only:
                    file_created = os.path.exists(os.path.join(DOWNLOADS_DIR, filename_only))

                if file_created:
                    # Create download URL for cross-device access
                    download_url = f"/api/download-file/{filename_only}"
                    file_type = 'mp4' if filename_only.endswith('.mp4') else 'm3u8'
                    
                    # Emit to specific session
                    socketio.emit(
                        'download_complete',
                        {
                            'success': success,
                            'filename': filename_only,
                            'original_filename': output_filename,
                        },
                        room=session_id,
                    )

                    # Also broadcast to all clients for sync with download URL
                    socketio.emit(
                        'download_complete_global',
                        {
                            'success': success,
                            'filename': filename_only,
                            'original_filename': output_filename,
                            'session_id': session_id,
                            'download_url': download_url,
                            'file_type': file_type,
                        },
                    )
                
                # Also broadcast file list update to all clients
                socketio.emit('files_updated', {
                    'message': 'File list updated'
                })
                
        except Exception as e:
            print(f"❌ Download thread error: {e}")
            # Emit to specific session
            socketio.emit('download_error', {
                'error': str(e)
            }, room=session_id)
            
            # Also broadcast to all clients for sync
            socketio.emit('download_error_global', {
                'error': str(e),
                'session_id': session_id
            })
            
            if session_id in active_downloads:
                del active_downloads[session_id]
        
        finally:
            # Always clean up global download lock
            with global_download_lock:
                if current_download_session == session_id:
                    current_download_session = None
                    download_start_time = None
                    
                    # Broadcast download end to all connected clients
                    socketio.emit('download_state_changed', {
                        'downloading': False,
                        'session_id': session_id
                    })
    
    threading.Thread(target=download_thread, daemon=True).start()
    
    return jsonify({'success': True, 'message': 'Download started'})

@app.route('/api/files')
def list_files():
    """List downloaded files"""
    files = []
    if os.path.exists(DOWNLOADS_DIR):
        for filename in os.listdir(DOWNLOADS_DIR):
            if filename.endswith(('.m3u8', '.mp4')) and not filename.startswith('.'):
                filepath = os.path.join(DOWNLOADS_DIR, filename)
                stat = os.stat(filepath)
                files.append({
                    'name': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
    
    return jsonify({'files': sorted(files, key=lambda x: x['modified'], reverse=True)})

@app.route('/api/file-info/<filename>')
def get_file_info(filename):
    """Get file information (existence, size, etc.)"""
    try:
        filepath = os.path.join(DOWNLOADS_DIR, filename)
        if os.path.exists(filepath) and filename.endswith(('.m3u8', '.mp4')):
            stat = os.stat(filepath)
            return jsonify({
                'exists': True,
                'filename': filename,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            return jsonify({'exists': False})
    except Exception as e:
        return jsonify({'exists': False, 'error': str(e)})

@app.route('/api/download-file/<filename>')
def download_file(filename):
    """Download a file"""
    try:
        filepath = os.path.join(DOWNLOADS_DIR, filename)
        if os.path.exists(filepath) and filename.endswith(('.m3u8', '.mp4')):
            return send_file(filepath, as_attachment=True)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-status')
def get_download_status():
    """Get current download status"""
    global current_download_session, download_start_time
    
    with global_download_lock:
        if current_download_session is not None:
            # Check if download is still active
            if download_start_time and (datetime.now() - download_start_time).total_seconds() < 600:
                # Get additional info from active downloads
                active_info = active_downloads.get(current_download_session, {})
                
                return jsonify({
                    'downloading': True,
                    'session_id': current_download_session,
                    'url': active_info.get('url'),
                    'filename': active_info.get('filename'),
                    'source': active_info.get('source'),
                    'start_time': download_start_time.isoformat(),
                    'duration': (datetime.now() - download_start_time).total_seconds()
                })
            else:
                # Clean up stale download
                current_download_session = None
                download_start_time = None
        
        return jsonify({
            'downloading': False,
            'session_id': None,
            'url': None,
            'filename': None,
            'source': None,
            'start_time': None,
            'duration': 0
        })

@app.route('/api/history')
def get_history():
    """Get download history"""
    return jsonify({'history': download_history})

@app.route('/api/history/clear', methods=['POST'])
def clear_history_endpoint():
    """Clear the entire download history"""
    global download_history
    download_history = []
    save_history()
    return jsonify({'success': True, 'message': 'History cleared'})

@app.route('/api/history/delete', methods=['POST'])
def delete_history_item():
    """Delete a specific history entry identified by its URL"""
    global download_history
    data = request.json or {}
    url_to_delete = data.get('url')
    if not url_to_delete:
        return jsonify({'error': 'URL is required'}), 400

    original_len = len(download_history)
    download_history = [entry for entry in download_history if entry.get('url') != url_to_delete]
    if len(download_history) == original_len:
        return jsonify({'error': 'Entry not found'}), 404

    save_history()
    return jsonify({'success': True, 'message': 'Entry removed'})

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f"Client disconnected: {request.sid}")
    # Clean up any active downloads for this session
    if request.sid in active_downloads:
        del active_downloads[request.sid]

@socketio.on('join_session')
def handle_join_session(data):
    """Handle client joining a session room"""
    session_id = data.get('session_id')
    if session_id:
        join_room(session_id)
        print(f"Client {request.sid} joined session {session_id}")

# Performance monitoring for ARM devices
def get_system_info():
    """Get system information for ARM devices"""
    import platform
    import psutil
    import os
    
    info = {
        'platform': platform.platform(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'cpu_count': psutil.cpu_count(),
        'cpu_percent': psutil.cpu_percent(interval=1),
        'memory': psutil.virtual_memory()._asdict(),
        'disk': psutil.disk_usage('/')._asdict(),
        'load_avg': os.getloadavg() if hasattr(os, 'getloadavg') else None,
        'is_arm': 'arm' in platform.machine().lower() or 'aarch64' in platform.machine().lower()
    }
    
    return info

@app.route('/api/system-info')
def get_system_info_endpoint():
    """Get system information for monitoring"""
    try:
        info = get_system_info()
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ARM-specific resource monitoring
class ARMResourceMonitor:
    def __init__(self):
        self.is_arm = False
        self.monitoring_enabled = False
        try:
            import platform
            self.is_arm = 'arm' in platform.machine().lower() or 'aarch64' in platform.machine().lower()
            if self.is_arm:
                import psutil
                self.monitoring_enabled = True
                print("🔧 ARM resource monitoring enabled")
        except ImportError:
            print("⚠️ psutil not available, resource monitoring disabled")
    
    def get_resource_usage(self):
        """Get current resource usage"""
        if not self.monitoring_enabled:
            return None
        
        try:
            import psutil
            return {
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'memory_percent': psutil.virtual_memory().percent,
                'memory_available': psutil.virtual_memory().available,
                'disk_usage': psutil.disk_usage('/').percent,
                'load_avg': psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
            }
        except Exception as e:
            print(f"⚠️ Error getting resource usage: {e}")
            return None
    
    def check_resource_limits(self):
        """Check if resource usage is too high for ARM devices"""
        if not self.monitoring_enabled:
            return True
        
        try:
            usage = self.get_resource_usage()
            if not usage:
                return True
            
            # ARM-specific thresholds
            if usage['cpu_percent'] > 85:
                print(f"⚠️ High CPU usage: {usage['cpu_percent']}%")
                return False
            
            if usage['memory_percent'] > 90:
                print(f"⚠️ High memory usage: {usage['memory_percent']}%")
                return False
            
            return True
        except Exception as e:
            print(f"⚠️ Error checking resource limits: {e}")
            return True

# Global resource monitor
resource_monitor = ARMResourceMonitor()

if __name__ == '__main__':
    print("🚀 Starting Kukaj Video Downloader...")
    
    # Print system information
    try:
        system_info = get_system_info()
        print(f"📊 System: {system_info['platform']}")
        print(f"🔧 Architecture: {system_info['machine']}")
        print(f"💾 Memory: {system_info['memory']['total'] // (1024**3)} GB")
        print(f"💻 CPU cores: {system_info['cpu_count']}")
        if system_info['is_arm']:
            print("🔧 ARM device detected - optimizations enabled")
    except Exception as e:
        print(f"⚠️ Could not get system info: {e}")
    
    # Check if we have enough resources
    if resource_monitor.monitoring_enabled:
        usage = resource_monitor.get_resource_usage()
        if usage:
            print(f"📊 Current CPU: {usage['cpu_percent']}%")
            print(f"📊 Current Memory: {usage['memory_percent']}%")
            if not resource_monitor.check_resource_limits():
                print("⚠️ Warning: High resource usage detected")
    
    socketio.run(app, host='0.0.0.0', port=8080, debug=False, allow_unsafe_werkzeug=True) 