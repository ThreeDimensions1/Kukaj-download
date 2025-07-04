# 🎨 Kukaj Video Downloader - Web Interface

A beautiful, modern web interface for downloading videos from kukaj domains.

## ✨ Features

- **Beautiful Modern Design**: Clean, responsive interface with gradient backgrounds
- **Real-time Progress**: Live updates during download process
- **Multi-format Support**: Download .m3u8 files or convert to MP4
- **File Management**: View and download previously downloaded files
- **URL Normalization**: Automatically handles kukaj.fi, kukaj.io, kukaj.in, etc.
- **WebSocket Integration**: Real-time communication for instant feedback

## 🚀 Quick Start

### Option 1: Using the Startup Script (Recommended)
```bash
source venv/bin/activate
python3 start_web.py
```

### Option 2: Direct Flask App
```bash
source venv/bin/activate
python3 app.py
```

### Option 3: Command Line (Original)
```bash
source venv/bin/activate
python3 kukaj_downloader.py <url> [options]
```

## 🌐 Accessing the Interface

1. Start the web server using one of the methods above
2. Open your browser to: **http://localhost:8080**
3. You'll see the beautiful Kukaj Video Downloader interface!

## 🎯 How to Use

### 1. Download a Video
1. **Enter URL**: Paste any kukaj domain URL (kukaj.fi, kukaj.io, kukaj.in, etc.)
   - Example: `https://serial.kukaj.fi/hra-na-olihen/S03E04`
2. **Choose Format** (optional):
   - ☐ Unchecked = Download .m3u8 file (fast, small)
   - ☑ Checked = Convert to MP4 (slower, more compatible)
3. **Custom Filename** (optional): Specify your own filename
4. **Click Download**: Watch the real-time progress in the console below!

### 2. View Downloaded Files
- The right panel shows all your downloaded files
- Click the download button next to any file to save it to your computer
- Files are automatically organized by date

### 3. Real-time Progress
- Watch live updates as the video is processed
- See URL normalization in action
- Track download progress with timestamps
- Color-coded status messages (success, warning, error, info)

## 🎨 Interface Highlights

### Design Elements
- **Gradient Background**: Beautiful purple gradient backdrop
- **Glass-morphism Cards**: Modern frosted glass effect
- **Interactive Elements**: Smooth hover animations and transitions
- **Responsive Design**: Works perfectly on desktop, tablet, and mobile
- **Icon Integration**: Font Awesome icons throughout
- **Typography**: Clean Inter font for excellent readability

### Color Scheme
- **Primary**: Indigo (#6366f1) for buttons and accents
- **Success**: Green (#10b981) for completed downloads
- **Warning**: Amber (#f59e0b) for non-critical issues
- **Error**: Red (#ef4444) for failures
- **Info**: Cyan (#06b6d4) for informational messages

### User Experience Features
- **Smart Form Validation**: Real-time URL validation
- **Loading States**: Beautiful spinner animations during downloads
- **File Icons**: Different icons for .m3u8 vs .mp4 files
- **File Size Formatting**: Human-readable file sizes
- **Timestamp Display**: Clear time information for all activities

## 🔧 Technical Details

### Architecture
- **Frontend**: Modern HTML5, CSS3, Vanilla JavaScript
- **Backend**: Flask web framework with WebSocket support
- **Real-time Communication**: Socket.IO for live updates
- **File Management**: RESTful API for file operations
- **Download Engine**: Integrated kukaj_downloader.py

### API Endpoints
- `GET /`: Main interface
- `POST /api/download`: Start download process
- `GET /api/files`: List downloaded files
- `GET /api/download-file/<filename>`: Download specific file
- `GET /api/history`: View download history

### WebSocket Events
- `download_progress`: Real-time progress updates
- `download_complete`: Download completion notification
- `download_error`: Error handling

## 🛠 Customization

### Changing Colors
Edit the CSS variables in `templates/index.html`:
```css
:root {
    --primary-color: #6366f1;  /* Change primary color */
    --success-color: #10b981;  /* Change success color */
    /* ... other colors ... */
}
```

### Adding Features
The modular JavaScript class `KukajDownloader` makes it easy to extend:
- Add new download options
- Implement file filtering
- Create download queues
- Add user preferences

## 📱 Mobile Experience

The interface is fully responsive and provides an excellent mobile experience:
- Touch-friendly buttons and inputs
- Optimized layouts for small screens
- Swipe-friendly file lists
- Mobile-optimized typography

## 🔒 Security Notes

- The web interface runs locally (localhost:8080)
- No external data transmission except to kukaj domains
- Files are stored locally on your machine
- All downloads respect the original command-line tool's behavior

## 🎉 Why Use the Web Interface?

### Advantages over Command Line:
1. **Visual Feedback**: See progress in real-time with beautiful UI
2. **Ease of Use**: No need to remember command-line arguments
3. **File Management**: Built-in file browser and download management
4. **Multi-tasking**: Keep the interface open while using other apps
5. **User-Friendly**: Perfect for users who prefer graphical interfaces
6. **Modern Experience**: Feels like a professional web application

### Perfect For:
- Users who prefer visual interfaces
- Batch downloading multiple videos
- Monitoring download progress
- Managing downloaded files
- Sharing with less technical users

## 🚀 Get Started Now!

1. Run: `python3 start_web.py`
2. Open: http://localhost:8080
3. Enjoy the beautiful interface! 🎨✨

---

*Built with ❤️ for the kukaj video downloading community* 