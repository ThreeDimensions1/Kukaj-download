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
            # Get the chromedriver path
            driver_path = ChromeDriverManager().install()
            
            # Handle the case where webdriver-manager returns wrong path
            if not driver_path.endswith('chromedriver'):
                import os
                import glob
                # Look for the actual chromedriver executable
                base_dir = os.path.dirname(driver_path)
                driver_candidates = glob.glob(os.path.join(base_dir, "**/chromedriver*"), recursive=True)
                
                # Find the actual executable
                for candidate in driver_candidates:
                    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                        if not candidate.endswith('.txt') and not candidate.endswith('.md'):
                            driver_path = candidate
                            break
            
            service = Service(driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Set a reasonable timeout
            self.driver.implicitly_wait(10)
            
            # Execute script to avoid detection
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
        except Exception as e:
            print(f"Error setting up Chrome driver: {e}")
            print("Trying to use system Chrome driver...")
            try:
                # Try to use system chromedriver
                self.driver = webdriver.Chrome(options=chrome_options)
                self.driver.implicitly_wait(10)
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            except Exception as e2:
                print(f"Failed to initialize Chrome driver: {e2}")
                print("Please ensure Chrome browser and chromedriver are installed")
                raise
    
    def extract_m3u8_url(self, url):
        """Extract .m3u8 URL from the webpage"""
        print(f"Loading page: {url}")
        self.driver.get(url)
        
        # Wait for the page to load and JavaScript to execute
        time.sleep(5)  # Wait for JavaScript to load the video
        
        # Look for .m3u8 URLs in various places
        m3u8_urls = []
        
        # Method 1: Check network requests (if available)
        try:
            logs = self.driver.get_log('performance')
            for log in logs:
                message = log['message']
                if '.m3u8' in message:
                    # Extract URL from log
                    url_match = re.search(r'https?://[^\s"\']+\.m3u8[^\s"\']*', message)
                    if url_match:
                        m3u8_urls.append(url_match.group(0))
        except Exception as e:
            print(f"Performance logs not available: {e}")
            # Continue with other methods
        
        # Method 2: Check page source for .m3u8 URLs
        page_source = self.driver.page_source
        m3u8_pattern = r'https?://[^\s"\']+\.m3u8[^\s"\']*'
        found_urls = re.findall(m3u8_pattern, page_source)
        m3u8_urls.extend(found_urls)
        
        # Method 3: Execute JavaScript to find video elements
        try:
            video_elements = self.driver.find_elements(By.TAG_NAME, "video")
            for video in video_elements:
                src = video.get_attribute("src")
                if src and '.m3u8' in src:
                    m3u8_urls.append(src)
        except Exception as e:
            print(f"Error finding video elements: {e}")
        
        # Method 4: Check for source elements
        try:
            source_elements = self.driver.find_elements(By.TAG_NAME, "source")
            for source in source_elements:
                src = source.get_attribute("src")
                if src and '.m3u8' in src:
                    m3u8_urls.append(src)
        except Exception as e:
            print(f"Error finding source elements: {e}")
        
        # Method 5: Execute JavaScript to find video sources
        try:
            js_sources = self.driver.execute_script("""
                var sources = [];
                // Check all video elements
                var videos = document.querySelectorAll('video');
                for (var i = 0; i < videos.length; i++) {
                    if (videos[i].src && videos[i].src.includes('.m3u8')) {
                        sources.push(videos[i].src);
                    }
                    if (videos[i].currentSrc && videos[i].currentSrc.includes('.m3u8')) {
                        sources.push(videos[i].currentSrc);
                    }
                }
                
                // Check all source elements
                var sourceTags = document.querySelectorAll('source');
                for (var i = 0; i < sourceTags.length; i++) {
                    if (sourceTags[i].src && sourceTags[i].src.includes('.m3u8')) {
                        sources.push(sourceTags[i].src);
                    }
                }
                
                // Check for HLS.js or other video libraries
                if (window.Hls && window.Hls.url) {
                    sources.push(window.Hls.url);
                }
                
                // Look for any variables containing .m3u8
                var scripts = document.querySelectorAll('script');
                for (var i = 0; i < scripts.length; i++) {
                    var content = scripts[i].innerHTML;
                    var m3u8Matches = content.match(/https?:\\/\\/[^\\s"']+\\.m3u8[^\\s"']*/g);
                    if (m3u8Matches) {
                        sources = sources.concat(m3u8Matches);
                    }
                }
                
                return sources;
            """)
            
            if js_sources:
                m3u8_urls.extend(js_sources)
                print(f"Found {len(js_sources)} URLs via JavaScript")
        except Exception as e:
            print(f"Error executing JavaScript: {e}")
        
        # Remove duplicates and return
        m3u8_urls = list(set(m3u8_urls))
        
        if not m3u8_urls:
            print("No .m3u8 URLs found. Let me try waiting longer...")
            time.sleep(3)  # Additional wait
            
            # Try again with page source
            page_source = self.driver.page_source
            found_urls = re.findall(m3u8_pattern, page_source)
            m3u8_urls.extend(found_urls)
            m3u8_urls = list(set(m3u8_urls))
        
        return m3u8_urls
    
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