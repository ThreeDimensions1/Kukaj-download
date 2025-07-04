# How M3U8 Link Extraction Works

## 🎯 Overview

The m3u8 extraction process captures video streaming URLs from Kukaj.fi by monitoring network traffic during JavaScript execution. This document explains exactly how it works.

## 🔍 The Complete Process

### Step 1: ChromeDriver Setup with Network Logging

```python
# Enable network performance logging
chrome_options.add_experimental_option('perfLoggingPrefs', {
    'enableNetwork': True,
    'enablePage': False,
    'enableTimeline': False
})

# Set logging preferences
chrome_options.add_experimental_option('loggingPrefs', {
    'performance': 'ALL',
    'browser': 'ALL'
})
```

### Step 2: Page Loading and JavaScript Execution

1. **Load the page**: `driver.get(url)`
2. **Wait for JavaScript**: 5-second delay allows video player scripts to execute
3. **Background requests**: JavaScript makes requests to video servers
4. **Network capture**: ChromeDriver logs all HTTP requests

### Step 3: Network Log Analysis

From your successful web interface logs:
```
📊 Method 1: Checking network logs...
   Found 5343 network log entries
   ✅ Found .m3u8 URL: https://be6721.rcr72.waw04.i8yz83pn.com/hls2/02/03203/1wd6zg99w0fs_o/master.m3u8?t=...
   ✅ Method 1 found 4 URLs
```

### Step 4: URL Extraction

Using regex pattern: `https?://[^\s"\']+\.m3u8[^\s"\']*`

The system finds:
- `master.m3u8` - Main playlist with quality options
- `index-v1-a1.m3u8` - Video/audio stream segments

## 🌐 Manual Browser Simulation

### Method 1: Chrome DevTools (Recommended)

1. **Open Chrome** and press `F12`
2. **Go to Network tab**
3. **Check "Preserve log"** checkbox
4. **Navigate to**: `https://film.kukaj.fi/matrix`
5. **Wait 5-10 seconds** for video to load
6. **Filter by "m3u8"** in search box
7. **Click on m3u8 requests** to see full URLs

### Method 2: Command Line Testing

```bash
# Test with your downloader
source venv/bin/activate
python3 kukaj_downloader.py https://film.kukaj.fi/matrix

# Or use the web interface
python3 start_web.py
# Then visit http://localhost:8080
```

## 📊 URL Structure Analysis

### Example URLs from Live Session:
```
https://be6721.rcr72.waw04.i8yz83pn.com/hls2/02/03203/1wd6zg99w0fs_o/master.m3u8?t=Ot6yzoFlVKwlTy4ba4QLEnzCu2-4JZHzZn2zsf9tNOY&s=1751567542&e=10800&f=42798168&srv=1055&asn=6855&sp=4000&p=
```

### URL Components:
- **Domain**: `be6721.rcr72.waw04.i8yz83pn.com` (CDN server)
- **Path**: `/hls2/02/03203/1wd6zg99w0fs_o/master.m3u8`
- **Parameters**:
  - `t` = Authentication token
  - `s` = Start timestamp
  - `e` = Expiration time (seconds)
  - `f` = File identifier
  - `srv` = Server ID
  - `asn` = Autonomous System Number
  - `sp` = Speed/quality parameter

## 🔧 Technical Details

### Why This Method Works:

1. **JavaScript-driven**: Kukaj.fi loads videos via JavaScript, not static HTML
2. **Network monitoring**: ChromeDriver captures all background requests
3. **Token-based**: URLs contain authentication tokens generated per session
4. **Time-limited**: Tokens expire, so URLs must be used quickly

### Alternative Methods (Less Reliable):

- **Method 2**: Page source parsing (❌ Usually empty)
- **Method 3**: Video element inspection (❌ No video tags)
- **Method 4**: Source element checking (❌ No source tags)
- **Method 5**: JavaScript execution (❌ Variables not accessible)

## 🎯 Success Indicators

From your logs, successful extraction shows:
```
🎯 Total unique .m3u8 URLs found: 2
📋 Final URL list:
   1. https://be6721.rcr72.waw04.i8yz83pn.com/.../master.m3u8?t=...
   2. https://be6721.rcr72.waw04.i8yz83pn.com/.../index-v1-a1.m3u8?t=...
```

## 💡 Key Insights

1. **Network logging is essential** - Only Method 1 consistently works
2. **JavaScript execution time matters** - 5-second wait is crucial
3. **Tokens expire quickly** - URLs must be used immediately
4. **Multiple URLs found** - Master playlist + stream segments
5. **CDN distribution** - Videos served from various servers

## 🚀 Usage Examples

### Download .m3u8 file:
```bash
python3 kukaj_downloader.py https://film.kukaj.fi/matrix
```

### Convert to MP4:
```bash
python3 kukaj_downloader.py https://film.kukaj.fi/matrix --mp4
```

### Web interface:
```bash
python3 start_web.py
# Visit http://localhost:8080
```

## 🔒 Security Considerations

- URLs contain authentication tokens
- Tokens are time-limited for security
- Multiple concurrent requests might be blocked
- Rate limiting may apply

## 📈 Performance Statistics

From your successful runs:
- **Network log entries**: ~5,000 per page load
- **Extraction time**: ~5-10 seconds
- **Success rate**: High with Method 1 (Network logs)
- **URL validity**: Limited by token expiration

This process successfully captures the dynamic, token-based video URLs that Kukaj.fi uses for streaming. 