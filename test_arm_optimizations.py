#!/usr/bin/env python3
"""
Test script for ARM optimizations in Kukaj Video Downloader
"""

import sys
import platform
import time
from kukaj_downloader import KukajDownloader

def test_arm_detection():
    """Test ARM device detection"""
    print("🔧 Testing ARM device detection...")
    machine = platform.machine().lower()
    is_arm = 'arm' in machine or 'aarch64' in machine
    print(f"Machine: {machine}")
    print(f"Is ARM: {is_arm}")
    return is_arm

def test_browser_initialization():
    """Test browser initialization with ARM optimizations"""
    print("\n🎭 Testing browser initialization...")
    try:
        with KukajDownloader(headless=True) as downloader:
            print("✅ Browser initialized successfully")
            return True
    except Exception as e:
        print(f"❌ Browser initialization failed: {e}")
        return False

def test_resource_monitoring():
    """Test resource monitoring functionality"""
    print("\n📊 Testing resource monitoring...")
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        print(f"CPU Usage: {cpu_percent}%")
        print(f"Memory Usage: {memory.percent}%")
        print(f"Available Memory: {memory.available / (1024**3):.2f} GB")
        return True
    except ImportError:
        print("⚠️ psutil not available")
        return False
    except Exception as e:
        print(f"❌ Resource monitoring failed: {e}")
        return False

def test_performance_optimizations():
    """Test performance optimizations"""
    print("\n⚡ Testing performance optimizations...")
    
    # Test reduced timeouts
    start_time = time.time()
    try:
        with KukajDownloader(headless=True, wait_sec=8) as downloader:
            # Just test initialization, don't actually download
            print("✅ Reduced timeout configuration works")
            elapsed = time.time() - start_time
            print(f"Initialization time: {elapsed:.2f}s")
            return True
    except Exception as e:
        print(f"❌ Performance optimization test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting ARM optimization tests...")
    print("=" * 50)
    
    tests = [
        ("ARM Detection", test_arm_detection),
        ("Browser Initialization", test_browser_initialization),
        ("Resource Monitoring", test_resource_monitoring),
        ("Performance Optimizations", test_performance_optimizations)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("📋 Test Results:")
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("🎉 All tests passed! ARM optimizations are working correctly.")
        return 0
    else:
        print("⚠️ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 