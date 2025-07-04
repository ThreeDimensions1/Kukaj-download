#!/usr/bin/env python3
"""
ChromeDriver Fix Utility
Clears WebDriver cache and reinstalls ChromeDriver to fix common issues
"""

import os
import shutil
import sys


def clear_webdriver_cache():
    """Clear the WebDriver cache directory"""
    cache_dir = os.path.expanduser("~/.wdm")
    
    if os.path.exists(cache_dir):
        try:
            print(f"🔄 Clearing WebDriver cache at: {cache_dir}")
            shutil.rmtree(cache_dir)
            print("✅ WebDriver cache cleared successfully")
            return True
        except Exception as e:
            print(f"❌ Error clearing cache: {e}")
            return False
    else:
        print("ℹ️ No WebDriver cache found")
        return True


def reinstall_chromedriver():
    """Reinstall ChromeDriver"""
    try:
        print("🔄 Reinstalling ChromeDriver...")
        from webdriver_manager.chrome import ChromeDriverManager
        
        driver_path = ChromeDriverManager().install()
        print(f"✅ ChromeDriver installed at: {driver_path}")
        
        # Verify the installation
        if os.path.isfile(driver_path) and os.access(driver_path, os.X_OK):
            print("✅ ChromeDriver installation verified")
            return True
        else:
            print("⚠️ ChromeDriver installation may have issues")
            return False
            
    except Exception as e:
        print(f"❌ Error reinstalling ChromeDriver: {e}")
        return False


def main():
    """Main function"""
    print("🔧 ChromeDriver Fix Utility")
    print("=" * 40)
    
    print("\n1. Clearing WebDriver cache...")
    cache_cleared = clear_webdriver_cache()
    
    print("\n2. Reinstalling ChromeDriver...")
    driver_installed = reinstall_chromedriver()
    
    print("\n" + "=" * 40)
    
    if cache_cleared and driver_installed:
        print("✅ ChromeDriver fix completed successfully!")
        print("🎯 You can now run the downloader again")
    else:
        print("⚠️ Some issues occurred during the fix")
        print("💡 Try running this script again or install ChromeDriver manually")
        sys.exit(1)


if __name__ == "__main__":
    main() 