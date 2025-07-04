# Home Assistant Integration Guide

## 🚀 **Multiple Integration Options (No Code Changes Required)**

### **Option 1: Full Add-on (Recommended)**
Turn your Kukaj downloader into a native Home Assistant add-on with web interface.

#### **Setup Steps:**
1. **Create add-on repository structure:**
   ```
   addon/
   ├── config.yaml
   ├── Dockerfile
   ├── run.sh
   ├── README.md
   ├── services.yaml
   ├── build.yaml
   └── (copy all your existing files here)
   ```

2. **Upload to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial Home Assistant add-on"
   git remote add origin https://github.com/yourusername/kukaj-downloader-addon.git
   git push -u origin main
   ```

3. **Add to Home Assistant:**
   - Go to **Settings** → **Add-ons** → **Add-on Store**
   - Click **⋮** → **Repositories**
   - Add: `https://github.com/yourusername/kukaj-downloader-addon`
   - Install "Kukaj Video Downloader"

#### **Benefits:**
- ✅ Native HA integration
- ✅ Web interface in HA sidebar
- ✅ Service calls for automations
- ✅ Persistent storage
- ✅ Auto-start on boot

---

### **Option 2: REST API Integration (Easiest)**
Use your existing Flask app as an external service.

#### **Setup (No Code Changes):**
1. **Start your existing app:**
   ```bash
   python3 start_web.py
   ```

2. **Add to Home Assistant configuration.yaml:**
   ```yaml
   rest_command:
     download_kukaj_video:
       url: "http://localhost:8080/api/download"
       method: POST
       headers:
         Content-Type: "application/json"
       payload: >
         {
           "url": "{{ url }}",
           "format": "{{ format | default('m3u8') }}",
           "filename": "{{ filename | default('') }}"
         }
   
   sensor:
     - platform: rest
       name: "Kukaj Downloads"
       resource: "http://localhost:8080/api/downloads"
       scan_interval: 30
       value_template: "{{ value_json | length }}"
       json_attributes:
         - "downloads"
   ```

3. **Create automation example:**
   ```yaml
   automation:
     - alias: "Download Video from Notification"
       trigger:
         platform: webhook
         webhook_id: kukaj_download
       action:
         service: rest_command.download_kukaj_video
         data:
           url: "{{ trigger.data.url }}"
           format: "mp4"
   ```

#### **Benefits:**
- ✅ Zero code changes
- ✅ Works with existing setup
- ✅ Full API access
- ✅ Quick setup

---

### **Option 3: Docker Container**
Run as a Docker container accessible from Home Assistant.

#### **Setup:**
1. **Create Dockerfile** (already provided in `addon/Dockerfile`)

2. **Build and run:**
   ```bash
   docker build -t kukaj-downloader .
   docker run -d -p 8080:8080 -v $(pwd)/downloads:/app/downloads kukaj-downloader
   ```

3. **Add to Home Assistant** (same as Option 2)

#### **Benefits:**
- ✅ Containerized deployment
- ✅ Persistent storage
- ✅ Easy scaling
- ✅ No HA dependencies

---

### **Option 4: Shell Command Integration**
Use Home Assistant's shell_command for direct CLI access.

#### **Setup (No Code Changes):**
Add to `configuration.yaml`:
```yaml
shell_command:
  download_kukaj_m3u8: "cd /path/to/kukaj && python3 kukaj_downloader.py '{{ url }}' -o '{{ filename }}'"
  download_kukaj_mp4: "cd /path/to/kukaj && python3 kukaj_downloader.py '{{ url }}' --mp4 -o '{{ filename }}'"

script:
  download_video:
    alias: "Download Kukaj Video"
    fields:
      url:
        description: "Video URL"
        example: "https://serial.kukaj.fi/hra-na-olihen/S03E04"
      format:
        description: "Format (m3u8 or mp4)"
        example: "mp4"
      filename:
        description: "Custom filename"
        example: "my-video"
    sequence:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ format == 'mp4' }}"
            sequence:
              - service: shell_command.download_kukaj_mp4
                data:
                  url: "{{ url }}"
                  filename: "{{ filename }}"
        default:
          - service: shell_command.download_kukaj_m3u8
            data:
              url: "{{ url }}"
              filename: "{{ filename }}"
```

#### **Benefits:**
- ✅ Direct CLI integration
- ✅ No additional services
- ✅ Lightweight approach
- ✅ Script-based automation

---

## 🎯 **Usage Examples**

### **Web Interface:**
- Access via HA sidebar (Add-on) or `http://homeassistant.local:8080`
- Same beautiful interface you already have

### **Service Calls:**
```yaml
# Download video
service: rest_command.download_kukaj_video
data:
  url: "https://serial.kukaj.fi/hra-na-olihen/S03E04"
  format: "mp4"
  filename: "game-of-thrones-s03e04"

# Get downloads list
service: sensor.kukaj_downloads
```

### **Automations:**
```yaml
# Auto-download from notification
- alias: "Auto Download from Telegram"
  trigger:
    platform: event
    event_type: telegram_text
  condition:
    condition: template
    value_template: "{{ 'kukaj.fi' in trigger.event.data.text }}"
  action:
    service: rest_command.download_kukaj_video
    data:
      url: "{{ trigger.event.data.text }}"
      format: "mp4"

# Notify when download complete
- alias: "Download Complete Notification"
  trigger:
    platform: state
    entity_id: sensor.kukaj_downloads
  action:
    service: notify.mobile_app_your_phone
    data:
      message: "Video download completed! {{ states('sensor.kukaj_downloads') }} files ready."
```

### **Dashboard Cards:**
```yaml
# Download interface card
- type: webpage
  url: "http://localhost:8080"
  title: "Kukaj Downloader"

# Downloads sensor card
- type: entities
  entities:
    - sensor.kukaj_downloads
  title: "Video Downloads"

# Quick download button
- type: button
  tap_action:
    action: call-service
    service: rest_command.download_kukaj_video
    data:
      url: !input video_url
      format: "mp4"
  name: "Download Video"
```

---

## 🔧 **Advanced Features**

### **Webhook Integration:**
```yaml
# configuration.yaml
automation:
  - alias: "Download via Webhook"
    trigger:
      platform: webhook
      webhook_id: kukaj_download
      allowed_methods:
        - POST
    action:
      service: rest_command.download_kukaj_video
      data:
        url: "{{ trigger.data.url }}"
        format: "{{ trigger.data.format | default('m3u8') }}"
```

**Usage:**
```bash
curl -X POST \
  http://homeassistant.local:8123/api/webhook/kukaj_download \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://serial.kukaj.fi/hra-na-olihen/S03E04", "format": "mp4"}'
```

### **File Management:**
```yaml
# Delete old downloads
- alias: "Cleanup Downloads"
  trigger:
    platform: time
    at: "02:00:00"
  action:
    service: shell_command.cleanup_downloads
    data: {}

shell_command:
  cleanup_downloads: "find /path/to/downloads -type f -mtime +7 -delete"
```

---

## 📱 **Mobile Integration**

### **iOS Shortcuts:**
Create a shortcut that:
1. Takes kukaj.fi URL from clipboard
2. Calls your webhook
3. Shows success notification

### **Android Tasker:**
1. **Share Intent:** Detect kukaj.fi URLs
2. **HTTP Request:** POST to your webhook
3. **Notification:** Show download status

---

## 🛠️ **Troubleshooting**

### **Common Issues:**
1. **Port conflicts:** Change port in configuration
2. **Network access:** Ensure HA can reach your service
3. **File permissions:** Check downloads directory permissions
4. **Chrome issues:** Use headless mode in Docker

### **Debug Mode:**
```yaml
# Add to configuration.yaml
logger:
  default: info
  logs:
    homeassistant.components.rest_command: debug
    homeassistant.components.shell_command: debug
```

---

## 🎉 **Result**

You now have a **fully integrated Home Assistant video downloader** with:

- 🎬 **Web Interface** in HA sidebar
- 📱 **Mobile controls** via HA app
- 🔄 **Automations** for hands-free downloading
- 📊 **Status monitoring** with sensors
- 🎯 **Webhook support** for external apps
- 💾 **File management** through HA

**No changes to your existing code required!** 🚀 