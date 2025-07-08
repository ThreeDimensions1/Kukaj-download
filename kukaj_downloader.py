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
    def __init__(self, headless=True, wait_sec: int = 12, verbose=False):
        """Downloader

        wait_sec – how many seconds to passively wait after navigation so that the
        video player has time to start issuing HLS (.m3u8) requests. 12 s has
        proven enough for Kukaj.
        """
        self.headless = headless
        self.wait_sec = wait_sec
        self.playwright = None
        self.browser = None
        self.page = None
        self.context = None
        self.verbose = verbose
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
    
    # ------------------------------------------------------------------
    # MEDIA URL EXTRACTION (M3U8 + MP4) --------------------------------
    # ------------------------------------------------------------------

    def extract_media_urls(self, url, source: str | None = None):
        """Extract media URLs (.m3u8 or .mp4) from the Kukaj page.

        Args:
            url (str): Original Kukaj video URL (film or serie page)
            source (str|None): Optional preferred source shortcut e.g. "MON", "TAP", "MIX".
                               If provided, the corresponding button is clicked after page load
                               to force the desired host.

        Returns:
            list[str]: list of unique media URLs discovered on the network
        """

        print(f"🔍 Loading page: {url}")

        if not self.page:
            print("❌ Page not initialized")
            return []

        found_urls: list[str] = []

        try:
            # -----------------------------------------------------------
            # Network sniffers – watch every request AND response in page
            # -----------------------------------------------------------
            print("🔄 Setting up network sniffers …")
            ctx = self.page.context

            def _sniff(route_or_resp):
                u = route_or_resp.url.lower()
                if (".m3u8" in u or ".mp4" in u) and (u not in found_urls):
                    found_urls.append(route_or_resp.url)
                    print(f"🎯 Found media URL: {route_or_resp.url}")

            ctx.on('request', _sniff)
            ctx.on('response', _sniff)

            # -----------------------------------------------------------
            # Navigate to main page
            # -----------------------------------------------------------
            print(f"🌐 GOTO  {url}")
            response = self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
            print(f"📍 Page status: {response.status if response else 'unknown'}")

            if response and response.status >= 400:
                print(f"⚠️ Page returned status {response.status}")

            # Optionally click desired source button (MON/TAP/MIX …)
            if source:
                try:
                    # Ensure source menu is present
                    self.page.wait_for_selector("div.subplayermenu", timeout=5000)

                    # Playwright best-practice: use :has-text() or get_by_text for reliability
                    print(f"➡️  Activating source button: {source.upper()}")
                    btn_locator = self.page.locator("div.subplayermenu").get_by_text(source.upper(), exact=True)
                    awaitable = None
                    try:
                        # Prefer clicking the <a> element for proper ajax handling
                        if btn_locator.count() > 0:
                            awaitable = btn_locator.first.click(timeout=5000)
                        else:
                            # Fallback – click by text anywhere
                            awaitable = self.page.get_by_text(source.upper(), exact=True).first.click(timeout=5000)
                    except Exception as e:
                        print(f"⚠️  Direct click failed: {e}")
                        # final fallback – click underlying button via JS
                        self.page.evaluate("el => el.click()", btn_locator.first)

                    # give site some time after activating new source – wait for network idle
                    try:
                        self.page.wait_for_load_state('networkidle', timeout=10000)
                    except Exception:
                        # ignore timeout – we'll rely on passive wait below
                        pass
                    # extra passive wait for any iframe traffic
                    self.page.wait_for_timeout(4000)
                except Exception as click_err:
                    print(f"⚠️  Unable to activate source '{source}': {click_err}")

            # Passive wait – let player/iframe emit network traffic
            print(f"⌛ Passive wait {self.wait_sec}s for media requests …")
            self.page.wait_for_timeout(self.wait_sec * 1000)

            # Deduplicate
            found_urls = list(dict.fromkeys(found_urls))

            if found_urls:
                print(f"🎉 Found {len(found_urls)} media URL(s)")
                for i, fu in enumerate(found_urls, 1):
                    print(f"   {i}. {fu}")
            else:
                print("❌ No media URLs found")

        except Exception as e:
            print(f"❌ Error extracting media URLs: {e}")

        return found_urls

    # Backwards compatibility -------------------------------------------------
    def extract_m3u8_url(self, url, source: str | None = None):
        """Alias to :py:meth:`extract_media_urls` for legacy calls."""
        return self.extract_media_urls(url, source)
    
    # ------------------------------------------------------------------
    # DOWNLOAD HELPERS (MP4 & M3U8)
    # ------------------------------------------------------------------

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
    
    # --------- MP4 helpers ---------------------------------------------------

    def download_mp4_python(self, mp4_url, output_filename):
        """Simple Python streaming download for MP4 files."""
        try:
            import requests
            print(f"🐍 Downloading MP4 via Python: {mp4_url}")
            with requests.get(mp4_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(output_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            print(f"✅ MP4 download successful: {output_filename}")
            return True
        except Exception as e:
            print(f"❌ MP4 Python download error: {e}")
            return False

    def download_mp4_file(self, mp4_url, output_filename):
        """Download MP4 file – try ffmpeg copy first then fallback to Python."""
        try:
            print(f"📥 Downloading MP4 with FFmpeg: {mp4_url}")
            cmd = [
                'ffmpeg',
                '-i', mp4_url,
                '-c', 'copy',
                '-y',
                output_filename
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ FFmpeg MP4 download successful: {output_filename}")
                return True
            else:
                print(f"⚠️  FFmpeg MP4 failed: {result.stderr.strip()}")
                print("🔄 Falling back to Python stream download …")
                return self.download_mp4_python(mp4_url, output_filename)
        except FileNotFoundError:
            print("⚠️  FFmpeg not found – using Python stream download …")
            return self.download_mp4_python(mp4_url, output_filename)
        except Exception as e:
            print(f"❌ MP4 download error: {e}")
            return False

    # ------------------------------------------------------------------
    # PUBLIC ENTRY ------------------------------------------------------
    # ------------------------------------------------------------------

    def download_video(self, url, output_filename: str | None = None, convert_to_mp4: bool = False, source: str | None = None):
        """Download video from kukaj.fi URL"""
        print(f"🎬 Starting download from: {url}")
        
        # Normalize the URL
        normalized_url, was_changed = normalize_kukaj_url(url)
        if was_changed:
            print(f"🔄 Normalized URL: {normalized_url}")
            url = normalized_url
        
        # Extract media URLs (.m3u8 or .mp4)
        media_urls = self.extract_media_urls(url, source)

        if not media_urls:
            print("❌ No video URLs found")
            return False

        # Prioritise according to extension / preference
        preferred_order = [
            lambda u: u.lower().endswith('.m3u8'),  # HLS first
            lambda u: '.m3u8' in u.lower(),
            lambda u: u.lower().endswith('.mp4'),
            lambda u: '.mp4' in u.lower(),
        ]

        media_urls.sort(key=lambda u: next((i for i, f in enumerate(preferred_order) if f(u)), 999))

        media_url = media_urls[0]
        print(f"📹 Using media URL: {media_url}")
        
        # Generate output filename if not provided
        if not output_filename:
            # Extract filename from original page URL
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
            
            # Decide extension based on media_url
            ext = '.mp4' if '.mp4' in media_url.lower() else '.m3u8'
            output_filename = f"{filename}{ext}"
        
        # Ensure downloads directory exists and path is correct
        downloads_dir = os.path.join(os.getcwd(), 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        if not output_filename.startswith(downloads_dir):
            output_filename = os.path.join(downloads_dir, os.path.basename(output_filename))
        
        print(f"💾 Output filename: {output_filename}")
        
        # Download according to extension
        if '.m3u8' in media_url.lower():
            success = self.download_m3u8_file(media_url, output_filename)
        else:
            # For direct MP4 we ignore convert_to_mp4 flag (already mp4)
            success = self.download_mp4_file(media_url, output_filename)
        
        if success:
            print(f"✅ Download completed: {output_filename}")
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