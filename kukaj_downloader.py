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
from playwright.sync_api import sync_playwright
import m3u8
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright


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
        self.playwright = None
        self.browser = None
        self.page = None
        self.context = None
        self.setup_playwright()
    
    def setup_playwright(self):
        """Set up Playwright with Chromium"""
        try:
            print("🎭 Setting up Playwright...")
            
            # Use sync playwright for simpler API
            self.playwright = sync_playwright().start()
            
            # Launch Firefox browser with minimal settings for proper web page loading
            self.browser = self.playwright.firefox.launch(
                headless=self.headless,
                firefox_user_prefs={
                    'network.proxy.type': 0,  # No proxy
                    'network.proxy.no_proxies_on': 'localhost, 127.0.0.1',
                    'network.http.use-cache': False,
                    'media.volume_scale': '0.0',  # Mute audio
                    'dom.webdriver.enabled': False,
                    'useAutomationExtension': False,
                    'network.trr.mode': 5,
                },
                args=[
                    '--width=1920',
                    '--height=1080',
                    '--no-remote',
                    '--disable-extensions'
                ]
            )
            
            # Create browser context with additional settings
            context = self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
                viewport={'width': 1920, 'height': 1080},
                ignore_https_errors=True,
                java_script_enabled=True,
                bypass_csp=True,
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'max-age=0'
                }
            )
            
            # Create page
            self.page = context.new_page()
            
            # Set longer timeouts for better reliability
            self.page.set_default_timeout(60000)  # 60 seconds
            self.page.set_default_navigation_timeout(60000)  # 60 seconds
            
            print("✅ Playwright setup complete")
            
        except Exception as e:
            print(f"❌ Failed to initialize Playwright: {e}")
            print("💡 Try running: playwright install firefox")
            raise
    
    def extract_m3u8_url(self, url):
        """Extract .m3u8 URL from the webpage using Playwright"""
        print(f"🔍 Loading page: {url}")
        
        if not self.page:
            print("❌ Page not initialized")
            return []
            
        m3u8_urls = []
        
        try:
            # Set up network monitoring for m3u8 files BEFORE navigating
            print("🔄 Setting up network monitoring for m3u8 files...")
            
            def handle_response(response):
                if '.m3u8' in response.url:
                    m3u8_urls.append(response.url)
                    print(f"🎯 Found m3u8 URL: {response.url}")
            
            self.page.on('response', handle_response)
            
            # Also monitor iframe responses
            def handle_frame_navigated(frame):
                print(f"📺 Frame navigated: {frame.url}")
                frame.on('response', handle_response)
            
            self.page.on('framenavigated', handle_frame_navigated)
            
            # Navigate to the page with multiple fallback strategies
            response = None
            navigation_strategies = [
                {'wait_until': 'domcontentloaded', 'timeout': 45000},
                {'wait_until': 'load', 'timeout': 45000},
                {'wait_until': 'networkidle', 'timeout': 60000}
            ]
            
            for i, strategy in enumerate(navigation_strategies, 1):
                try:
                    print(f"🚀 Navigation attempt {i}/3 using {strategy['wait_until']}...")
                    print(f"🌐 Navigating to: {url}")
                    response = self.page.goto(url, **strategy)
                    actual_url = self.page.url
                    print(f"📍 Actually loaded: {actual_url}")
                    break
                except Exception as e:
                    print(f"⚠️ Navigation attempt {i} failed: {e}")
                    if i == len(navigation_strategies):
                        # If all strategies fail, try without wait condition
                        print("🔄 Trying basic navigation without wait condition...")
                        print(f"🌐 Final attempt to: {url}")
                        response = self.page.goto(url, timeout=45000)
                        actual_url = self.page.url
                        print(f"📍 Finally loaded: {actual_url}")
                    continue
            
            if response and response.status >= 400:
                print(f"⚠️ Page returned status {response.status}")
            
            print("✅ Page loaded successfully")
            
            # Wait for iframe to load completely
            print("⏳ Waiting for iframe to load...")
            try:
                self.page.wait_for_timeout(5000)  # Give iframe time to load
            except Exception as e:
                print(f"⚠️ Iframe wait error: {e}")
                # Continue anyway
            
            # Find and interact with the video player iframe
            try:
                # Look for video player iframe
                iframe_element = self.page.query_selector('iframe')
                if iframe_element:
                    iframe_src = iframe_element.get_attribute('src')
                    print(f"🎬 Found iframe: {iframe_src}")
                    
                    # Wait for iframe to fully load
                    try:
                        self.page.wait_for_timeout(3000)
                    except Exception as e:
                        print(f"⚠️ Iframe load wait error: {e}")
                        # Continue anyway
                    
                    # Multiple attempts to trigger video loading
                    for attempt in range(3):
                        print(f"🎬 Video trigger attempt {attempt + 1}/3")
                        
                        # Try clicking on the iframe area to start video
                        try:
                            iframe_element.click()
                            print("🖱️ Clicked on iframe")
                        except:
                            pass
                        
                        # Also try clicking in the center of the iframe
                        try:
                            box = iframe_element.bounding_box()
                            if box:
                                center_x = box['x'] + box['width'] / 2
                                center_y = box['y'] + box['height'] / 2
                                self.page.mouse.click(center_x, center_y)
                                print(f"🖱️ Clicked iframe center at ({center_x}, {center_y})")
                        except:
                            pass
                        
                        # Try double-clicking
                        try:
                            self.page.mouse.dblclick(center_x, center_y)
                            print("🖱️ Double-clicked iframe center")
                        except:
                            pass
                        
                        # Try pressing space key to play
                        try:
                            self.page.keyboard.press('Space')
                            print("⌨️ Pressed Space key")
                        except:
                            pass
                        
                        # Try pressing Enter key
                        try:
                            self.page.keyboard.press('Enter')
                            print("⌨️ Pressed Enter key")
                        except:
                            pass
                        
                        # Wait a bit between attempts
                        try:
                            self.page.wait_for_timeout(2000)
                        except:
                            pass
                        
                        # Check if we got any m3u8 URLs
                        if m3u8_urls:
                            print(f"✅ Found URLs after attempt {attempt + 1}")
                            break
                        
                # Also try general video selectors
                video_selectors = ['video', '.play-button', '.play', '.video-play', 'button[aria-label*="play"]', '.vjs-big-play-button']
                for selector in video_selectors:
                    try:
                        element = self.page.query_selector(selector)
                        if element and element.is_visible():
                            print(f"🖱️ Clicking on {selector}")
                            element.click()
                            try:
                                self.page.wait_for_timeout(1000)
                            except Exception as e:
                                print(f"⚠️ Video click wait error: {e}")
                                # Continue anyway
                    except:
                        continue
                        
            except Exception as e:
                print(f"⚠️ Video trigger error: {e}")
            
            # Wait longer for video to fully load and make network requests
            print("⏳ Waiting 10 seconds for video to load and make requests...")
            try:
                self.page.wait_for_timeout(10000)
            except Exception as e:
                print(f"⚠️ Wait timeout error: {e}")
                # Continue anyway, we might have captured some URLs
            
            # Remove duplicates
            m3u8_urls = list(set(m3u8_urls))
            
            if m3u8_urls:
                print(f"🎉 Found {len(m3u8_urls)} m3u8 URL(s)")
                for i, found_url in enumerate(m3u8_urls, 1):
                    print(f"   {i}. {found_url}")
            else:
                print("❌ No m3u8 URLs found")
                
        except Exception as e:
            print(f"❌ Error extracting m3u8 URL: {e}")
        
        return m3u8_urls
    
    def download_with_ffmpeg(self, m3u8_url, output_filename):
        """Download m3u8 using FFmpeg"""
        try:
            print(f"📥 Downloading with FFmpeg: {m3u8_url}")
            
            cmd = [
                'ffmpeg',
                '-i', m3u8_url,
                '-c', 'copy',
                '-bsf:a', 'aac_adtstoasc',
                '-y',  # Overwrite output file
                output_filename
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✅ FFmpeg download successful: {output_filename}")
                return True
            else:
                print(f"❌ FFmpeg failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ FFmpeg download error: {e}")
            return False
    
    def download_with_python(self, m3u8_url, output_filename):
        """Download m3u8 using Python requests as fallback"""
        try:
            print(f"🐍 Downloading with Python: {m3u8_url}")
            
            # Parse the m3u8 playlist
            playlist = m3u8.load(m3u8_url)
            
            if not playlist.segments:
                print("❌ No segments found in m3u8 playlist")
                return False
            
            print(f"📋 Found {len(playlist.segments)} segments")
            
            # Download all segments
            segments_data = []
            for i, segment in enumerate(playlist.segments):
                segment_url = segment.uri
                if not segment_url:
                    print(f"⚠️ No URL for segment {i+1}")
                    continue
                    
                if not segment_url.startswith('http'):
                    segment_url = urljoin(m3u8_url, segment_url)
                
                print(f"⬇️ Downloading segment {i+1}/{len(playlist.segments)}")
                
                try:
                    response = requests.get(segment_url, timeout=10)
                    response.raise_for_status()
                    segments_data.append(response.content)
                except Exception as e:
                    print(f"⚠️ Error downloading segment {i+1}: {e}")
                    continue
            
            # Combine all segments
            if segments_data:
                print(f"🔗 Combining {len(segments_data)} segments...")
                with open(output_filename, 'wb') as f:
                    for segment_data in segments_data:
                        f.write(segment_data)
                print(f"✅ Python download successful: {output_filename}")
                return True
            else:
                print("❌ No segments downloaded")
                return False
                
        except Exception as e:
            print(f"❌ Python download error: {e}")
            return False
    
    def download_m3u8_file(self, m3u8_url, output_filename):
        """Download m3u8 file using FFmpeg or Python fallback"""
        print(f"📥 Downloading m3u8 file: {m3u8_url}")
        
        # Try FFmpeg first
        if self.download_with_ffmpeg(m3u8_url, output_filename):
            return True
        
        # Fall back to Python if FFmpeg fails
        print("🔄 FFmpeg failed, trying Python fallback...")
        return self.download_with_python(m3u8_url, output_filename)
    
    def download_video(self, url, output_filename=None, convert_to_mp4=False):
        """Download video from kukaj.fi URL"""
        print(f"🎬 Starting download from: {url}")
        
        # Normalize the URL
        normalized_url, was_changed = normalize_kukaj_url(url)
        if was_changed:
            print(f"🔄 Normalized URL: {normalized_url}")
            url = normalized_url
        
        # Extract m3u8 URLs
        m3u8_urls = self.extract_m3u8_url(url)
        
        if not m3u8_urls:
            print("❌ No video URLs found")
            return False
        
        # Use the first m3u8 URL found
        m3u8_url = m3u8_urls[0]
        print(f"📹 Using video URL: {m3u8_url}")
        
        # Generate output filename if not provided
        if not output_filename:
            # Extract filename from URL
            parsed_url = urlparse(url)
            path_parts = parsed_url.path.strip('/').split('/')
            
            if len(path_parts) >= 2:
                # For URLs like https://serial.kukaj.fi/show/S01E01
                if len(path_parts) >= 3:
                    filename = f"{path_parts[-2]}_{path_parts[-1]}"
                else:
                    filename = path_parts[-1]
            else:
                filename = path_parts[-1] if path_parts else "video"
            
            # Clean filename
            filename = re.sub(r'[^\w\-_\.]', '_', filename)
            output_filename = f"{filename}.m3u8"
        
        # Ensure we're saving to the downloads directory
        downloads_dir = os.path.join(os.getcwd(), 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        
        # Update output filename to include downloads directory
        if not output_filename.startswith(downloads_dir):
            output_filename = os.path.join(downloads_dir, os.path.basename(output_filename))
        
        print(f"💾 Output filename: {output_filename}")
        
        # Download the video
        success = self.download_m3u8_file(m3u8_url, output_filename)
        
        if success:
            print(f"✅ Download completed: {output_filename}")
            
            # Convert to MP4 if requested
            if convert_to_mp4:
                mp4_filename = output_filename.replace('.m3u8', '.mp4')
                print(f"🔄 Converting to MP4: {mp4_filename}")
                
                cmd = [
                    'ffmpeg',
                    '-i', output_filename,
                    '-c', 'copy',
                    '-y',
                    mp4_filename
                ]
                
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode == 0:
                        print(f"✅ MP4 conversion successful: {mp4_filename}")
                        return mp4_filename
                    else:
                        print(f"⚠️ MP4 conversion failed: {result.stderr}")
                        return output_filename
                except Exception as e:
                    print(f"⚠️ MP4 conversion error: {e}")
                    return output_filename
            
            return output_filename
        else:
            print("❌ Download failed")
            return False
    
    def close(self):
        """Close browser and cleanup"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def main():
    """Main function for command line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Download videos from kukaj.fi')
    parser.add_argument('url', help='kukaj.fi video URL')
    parser.add_argument('-o', '--output', help='Output filename')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    parser.add_argument('--mp4', action='store_true', help='Convert to MP4 after download')
    
    args = parser.parse_args()
    
    try:
        with KukajDownloader(headless=args.headless) as downloader:
            success = downloader.download_video(
                args.url, 
                output_filename=args.output,
                convert_to_mp4=args.mp4
            )
            
            if success:
                print(f"🎉 Success! Downloaded: {success}")
            else:
                print("❌ Download failed")
                exit(1)
                
    except KeyboardInterrupt:
        print("\n⚠️ Download interrupted by user")
        exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
URL           = "https://film.kukaj.fi/matrix"   # <-- any Kukaj* URL
HEADLESS      = False                           # set True for Termux / CI
WAIT_SECONDS  = 15                              # time to wait for video JS
DOWNLOAD_DIR  = Path("downloads")
# ---------------------------------------------------------------------------


async def main():
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.firefox.launch(
            headless=HEADLESS,
            firefox_user_prefs={
                # IMPORTANT: all proxies off – avoids "0.0.7.128" detour
                "network.proxy.type": 0,
                "network.proxy.no_proxies_on": "",
                # Disable DOH / TRR so normal system DNS is used
                "network.trr.mode": 5,
            },
            # Keep the args list short – many chromium-only flags break Firefox
            args=["--width=1920", "--height=1080"],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) "
                "Gecko/20100101 Firefox/120.0"
            ),
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )

        page = await context.new_page()

        m3u8_urls = []

        # --- network listeners ------------------------------------------------
        async def sniff(route_or_resp):
            url = route_or_resp.url
            if ".m3u8" in url:
                if url not in m3u8_urls:
                    m3u8_urls.append(url)
                    print(f"🎯  m3u8 →  {url}")

        page.on("request", sniff)
        page.on("response", sniff)

        # all future iframes inherit the listeners
        context.on("page", lambda new_page: (
            new_page.on("request", sniff),
            new_page.on("response", sniff),
        ))

        print(f"🌐  GOTO  {URL}")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        # give the site (and hidden iframes) some time to run JS
        print(f"⏳  waiting {WAIT_SECONDS}s for video player …")
        await page.wait_for_timeout(WAIT_SECONDS * 1000)

        # ---------------------------------------------------------------------
        if m3u8_urls:
            best = m3u8_urls[0]
            print(f"\n✅  first m3u8: {best}")
            # OPTIONAL: download straight away with ffmpeg --------------------
            out = DOWNLOAD_DIR / (urlparse(URL).path.strip("/").replace("/", "_") + ".m3u8")
            print(f"⬇️   saving playlist to  {out}")
            out.write_text(await (await context.request.get(best)).text())
        else:
            print("\n❌  no m3u8 found – try a longer wait or check the site")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main()) 