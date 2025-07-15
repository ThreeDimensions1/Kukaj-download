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

# removed dynamic legacy import – we now embed legacy TAP logic directly


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
        proven enough for Kukaj, but reduced for ARM devices.
        """
        self.headless = headless
        # Reduce wait time for ARM devices to avoid timeouts
        import platform
        platform_machine = platform.machine().lower()
        if 'arm' in platform_machine or 'aarch64' in platform_machine:
            self.wait_sec = min(wait_sec, 8)  # Max 8 seconds for ARM
            print(f"🔧 ARM device detected, reducing wait time to {self.wait_sec}s")
        else:
            self.wait_sec = wait_sec
        
        self.playwright = None
        self.browser = None
        self.page = None
        self.context = None
        self.verbose = verbose
        self.setup_playwright()
    
    def setup_playwright(self):
        """Set up Playwright with ARM-optimized settings"""
        try:
            print("🎭 Setting up Playwright...")
            
            # Use sync playwright for simpler API
            self.playwright = sync_playwright().start()
            
            # ARM-optimized Firefox settings for Banana Pi M5
            firefox_prefs = {
                    'network.proxy.type': 0,  # No proxy
                    'network.proxy.no_proxies_on': 'localhost, 127.0.0.1',
                    'network.http.use-cache': False,
                    'media.volume_scale': '0.0',  # Mute audio
                    'dom.webdriver.enabled': False,
                    'useAutomationExtension': False,
                    'network.trr.mode': 5,
                # ARM optimizations
                'gfx.canvas.azure.backends': 'cairo',  # Use software rendering
                'layers.acceleration.disabled': True,  # Disable hardware acceleration
                'webgl.disabled': True,  # Disable WebGL
                'media.hardware-video-decoding.enabled': False,  # Disable hardware video decoding
                'browser.sessionstore.resume_from_crash': False,  # Disable crash recovery
                'browser.cache.disk.enable': False,  # Disable disk cache
                'browser.cache.memory.enable': False,  # Disable memory cache
            }
            
            # Try to launch Firefox first – if it fails (common on some ARM builds),
            # automatically fall back to Chromium so the downloader still works.
            try:
                # Launch Firefox browser with ARM-optimized settings
                self.browser = self.playwright.firefox.launch(
                    headless=self.headless,
                    firefox_user_prefs=firefox_prefs,
                args=[
                        '--width=1280',  # Reduced resolution for ARM
                        '--height=720',
                    '--no-remote',
                        '--disable-extensions',
                        '--disable-dev-shm-usage',  # Avoid shared memory issues
                        '--no-sandbox',  # Avoid sandbox issues on ARM
                    ]
                )
                browser_engine = 'Firefox'
            except Exception as firefox_err:
                print(f"⚠️  Firefox launch failed on this platform: {firefox_err}\n   ➡️  Falling back to Chromium …")
                self.browser = self.playwright.chromium.launch(
                    headless=self.headless,
                    args=[
                        '--disable-gpu',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-extensions',
                        '--window-size=1280,720',
                    ]
                )
                browser_engine = 'Chromium'
            
            # Create browser context with ARM-optimized settings – UA differs per engine for realism
            ua_default = {
                'Firefox': 'Mozilla/5.0 (X11; Linux armv7l; rv:120.0) Gecko/20100101 Firefox/120.0',
                'Chromium': 'Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            }[browser_engine]

            context = self.browser.new_context(
                user_agent=ua_default,
                viewport={'width': 1280, 'height': 720},  # Reduced viewport
                ignore_https_errors=True,
                java_script_enabled=True,
                bypass_csp=True,
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',  # Removed br for ARM compatibility
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'no-cache'
                }
            )
            
            # Store context for later
            self.context = context
            
            # Create page
            self.page = context.new_page()
            
            # ARM-optimized timeouts (shorter for better reliability)
            self.page.set_default_timeout(30000)  # 30 seconds
            self.page.set_default_navigation_timeout(30000)  # 30 seconds
            
            print(f"✅ Playwright setup complete using {browser_engine} (ARM-optimized)")
            
        except Exception as e:
            print(f"❌ Failed to initialize Playwright: {e}")
            print("💡 Try running: playwright install firefox")
            print("💡 On ARM devices, ensure you have sufficient memory and swap space")
            raise
    
    # ------------------------------------------------------------------
    # LEGACY TAP EXTRACTION --------------------------------------------
    # ------------------------------------------------------------------
    def _tap_extract_legacy(self, url: str, found_urls: list[str]):
        """Legacy, proven TAP extraction ported from previous version.
        Mutates and returns found_urls list if successful.
        """
        try:
            if self.page is None:
                return found_urls
            print("🕹️  Legacy TAP extractor engaged …")
            # Ensure source menu
            try:
                self.page.wait_for_selector("div.subplayermenu", timeout=5000)
            except Exception:
                pass

            # 1️⃣ Try to locate TAP button inside subplayermenu
            btn_locator = self.page.locator("div.subplayermenu").get_by_text("TAP", exact=True)
            if btn_locator.count() == 0:
                btn_locator = self.page.get_by_text("TAP", exact=True)

            if btn_locator.count() == 0:
                print("⚠️  TAP button not found via text lookup – trying generic anchor …")
                generic_anchor = self.page.locator("a:has-text('TAP')").first
                if generic_anchor.count() > 0:
                    href_raw = generic_anchor.get_attribute('href')
                    if href_raw and href_raw not in ("#", "", "javascript:void(0)"):
                        from urllib.parse import urljoin
                        abs_href = urljoin(url, href_raw)
                        print(f"↪️  Navigating to TAP href: {abs_href}")
                        self.page.goto(abs_href, wait_until='domcontentloaded', timeout=30000)
                        self.page.wait_for_timeout(4000)
                else:
                    print("❌ TAP anchor not found, legacy extractor failed early")
                    return []
            else:
                href = btn_locator.first.get_attribute("href")
                if href and href not in ("#", "", "javascript:void(0)"):
                    from urllib.parse import urljoin
                    next_url = urljoin(url, href)
                    print(f"↪️  Navigating to TAP href: {next_url}")
                    self.page.goto(next_url, wait_until='domcontentloaded', timeout=30000)
                else:
                    btn_locator.first.click(timeout=5000)

            # Allow network idle then small passive wait
            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass
            self.page.wait_for_timeout(4000)

            # Immediate frame scan for Streamtape video elements
            for frm in self.page.frames:
                try:
                    if any(dom in frm.url for dom in ["streamtape", "streamta.pe", "tapecontent"]):
                        candidate = frm.evaluate("() => (document.querySelector('video') && document.querySelector('video').src) || null")
                        if candidate and candidate.startswith('http') and candidate not in found_urls:
                            # STRICT FILTERING: Only accept URLs from streamtape domains
                            if any(dom in candidate.lower() for dom in ["streamtape", "streamta.pe", "tapecontent"]):
                                found_urls.append(candidate)
                                print(f"🎯 (Legacy) Found video URL: {candidate}")
                except Exception:
                    pass

            # Passive wait if still nothing
            return found_urls
        except Exception as legacy_err:
            print(f"⚠️ Legacy TAP extractor error: {legacy_err}")
            return []

    # ------------------------------------------------------------------
    # LEGACY MON EXTRACTION -------------------------------------------
    # ------------------------------------------------------------------
    def _mon_extract_legacy(self, url: str, found_urls: list[str]):
        """Simplified legacy MON extractor – mirrors behaviour from kukaj_downloader_old.py but scoped to MON."""
        try:
            if self.page is None:
                return found_urls

            print("🕹️  Legacy MON extractor engaged …")

            # Store listeners to remove them later
            listeners = []

            def _sniff(route_or_resp):
                u = route_or_resp.url.lower()
                if ".m3u8" in u and u not in found_urls:
                    found_urls.append(route_or_resp.url)
                    print(f"🎯 (Legacy MON) Found m3u8 URL: {route_or_resp.url}")

            # Add listeners and track them
            ctx = self.page.context
            ctx.on("request", _sniff)
            ctx.on("response", _sniff)
            listeners.append(("request", _sniff))
            listeners.append(("response", _sniff))

            # Navigate if not there
            if self.page.url != url:
                self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Click MON button if present
            try:
                self.page.wait_for_selector("div.subplayermenu", timeout=5000)
                btn = self.page.locator("div.subplayermenu").get_by_text("MON", exact=True)
                if btn.count() == 0:
                    btn = self.page.get_by_text("MON", exact=True)
                if btn.count() > 0:
                    btn.first.click(timeout=5000)
            except Exception:
                pass

            # Passive wait longer (15 s) – Filemoon is slower to load
            self.page.wait_for_timeout(15000)

            # Remove listeners to avoid duplicates
            for event_type, listener in listeners:
                ctx.remove_listener(event_type, listener)

            return found_urls
        except Exception as e:
            print(f"⚠️ Legacy MON extractor error: {e}")
            return found_urls


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
        # Track all listeners to clean them up later
        all_listeners = []
        # Flag to indicate if we should stop extraction
        should_stop_extraction = False
        
        try:
            # For TAP source, use only the legacy extractor which is proven to work
            if source and source.upper() == 'TAP':
                print("🔄 Using legacy TAP extractor directly")
                self._tap_extract_legacy(url, found_urls)
                
                # STRICT FILTERING: Only accept URLs from streamtape domains
                if found_urls:
                    filtered_urls = []
                    for u in found_urls:
                        if any(host in u.lower() for host in ['streamtape', 'tapecontent', 'streamta.pe']):
                            filtered_urls.append(u)
                    
                    if filtered_urls:
                        print(f"🎯 Filtered {len(found_urls)} URLs to {len(filtered_urls)} legitimate Streamtape sources")
                        found_urls = filtered_urls
                    else:
                        print("⚠️ All found URLs were filtered out as non-Streamtape")
                
                # If we found valid URLs, return them immediately
                if found_urls:
                    print(f"🎉 Found {len(found_urls)} media URL(s)")
                    for i, fu in enumerate(found_urls, 1):
                        print(f"   {i}. {fu}")
                    return found_urls
            
            # For MON sources, try URL-based selection first to catch early m3u8 requests
            if source and source.upper() == 'MON':
                print("🔄 Using URL-based MON selection first to catch early m3u8 requests")
                
                # -----------------------------------------------------------
                # Network sniffers – set up BEFORE navigation
                # -----------------------------------------------------------
                print("🔄 Setting up network sniffers for MON…")
                ctx = self.page.context

                def _sniff_mon_request(route):
                    nonlocal should_stop_extraction
                    u = route.url.lower()
                    # Filter URLs to include only legitimate video sources
                    if (".m3u8" in u) and (u not in found_urls):
                        found_urls.append(route.url)
                        print(f"🎯 Found MON m3u8 URL: {route.url}")
                        # Mark for early return but don't actually return
                        if len(found_urls) >= 1:
                            should_stop_extraction = True

                def _sniff_mon_response(response):
                    nonlocal should_stop_extraction
                    u = response.url.lower()
                    # Filter URLs to include only legitimate video sources
                    if (".m3u8" in u) and (u not in found_urls):
                        found_urls.append(response.url)
                        print(f"🎯 Found MON m3u8 URL: {response.url}")
                        # Mark for early return but don't actually return
                        if len(found_urls) >= 1:
                            should_stop_extraction = True

                # Register listeners and track them
                ctx.on('request', _sniff_mon_request)
                ctx.on('response', _sniff_mon_response)
                all_listeners.append(('request', _sniff_mon_request))
                all_listeners.append(('response', _sniff_mon_response))
                
                # Try to construct a direct MON URL first
                try:
                    # Parse the original URL
                    from urllib.parse import urlparse, urljoin
                    parsed_url = urlparse(url)
                    path_parts = parsed_url.path.strip('/').split('/')
                    
                    # Attempt to construct a MON URL
                    if len(path_parts) >= 1:
                        # For film URLs like /matrix
                        if len(path_parts) == 1:
                            mon_url = urljoin(url, f"{path_parts[0]}/1")
                        # For series URLs like /series-name/S01E01
                        elif len(path_parts) >= 2:
                            mon_url = urljoin(url, f"{path_parts[0]}/{path_parts[1]}/1")
                        else:
                            mon_url = urljoin(url, "1")
                            
                        print(f"🌐 Trying direct MON URL: {mon_url}")
                        response = self.page.goto(mon_url, wait_until='domcontentloaded', timeout=30000)
                        print(f"📍 MON URL status: {response.status if response else 'unknown'}")
                        
                        # Wait for network activity to catch m3u8 requests
                        try:
                            self.page.wait_for_load_state('networkidle', timeout=10000)
                        except:
                            pass
                        
                        # Passive wait to catch any delayed requests
                        self.page.wait_for_timeout(5000)
                        
                        # If we found URLs, clean up listeners and return them
                        if found_urls or should_stop_extraction:
                            print(f"🎉 Found {len(found_urls)} media URL(s) via direct MON URL")
                            for i, fu in enumerate(found_urls, 1):
                                print(f"   {i}. {fu}")
                            
                            # Clean up listeners before returning
                            for event_type, listener in all_listeners:
                                ctx.remove_listener(event_type, listener)
                            return found_urls
                    
                    # If direct URL didn't work, fall back to regular flow
                    print("⚠️ Direct MON URL didn't yield results, falling back to regular flow")
                    
                    # Go back to original URL for regular flow
                    self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
                except Exception as mon_err:
                    print(f"⚠️ MON direct URL error: {mon_err}")
                    # Go back to original URL for regular flow
                    self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
                
                # Clean up listeners before continuing to avoid duplicates
                for event_type, listener in all_listeners:
                    ctx.remove_listener(event_type, listener)
                all_listeners = []
                should_stop_extraction = False  # Reset flag

            # --- If MON still not found after regular flow, fallback to legacy ---
            if source and source.upper() == 'MON' and not found_urls:
                print("🔄 Falling back to legacy MON extractor")
                self._mon_extract_legacy(url, found_urls)
                if found_urls:
                    return list(dict.fromkeys(found_urls))
            
            # For non-TAP sources or if TAP/MON direct methods failed, continue with normal flow
            # -----------------------------------------------------------
            # Network sniffers – watch every request AND response in page
            # -----------------------------------------------------------
            print("🔄 Setting up network sniffers …")
            ctx = self.page.context

            def _sniff_request(route):
                u = route.url.lower()
                # Filter URLs to include only legitimate video sources (exclude ads)
                if (".m3u8" in u or ".mp4" in u) and (u not in found_urls):
                    # For TAP source, only accept streamtape domains
                    if source and source.upper() == 'TAP':
                        if any(host in u for host in ['streamtape', 'tapecontent', 'streamta.pe']):
                            found_urls.append(route.url)
                            print(f"🎯 Found TAP media URL: {route.url}")
                    # For MON or other sources, accept m3u8 files
                    elif ".m3u8" in u:
                        found_urls.append(route.url)
                        print(f"🎯 Found m3u8 URL: {route.url}")
                    # For any source, accept mp4 from known hosts
                    elif ".mp4" in u and any(host in u for host in ['streamtape', 'tapecontent', 'streamta.pe']):
                        found_urls.append(route.url)
                        print(f"🎯 Found mp4 URL: {route.url}")

            def _sniff_response(response):
                u = response.url.lower()
                # Filter URLs to include only legitimate video sources (exclude ads)
                if (".m3u8" in u or ".mp4" in u) and (u not in found_urls):
                    # For TAP source, only accept streamtape domains
                    if source and source.upper() == 'TAP':
                        if any(host in u for host in ['streamtape', 'tapecontent', 'streamta.pe']):
                            found_urls.append(response.url)
                            print(f"🎯 Found TAP media URL: {response.url}")
                    # For MON or other sources, accept m3u8 files
                    elif ".m3u8" in u:
                        found_urls.append(response.url)
                        print(f"🎯 Found m3u8 URL: {response.url}")
                    # For any source, accept mp4 from known hosts
                    elif ".mp4" in u and any(host in u for host in ['streamtape', 'tapecontent', 'streamta.pe']):
                        found_urls.append(response.url)
                        print(f"🎯 Found mp4 URL: {response.url}")

            # Register listeners and track them
            ctx.on('request', _sniff_request)
            ctx.on('response', _sniff_response)
            all_listeners.append(('request', _sniff_request))
            all_listeners.append(('response', _sniff_response))

            # -----------------------------------------------------------
            # Navigate to main page if not already there
            # -----------------------------------------------------------
            if self.page.url != url:
                print(f"🌐 GOTO  {url}")
            response = self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
            print(f"📍 Page status: {response.status if response else 'unknown'}")
            
            if response and response.status >= 400:
                print(f"⚠️ Page returned status {response.status}")
            
            # Optionally click desired source button (MON/TAP/MIX …)
            if source:
                source_activated = False
                max_source_attempts = 3
                source_attempt = 0
                
                while not source_activated and source_attempt < max_source_attempts:
                    source_attempt += 1
                    try:
                        print(f"➡️  Activating source button: {source.upper()} (attempt {source_attempt}/{max_source_attempts})")
                        
                        # Wait for page to be ready
                        self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                        
                        # Try to find source menu with increased timeout for ARM devices
                        try:
                            self.page.wait_for_selector("div.subplayermenu", timeout=8000)
                        except:
                            print("⚠️  Source menu not found, trying alternative selectors...")
                            # Try alternative selectors
                            try:
                                self.page.wait_for_selector(f"[data-source='{source.upper()}']", timeout=3000)
                            except:
                                try:
                                    self.page.wait_for_selector(f"button:has-text('{source.upper()}')", timeout=3000)
                                except:
                                    pass

                        # Multiple strategies to find and click the source button
                        btn_locator = None
                        
                        # Strategy 1: Look in subplayermenu
                        try:
                            btn_locator = self.page.locator("div.subplayermenu").get_by_text(source.upper(), exact=True)
                            if btn_locator.count() > 0:
                                print(f"✅ Found source button in subplayermenu")
                            else:
                                btn_locator = None
                        except:
                            pass
                        
                        # Strategy 2: Look anywhere on page
                        if not btn_locator or btn_locator.count() == 0:
                            try:
                                btn_locator = self.page.get_by_text(source.upper(), exact=True)
                                if btn_locator.count() > 0:
                                    print(f"✅ Found source button on page")
                                else:
                                    btn_locator = None
                            except:
                                pass
                        
                        # Strategy 3: Look for data attributes or class names
                        if not btn_locator or btn_locator.count() == 0:
                            try:
                                btn_locator = self.page.locator(f"[data-source='{source.upper()}'], [data-host='{source.upper()}'], .source-{source.lower()}")
                                if btn_locator.count() > 0:
                                    print(f"✅ Found source button by data attributes")
                                else:
                                    btn_locator = None
                            except:
                                pass

                        if not btn_locator or btn_locator.count() == 0:
                            print(f"⚠️  Source button '{source.upper()}' not found (attempt {source_attempt})")
                            if source_attempt < max_source_attempts:
                                self.page.wait_for_timeout(2000)  # Wait before retry
                                continue
                            else:
                                break

                        # Check if it's a navigation link
                        href = btn_locator.first.get_attribute("href")

                        if href and href not in ("#", "", "javascript:void(0)"):
                            from urllib.parse import urljoin
                            next_url = urljoin(url, href)
                            print(f"↪️  Navigating to source URL: {next_url}")
                            
                            try:
                                self.page.goto(next_url, wait_until='domcontentloaded', timeout=20000)
                                source_activated = True
                                
                                # If destination is a Streamtape page, grab video source instantly
                                if any(x in self.page.url for x in ["streamtape.com", "tapecontent.net", "streamta.pe"]):
                                    try:
                                        self.page.wait_for_selector("video", timeout=8000)
                                        direct_src = self.page.evaluate("() => document.querySelector('video') && document.querySelector('video').src")
                                        if direct_src and direct_src.startswith('http') and direct_src not in found_urls:
                                            found_urls.append(direct_src)
                                            print(f"🎯 Found media URL from direct Streamtape page: {direct_src}")
                                    except Exception as st_err:
                                        print(f"⚠️  Streamtape direct extraction failed: {st_err}")
                            except Exception as nav_err:
                                print(f"⚠️  Navigation failed: {nav_err}")
                                continue
                        else:
                            # Try clicking the button
                            try:
                                # Regular click
                                btn_locator.first.click(timeout=8000)
                                source_activated = True
                                print(f"✅ Successfully clicked source button")
                                    
                            except Exception as click_err:
                                print(f"⚠️  Click failed: {click_err}")
                                # Try JavaScript click as fallback
                                try:
                                    self.page.evaluate("el => el.click()", btn_locator.first)
                                    source_activated = True
                                    print(f"✅ Successfully clicked source button via JS")
                                except Exception as js_err:
                                    print(f"⚠️  JavaScript click failed: {js_err}")
                                    continue

                        # If source was activated, wait for content to load
                        if source_activated:
                            try:
                                self.page.wait_for_load_state('networkidle', timeout=8000)
                            except Exception:
                                # Fallback to passive wait
                                self.page.wait_for_timeout(3000)
                            
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
                            break
                            
                    except Exception as source_err:
                        print(f"⚠️  Source activation attempt {source_attempt} failed: {source_err}")
                        if source_attempt < max_source_attempts:
                            self.page.wait_for_timeout(2000)  # Wait before retry
                            continue
                        else:
                            break
                
                if not source_activated:
                    print(f"❌ Failed to activate source '{source.upper()}' after {max_source_attempts} attempts")
            
            # Regular passive wait for non-TAP sources or if no URLs found
            if not found_urls:
                print(f"⌛ Passive wait {self.wait_sec}s for media requests …")
                self.page.wait_for_timeout(self.wait_sec * 1000)
            else:
                print("⚡ Skipping passive wait – URL already captured")

            # Clean up all listeners to avoid duplicates
            for event_type, listener in all_listeners:
                ctx.remove_listener(event_type, listener)
            all_listeners = []

            # Deduplicate
            found_urls = list(dict.fromkeys(found_urls))

            # Final filtering to exclude ad URLs
            if found_urls:
                filtered_urls = []
                for u in found_urls:
                    # For TAP source, only accept streamtape domains
                    if source and source.upper() == 'TAP':
                        if any(host in u.lower() for host in ['streamtape', 'tapecontent', 'streamta.pe']):
                            filtered_urls.append(u)
                    # For MON or other sources, accept m3u8 files
                    elif ".m3u8" in u.lower():
                        filtered_urls.append(u)
                    # For any source, accept mp4 from known hosts
                    elif ".mp4" in u.lower() and any(host in u.lower() for host in ['streamtape', 'tapecontent', 'streamta.pe']):
                        filtered_urls.append(u)
                
                if len(filtered_urls) < len(found_urls):
                    print(f"🎯 Filtered {len(found_urls)} URLs to {len(filtered_urls)} legitimate video sources")
                    found_urls = filtered_urls

            if found_urls:
                print(f"🎉 Found {len(found_urls)} media URL(s)")
                for i, fu in enumerate(found_urls, 1):
                    print(f"   {i}. {fu}")
            else:
                print("❌ No media URLs found")
                
                # If no URLs found with normal flow, try legacy TAP extractor as last resort
                if source and source.upper() == 'TAP':
                    print("🔄 Trying legacy TAP extractor as last resort")
                    self._tap_extract_legacy(url, found_urls)
                    
                    # Filter URLs again - STRICT for TAP
                    if found_urls:
                        filtered_urls = []
                        for u in found_urls:
                            if any(host in u.lower() for host in ['streamtape', 'tapecontent', 'streamta.pe']):
                                filtered_urls.append(u)
                        
                        if filtered_urls:
                            print(f"🎯 Filtered {len(found_urls)} URLs to {len(filtered_urls)} legitimate Streamtape sources")
                            found_urls = filtered_urls
                        else:
                            print("⚠️ All found URLs were filtered out as non-Streamtape")
                    
                    if found_urls:
                        print(f"🎉 Found {len(found_urls)} media URL(s) with legacy extractor")
                        for i, fu in enumerate(found_urls, 1):
                            print(f"   {i}. {fu}")
                
        except Exception as e:
            print(f"❌ Error extracting media URLs: {e}")
            # Clean up any remaining listeners
            if all_listeners:
                ctx = self.page.context
                for event_type, listener in all_listeners:
                    try:
                        ctx.remove_listener(event_type, listener)
                    except:
                        pass
        
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
        
        # Stop here if we found a URL - don't try to extract again
        
        # Prioritise according to extension / preference
        preferred_order = [
            lambda u: u.lower().endswith('.m3u8'),  # HLS first
            lambda u: '.m3u8' in u.lower(),
            lambda u: u.lower().endswith('.mp4'),
            lambda u: '.mp4' in u.lower(),
        ]

        media_urls.sort(key=lambda u: next((i for i, f in enumerate(preferred_order) if f(u)), 999))

        # Take the first URL and don't process the rest
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
        try:
            if self.page:
                try:
                    self.page.close()
                except Exception:
                    pass

            if self.context:
                try:
                    self.context.close()
                except Exception:
                    pass

            if self.browser:
                try:
                    self.browser.close()
                except Exception:
                    pass

            if self.playwright:
                try:
                    self.playwright.stop()
                except Exception:
                    pass

            print("🧹 Browser closed and resources cleaned up")
        except Exception as e:
            print(f"⚠️ Error during cleanup: {e}")
            # Force cleanup on ARM devices
            import platform
            if 'arm' in platform.machine().lower() or 'aarch64' in platform.machine().lower():
                try:
                    import subprocess
                    subprocess.run(['pkill', '-f', 'firefox'], stderr=subprocess.DEVNULL)
                    print("🔧 Force-killed Firefox processes on ARM device")
                except:
                    pass
    
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