#!/usr/bin/env python3
"""
Kukaj.fi Video Downloader
Downloads videos from kukaj.fi that are loaded as .m3u8 files via JavaScript
"""

import os
import re
import time
import requests
import subprocess
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import m3u8


def normalize_kukaj_url(url):
    """
    Normalize kukaj URLs by converting other subdomains to kukaj.fi
    
    Args:
        url (str): The original URL
        
    Returns:
        tuple: (normalized_url, was_changed)
    """
    # Parse the URL
    parsed = urlparse(url)
    
    # Check if it's a kukaj domain that needs normalization
    if 'kukaj.' in parsed.netloc:
        # Pattern to match kukaj domains: optionally subdomain + kukaj + TLD
        import re
        match = re.match(r'^(.*\.)?(kukaj\.)([a-z]+)$', parsed.netloc)
        
        if match:
            subdomain_part = match.group(1) or ""  # e.g., "serial."
            kukaj_part = match.group(2)           # "kukaj."
            tld = match.group(3)                  # e.g., "io", "in", "tv"
            
            # Only normalize if it's not already .fi
            if tld != 'fi':
                # Replace with kukaj.fi while preserving subdomain
                normalized_netloc = f"{subdomain_part}kukaj.fi"
                
                # Reconstruct the URL
                normalized_url = f"{parsed.scheme}://{normalized_netloc}{parsed.path}"
                if parsed.query:
                    normalized_url += f"?{parsed.query}"
                if parsed.fragment:
                    normalized_url += f"#{parsed.fragment}"
                    
                return normalized_url, True
    
    # Return original URL if no changes needed
    return url, False


class KukajDownloader:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.setup_driver()
    
    def setup_driver(self):
        """Set up Chrome WebDriver with appropriate options"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Enable logging for network requests
        chrome_options.add_argument("--enable-logging")
        chrome_options.add_argument("--log-level=0")
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
        
        # Install and setup Chrome driver with better error handling
        try:
            # Try system chromedriver first (more reliable)
            try:
                self.driver = webdriver.Chrome(options=chrome_options)
                print("✅ Using system ChromeDriver")
            except Exception:
                # Fallback to webdriver-manager
                print("🔄 System ChromeDriver not found, downloading...")
                
                # Try to clear cache and reinstall if we've had issues before
                try:
                    driver_path = ChromeDriverManager().install()
                except Exception as e:
                    print(f"⚠️ ChromeDriver installation failed: {e}")
                    print("🔄 Clearing WebDriver cache and retrying...")
                    
                    # Clear the webdriver cache
                    import shutil
                    cache_dir = os.path.expanduser("~/.wdm")
                    if os.path.exists(cache_dir):
                        try:
                            shutil.rmtree(cache_dir)
                            print("✅ WebDriver cache cleared")
                        except:
                            print("⚠️ Could not clear cache")
                    
                    # Retry installation
                    driver_path = ChromeDriverManager().install()
                
                # Handle the case where webdriver-manager returns wrong path
                import os
                import glob
                import stat
                
                # Always validate the path returned by webdriver-manager
                if not os.path.isfile(driver_path) or not os.access(driver_path, os.X_OK):
                    print(f"⚠️ Invalid driver path: {driver_path}")
                    # Look for the actual chromedriver executable
                    base_dir = os.path.dirname(driver_path)
                    
                    # Search more thoroughly for chromedriver
                    driver_candidates = []
                    
                    # Look in the same directory and subdirectories
                    for root, dirs, files in os.walk(base_dir):
                        for file in files:
                            if file == 'chromedriver' or (file.startswith('chromedriver') and not file.endswith('.txt') and not file.endswith('.md')):
                                full_path = os.path.join(root, file)
                                driver_candidates.append(full_path)
                    
                    # Find the actual executable
                    driver_path = None
                    for candidate in driver_candidates:
                        if os.path.isfile(candidate):
                            # Check if it's actually executable
                            file_stat = os.stat(candidate)
                            if file_stat.st_mode & stat.S_IXUSR:  # Check if user has execute permission
                                # Additional check: make sure it's not a text file
                                try:
                                    with open(candidate, 'rb') as f:
                                        header = f.read(4)
                                        # Check if it's a binary file (not text)
                                        if header and not header.startswith(b'#') and not header.startswith(b'<'):
                                            driver_path = candidate
                                            print(f"✅ Found valid ChromeDriver at: {candidate}")
                                            break
                                except:
                                    continue
                    
                    if not driver_path:
                        raise Exception("Could not find valid ChromeDriver executable")
                
                print(f"🔧 Using ChromeDriver at: {driver_path}")
                
                service = Service(driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                print("✅ Using downloaded ChromeDriver")
            
            # Set timeouts to prevent hanging
            self.driver.set_page_load_timeout(30)  # 30 second page load timeout
            self.driver.implicitly_wait(10)
            
            # Execute script to avoid detection
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
        except Exception as e:
            print(f"❌ Failed to initialize Chrome driver: {e}")
            print("💡 Try installing ChromeDriver manually or check if Chrome is installed")
            raise
    
    def extract_m3u8_url(self, url):
        """Extract .m3u8 URL from the webpage"""
        print(f"Loading page: {url}")
        
        try:
            # Load page with timeout handling
            self.driver.get(url)
            print("✅ Page loaded successfully")
        except Exception as e:
            print(f"⚠️ Page load issue: {e}")
            print("🔄 Attempting to continue anyway...")
        
        # Wait for the page to load and JavaScript to execute
        print("🔄 Waiting for JavaScript to load video...")
        
        # Progressive wait with status updates
        for i in range(5):
            time.sleep(1)
            print(f"⏳ Waiting... ({i+1}/5 seconds)")
        
        # Try to trigger video loading by scrolling and looking for play buttons
        print("🎬 Attempting to trigger video loading...")
        try:
            # Scroll down to ensure video is in viewport
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(1)
            
            # Look for and click play buttons
            play_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                "button[aria-label*='play'], button[title*='play'], .play-button, .vjs-big-play-button, [class*='play']")
            
            if play_buttons:
                print(f"   Found {len(play_buttons)} potential play buttons, clicking the first one...")
                try:
                    play_buttons[0].click()
                    time.sleep(2)
                except:
                    print("   ⚠️ Could not click play button")
            else:
                print("   No play buttons found")
                
        except Exception as e:
            print(f"   ⚠️ Error during page interaction: {e}")
        
        print("🔍 Extracting video URLs from network logs...")
        
        # Only use Method 1 (Network logs) - it's the only one that works
        m3u8_urls = []
        
        try:
            logs = self.driver.get_log('performance')
            print(f"📊 Analyzing {len(logs)} network requests...")
            
            for log in logs:
                message = log['message']
                if '.m3u8' in message:
                    # Extract URL from log
                    url_match = re.search(r'https?://[^\s"\']+\.m3u8[^\s"\']*', message)
                    if url_match:
                        m3u8_urls.append(url_match.group(0))
            
            # Remove duplicates
            m3u8_urls = list(set(m3u8_urls))
            
            if m3u8_urls:
                print(f"✅ Found {len(m3u8_urls)} unique .m3u8 URLs")
                for i, url in enumerate(m3u8_urls, 1):
                    print(f"   {i}. {url[:80]}..." if len(url) > 80 else f"   {i}. {url}")
                return m3u8_urls
            else:
                print("❌ No .m3u8 URLs found in network logs")
                
                # Enhanced fallback strategy
                print("🔄 Trying enhanced fallback strategy...")
                
                # Try more aggressive interactions
                try:
                    # Look for video elements and try to play them
                    video_elements = self.driver.find_elements(By.TAG_NAME, 'video')
                    if video_elements:
                        print(f"   Found {len(video_elements)} video elements, trying to play...")
                        for video in video_elements:
                            try:
                                self.driver.execute_script("arguments[0].play();", video)
                                time.sleep(1)
                                print("   ✅ Triggered video play")
                            except:
                                pass
                    
                    # Try clicking more button types
                    more_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                        "[onclick*='play'], [class*='player'], .video-player, .player-button, .start-button")
                    
                    if more_buttons:
                        print(f"   Found {len(more_buttons)} additional buttons, trying to click...")
                        for button in more_buttons[:3]:  # Try first 3
                            try:
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                                time.sleep(0.5)
                                self.driver.execute_script("arguments[0].click();", button)
                                time.sleep(1)
                                print("   ✅ Clicked additional button")
                            except:
                                pass
                    
                    # Wait for potential async video loading
                    print("⏳ Waiting additional 8 seconds for video to load...")
                    time.sleep(8)
                    
                    # Get any new network logs generated after interactions
                    new_logs = self.driver.get_log('performance')
                    if new_logs:
                        print(f"📊 Analyzing {len(new_logs)} new network requests...")
                        for log in new_logs:
                            message = log['message']
                            if '.m3u8' in message:
                                url_match = re.search(r'https?://[^\s"\']+\.m3u8[^\s"\']*', message)
                                if url_match:
                                    m3u8_urls.append(url_match.group(0))
                        
                        m3u8_urls = list(set(m3u8_urls))
                        
                        if m3u8_urls:
                            print(f"✅ Enhanced fallback successful! Found {len(m3u8_urls)} .m3u8 URLs")
                            for i, url in enumerate(m3u8_urls, 1):
                                print(f"   {i}. {url[:80]}..." if len(url) > 80 else f"   {i}. {url}")
                            return m3u8_urls
                    else:
                        print("   No new network requests captured")
                    
                except Exception as e:
                    print(f"   ⚠️ Error during enhanced fallback: {e}")
                
                print("❌ Still no .m3u8 URLs found after enhanced fallback")
                
                # Final debug info
                page_title = self.driver.title
                current_url = self.driver.current_url
                print(f"🔍 Debug info:")
                print(f"   Page title: {page_title}")
                print(f"   Current URL: {current_url}")
                
                if "kukaj" not in current_url.lower():
                    print("⚠️ Page may have redirected - URL doesn't contain 'kukaj'")
                
                # Last resort: Check page source for any clues
                try:
                    page_source = self.driver.page_source
                    if "This video is not available" in page_source or "Video not found" in page_source:
                        print("⚠️ Video may not be available on this page")
                    elif "loading" in page_source.lower() or "spinner" in page_source.lower():
                        print("⚠️ Page may still be loading content")
                    else:
                        print("⚠️ Page content appears normal - video sources may be heavily obfuscated")
                except:
                    pass
                
                return []
                
        except Exception as e:
            print(f"⚠️ Error accessing network logs: {e}")
            return []
    
    def download_with_ffmpeg(self, m3u8_url, output_filename):
        """Download video using ffmpeg"""
        print(f"Downloading video from: {m3u8_url}")
        print(f"Output filename: {output_filename}")
        
        # Prepare ffmpeg command
        cmd = [
            'ffmpeg',
            '-i', m3u8_url,
            '-c', 'copy',  # Copy without re-encoding
            '-bsf:a', 'aac_adtstoasc',  # Fix AAC stream if needed
            '-y',  # Overwrite output file
            output_filename
        ]
        
        try:
            # Run ffmpeg
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            
            if result.returncode == 0:
                print(f"Successfully downloaded: {output_filename}")
                return True
            else:
                print(f"FFmpeg error: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            print("Download timed out after 1 hour")
            return False
        except FileNotFoundError:
            print("FFmpeg not found. Please install FFmpeg.")
            return False
        except Exception as e:
            print(f"Error during download: {e}")
            return False
    
    def download_with_python(self, m3u8_url, output_filename):
        """Download video using Python libraries (fallback method)"""
        print(f"Downloading video using Python method from: {m3u8_url}")
        
        try:
            # Load and parse m3u8 playlist
            playlist = m3u8.load(m3u8_url)
            
            if not playlist.segments:
                print("No segments found in m3u8 playlist")
                return False
            
            # Download segments and combine
            with open(output_filename, 'wb') as output_file:
                for i, segment in enumerate(playlist.segments):
                    segment_url = urljoin(m3u8_url, segment.uri)
                    print(f"Downloading segment {i+1}/{len(playlist.segments)}: {segment_url}")
                    
                    response = requests.get(segment_url, stream=True)
                    response.raise_for_status()
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        output_file.write(chunk)
            
            print(f"Successfully downloaded: {output_filename}")
            return True
            
        except Exception as e:
            print(f"Error during Python download: {e}")
            return False
    
    def download_m3u8_file(self, m3u8_url, output_filename):
        """Download the .m3u8 file itself"""
        print(f"Downloading .m3u8 file from: {m3u8_url}")
        print(f"Output filename: {output_filename}")
        
        try:
            response = requests.get(m3u8_url, stream=True)
            response.raise_for_status()
            
            with open(output_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"Successfully downloaded .m3u8 file: {output_filename}")
            return True
            
        except Exception as e:
            print(f"Error downloading .m3u8 file: {e}")
            return False
    
    def download_video(self, url, output_filename=None, convert_to_mp4=False):
        """Main method to download video from kukaj.fi URL"""
        try:
            # Normalize the URL (convert other kukaj subdomains to kukaj.fi)
            normalized_url, was_changed = normalize_kukaj_url(url)
            if was_changed:
                print(f"URL normalized: {url}")
                print(f"Using: {normalized_url}")
                print()
                url = normalized_url
            
            # Extract m3u8 URLs
            m3u8_urls = self.extract_m3u8_url(url)
            
            if not m3u8_urls:
                print("No .m3u8 URLs found on the page")
                return False
            
            print(f"Found {len(m3u8_urls)} .m3u8 URL(s):")
            for i, m3u8_url in enumerate(m3u8_urls, 1):
                print(f"  {i}. {m3u8_url}")
            
            # Use the first m3u8 URL found
            m3u8_url = m3u8_urls[0]
            
            # Generate output filename if not provided
            if not output_filename:
                parsed_url = urlparse(url)
                path_parts = parsed_url.path.strip('/').split('/')
                if len(path_parts) >= 2:
                    base_name = f"{path_parts[-2]}_{path_parts[-1]}"
                else:
                    base_name = "downloaded_video"
                
                if convert_to_mp4:
                    output_filename = f"{base_name}.mp4"
                else:
                    output_filename = f"{base_name}.m3u8"
            
            # Download based on the requested format
            if convert_to_mp4:
                # Try downloading with ffmpeg first, then fallback to Python method
                if self.download_with_ffmpeg(m3u8_url, output_filename):
                    return True
                else:
                    print("FFmpeg download failed, trying Python method...")
                    return self.download_with_python(m3u8_url, output_filename)
            else:
                # Download just the .m3u8 file
                return self.download_m3u8_file(m3u8_url, output_filename)
                
        except Exception as e:
            print(f"Error during download: {e}")
            return False
    
    def close(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def main():
    """Main function to run the downloader"""
    import sys
    import argparse
    
    # Create argument parser
    parser = argparse.ArgumentParser(
        description="Download videos from kukaj domains (downloads .m3u8 by default)\nSupports kukaj.fi, kukaj.io, kukaj.in and other subdomains",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04
  python kukaj_downloader.py https://serial.kukaj.io/hra-na-olihen/S03E04 --mp4
  python kukaj_downloader.py https://serial.kukaj.in/hra-na-olihen/S03E04 -o episode.m3u8
  python kukaj_downloader.py https://serial.kukaj.fi/hra-na-olihen/S03E04 --mp4 -o episode.mp4

Note: Other kukaj subdomains (kukaj.io, kukaj.in, etc.) will be automatically 
      converted to kukaj.fi for compatibility.
        """
    )
    
    parser.add_argument('url', help='The kukaj.fi URL to download from')
    parser.add_argument('-o', '--output', help='Output filename (optional)')
    parser.add_argument('--mp4', action='store_true', 
                       help='Convert to MP4 format (default: download .m3u8 file)')
    parser.add_argument('--headless', action='store_true', default=True,
                       help='Run browser in headless mode (default: True)')
    parser.add_argument('--no-headless', action='store_true', 
                       help='Run browser with GUI (for debugging)')
    
    args = parser.parse_args()
    
    # Determine headless mode
    headless = args.headless and not args.no_headless
    
    print("Kukaj.fi Video Downloader")
    print("=" * 40)
    
    if args.mp4:
        print("Mode: Download and convert to MP4")
    else:
        print("Mode: Download .m3u8 file")
    
    print(f"URL: {args.url}")
    if args.output:
        print(f"Output: {args.output}")
    print()
    
    with KukajDownloader(headless=headless) as downloader:
        success = downloader.download_video(args.url, args.output, args.mp4)
        
        if success:
            print("\nDownload completed successfully!")
        else:
            print("\nDownload failed!")
            sys.exit(1)


if __name__ == "__main__":
    main() 