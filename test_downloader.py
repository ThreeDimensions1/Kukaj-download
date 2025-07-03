#!/usr/bin/env python3
"""
Test script for Kukaj.fi Video Downloader
"""

from kukaj_downloader import KukajDownloader, normalize_kukaj_url

def test_url_normalization():
    """Test URL normalization for different kukaj subdomains"""
    print("Testing URL normalization...")
    
    test_cases = [
        ("https://serial.kukaj.fi/hra-na-olihen/S03E04", False),
        ("https://serial.kukaj.io/hra-na-olihen/S03E04", True),
        ("https://serial.kukaj.in/hra-na-olihen/S03E04", True),
        ("https://kukaj.tv/hra-na-olihen/S03E04", True),
        ("https://www.kukaj.fi/hra-na-olihen/S03E04", False),
        ("https://example.com/video", False),
    ]
    
    for original_url, should_change in test_cases:
        normalized_url, was_changed = normalize_kukaj_url(original_url)
        print(f"Original: {original_url}")
        print(f"Normalized: {normalized_url}")
        print(f"Changed: {was_changed} (Expected: {should_change})")
        
        if was_changed == should_change:
            print("✅ PASS")
        else:
            print("❌ FAIL")
        print()
    
    return True

def test_url_extraction():
    """Test URL extraction without downloading"""
    test_url = "https://serial.kukaj.fi/hra-na-olihen/S03E04"
    
    print("Testing URL extraction...")
    print(f"URL: {test_url}")
    
    try:
        with KukajDownloader(headless=False) as downloader:  # Use headless=False for debugging
            m3u8_urls = downloader.extract_m3u8_url(test_url)
            
            if m3u8_urls:
                print(f"\nFound {len(m3u8_urls)} .m3u8 URL(s):")
                for i, url in enumerate(m3u8_urls, 1):
                    print(f"  {i}. {url}")
                return True
            else:
                print("No .m3u8 URLs found")
                return False
                
    except Exception as e:
        print(f"Error during test: {e}")
        return False

def test_download():
    """Test downloading a video"""
    test_url = "https://serial.kukaj.fi/hra-na-olihen/S03E04"
    
    print("\nTesting video download...")
    print(f"URL: {test_url}")
    
    try:
        with KukajDownloader(headless=True) as downloader:
            # Test .m3u8 download
            print("Testing .m3u8 download...")
            success_m3u8 = downloader.download_video(test_url, "test_download.m3u8", convert_to_mp4=False)
            
            if success_m3u8:
                print("✅ .m3u8 download successful: test_download.m3u8")
                
                # Ask if user wants to test MP4 conversion
                response = input("Do you want to test MP4 conversion? (y/n): ").lower()
                if response == 'y':
                    print("Testing MP4 conversion...")
                    success_mp4 = downloader.download_video(test_url, "test_download.mp4", convert_to_mp4=True)
                    if success_mp4:
                        print("✅ MP4 conversion successful: test_download.mp4")
                        return True
                    else:
                        print("❌ MP4 conversion failed")
                        return False
                else:
                    return True
            else:
                print("❌ .m3u8 download failed")
                return False
                
    except Exception as e:
        print(f"Error during download: {e}")
        return False

if __name__ == "__main__":
    print("Kukaj Video Downloader Test")
    print("=" * 40)
    
    # Test URL normalization first
    print("1. Testing URL normalization...")
    test_url_normalization()
    
    print("\n" + "=" * 40)
    
    # Test URL extraction
    print("2. Testing URL extraction...")
    if test_url_extraction():
        print("\n" + "=" * 40)
        
        # Ask if user wants to proceed with download
        response = input("\nDo you want to proceed with actual download? (y/n): ").lower()
        if response == 'y':
            test_download()
        else:
            print("Skipping download test.")
    else:
        print("URL extraction failed. Check your setup.") 