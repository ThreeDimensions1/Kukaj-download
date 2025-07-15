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
            
            # Store context for later (e.g., cookie extraction)
            self.context = context

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
                        if btn_locator.count() == 0:
                            # Fallback – search anywhere on the page
                            btn_locator = self.page.get_by_text(source.upper(), exact=True)

                        if btn_locator.count() == 0:
                            raise ValueError("Source button not found")

                        # Check if it's an <a href="/something"> link
                        href = btn_locator.first.get_attribute("href")

                        if href and href not in ("#", "", "javascript:void(0)"):
                            from urllib.parse import urljoin
                            next_url = urljoin(url, href)
                            print(f"↪️  Navigating to source URL: {next_url}")
                            self.page.goto(next_url, wait_until='domcontentloaded', timeout=30000)

                            # If destination is a Streamtape page, grab video source instantly
                            if any(x in self.page.url for x in ["streamtape.com", "tapecontent.net", "streamta.pe"]):
                                try:
                                    self.page.wait_for_selector("video", timeout=5000)
                                    direct_src = self.page.evaluate("() => document.querySelector('video') && document.querySelector('video').src")
                                    if direct_src and direct_src.startswith('http') and direct_src not in found_urls:
                                        found_urls.append(direct_src)
                                        print(f"🎯 Found media URL from direct Streamtape page: {direct_src}")
                                except Exception as st_err:
                                    print(f"⚠️  Streamtape direct extraction failed: {st_err}")
                        else:
                            # Serial pages sometimes place source links as plain anchors outside subplayermenu
                            # Quick path: look for any <a> containing the source text and an href ending with a digit
                            if source.upper() == 'TAP':
                                try:
                                    generic_anchor = self.page.locator(f"a:has-text('{source.upper()}')").first
                                    if generic_anchor.count() > 0:
                                        href_raw = generic_anchor.get_attribute('href')
                                        if href_raw and href_raw not in ("#", "javascript:void(0)"):
                                            from urllib.parse import urljoin
                                            abs_href = urljoin(url, href_raw)
                                            if abs_href != self.page.url:
                                                print(f"↪️  Direct anchor navigation to: {abs_href}")
                                                self.page.goto(abs_href, wait_until='domcontentloaded', timeout=30000)
                                                # allow embedded player to load
                                                self.page.wait_for_timeout(4000)
                                except Exception:
                                    pass
                            # Regular in-page AJAX style: just click
                            btn_locator.first.click(timeout=5000)
                    except Exception as e:
                        print(f"⚠️  Activating source via click/navigation failed: {e}")
                        # final fallback – trigger click via JS if we still have element
                        try:
                            self.page.evaluate("el => el.click()", btn_locator.first)
                        except Exception:
                            pass

                    # give site some time after activating new source – wait for network idle
                    try:
                        self.page.wait_for_load_state('networkidle', timeout=10000)
                    except Exception:
                        # ignore timeout – we'll rely on passive wait below
                        pass
                    # extra passive wait for any iframe traffic
                    self.page.wait_for_timeout(4000)
                    # Immediate frame scan for Streamtape
                    for frm in self.page.frames:
                        try:
                            if 'streamtape' in frm.url or 'streamta.pe' in frm.url:
                                candidate = frm.evaluate("() => (document.querySelector('video') && document.querySelector('video').src) || null")
                                if candidate and candidate.startswith('http') and candidate not in found_urls:
                                    found_urls.append(candidate)
                                    print(f"🎯 Found media URL via immediate Streamtape scan: {candidate}")
                        except Exception:
                            pass
                except Exception as click_err:
                    print(f"⚠️  Unable to activate source '{source}': {click_err}")

            # Passive wait – only if we *still* have no URL
            if not found_urls:
                print(f"⌛ Passive wait {self.wait_sec}s for media requests …")
                self.page.wait_for_timeout(self.wait_sec * 1000)
            else:
                print("⚡ Skipping passive wait – URL already captured")

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
        """Stream an MP4 file with requests, adding typical browser headers and any cookies captured by Playwright."""
        try:
            import requests
            from urllib.parse import urlparse

            print(f"🐍 Downloading MP4 via Python: {mp4_url}")

            # --------------------------------------------------
            # Build headers – many hosts (e.g. Streamtape) block
            # requests that lack a Referer or proper User-Agent.
            # --------------------------------------------------
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
                "Accept": "*/*",
            }

            if any(h in mp4_url for h in ["streamtape", "tapecontent"]):
                # Streamtape requires a valid referer header
                headers["Referer"] = "https://streamtape.com/"

            # Attach cookies from the browsing session if available
            try:
                if self.context:
                    host = urlparse(mp4_url).hostname or ""
                    cookie_parts = []
                    for c in self.context.cookies():
                        name = c.get('name')
                        value = c.get('value')
                        domain = c.get('domain')
                        if name and value and domain and host.endswith(domain.lstrip('.')):
                            cookie_parts.append(f"{name}={value}")
                    cookie_str = "; ".join(cookie_parts)
                    if cookie_str:
                        headers["Cookie"] = cookie_str
            except Exception:
                pass  # Fallback silently if cookie extraction fails

            with requests.get(mp4_url, stream=True, timeout=60, headers=headers) as r:
                r.raise_for_status()

                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                last_pct = -1

                with open(output_filename, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1 MB chunks
                        if chunk:
                            f.write(chunk)
                            if total:
                                downloaded += len(chunk)
                                pct = int(downloaded / total * 100)
                                if pct >= last_pct + 10:
                                    print(f"📥 ... {pct}%")
                                    last_pct = pct

            print(f"✅ MP4 download successful: {output_filename}")
            return True
        except Exception as e:
            print(f"❌ MP4 Python download error: {e}")
            return False

    def download_mp4_file(self, mp4_url, output_filename):
        """Download MP4 file – try fast Python streaming first, then fall back to FFmpeg if necessary."""

        # 1️⃣ Python streaming (most hosts, including Streamtape, work fine with correct headers)
        if self.download_mp4_python(mp4_url, output_filename):
            return True

        # 2️⃣ Fallback – attempt FFmpeg copy
        try:
            print(f"📥 Retrying MP4 download with FFmpeg: {mp4_url}")
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
                print(f"❌ FFmpeg MP4 failed: {result.stderr.strip()}")
                return False
        except FileNotFoundError:
            print("⚠️  FFmpeg not available and Python download already failed.")
            return False
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


async def demo_async():
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
        def _attach(new_page):
            new_page.on("request", sniff)
            new_page.on("response", sniff)

        context.on("page", _attach)

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

# ---------------------------------------------------------------------------
# The async demonstration above is disabled by default to prevent interference
# with the standard CLI entrypoint. Uncomment the following lines to try it
# manually:
#
# if __name__ == "__main__":
#     asyncio.run(demo_async()) 