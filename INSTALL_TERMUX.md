# 📲 Kukaj Video Downloader on Termux / Android

This guide shows how to get the **Kukaj Video Downloader** (Flask + Playwright) running entirely on an Android device with [Termux](https://termux.dev/).

---

## 1. Prerequisites

1. **Install Termux** from F-Droid (recommended) or the Play Store clone "Termux-App".  *Do **not** use the abandoned Play Store version – it's outdated.*
2. Launch Termux once and allow storage access:
   ```bash
   termux-setup-storage   # grants $HOME/storage/shared → /sdcard
   ```
3. Update the base system and handy build tools:
   ```bash
   pkg update && pkg upgrade -y
   pkg install -y git python ffmpeg nodejs-lts clang make libjpeg-turbo
   ```
   * `ffmpeg` is used for fast downloads / MP4 remux.

---

## 2. Clone the project

Choose a directory (e.g. `$HOME/projects`):
```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/<your-fork>/kukaj-video-downloader.git
cd kukaj-video-downloader
```

---

## 3. Python environment

Termux ships with a recent CPython.  You can work directly in the system interpreter or create a virtual-env:
```bash
python -m venv .venv
source .venv/bin/activate
```

Install Python dependencies:
```bash
pip install --upgrade pip wheel
pip install -r requirements.txt
```

---

## 4. Playwright + browsers

Playwright needs the **Firefox** runtime (≈ 120 MB).  Termux can download the Linux build automatically:
```bash
pip install playwright==1.*
playwright install firefox --with-deps
```
*Tip:* If storage is tight you can delete Chromium / WebKit packages inside `~/.cache/ms-playwright/` – only the `firefox` folder is required.

---

## 5. First run

```bash
# for CLI usage
python kukaj_downloader.py "https://film.kukaj.fi/matrix" --headless

# or launch the Flask web-UI (port 5000)
python start_web.py --headless
```

Open `http://127.0.0.1:5000` in any Android browser (Kiwi, Firefox, Chrome, …).  If you want to reach the server from another device, replace *127.0.0.1* with your phone's Wi-Fi IP.

> **Tip:** On Android 12+ the system may kill long-running background processes.  Keep the Termux session in foreground or use [Termux:Widget](https://github.com/termux/termux-widget) to create a quick-toggle script.

---

## 6. Updating

```bash
cd ~/projects/kukaj-video-downloader
git pull
pip install -r requirements.txt   # pick up new deps
playwright install firefox        # update browser build when needed
```

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `playwright install` fails with "glibc not found" | Termux uses musl-like bionic libs; Playwright bundles its own – keep `--with-deps` flag. |
| Firefox can't resolve domains / redirects to *0.0.7.128* | Proxy & DoH are disabled in `firefox_user_prefs` within `kukaj_downloader.py`.  Make sure you are on the latest code. |
| `EACCES` saving to `/sdcard` | The downloads folder lives in the project root.  To copy elsewhere: `cp downloads/*.mp4 ~/storage/shared/` |
| High battery drain | Run with `--headless` and exit Termux when finished. |

---

Enjoy downloading Kukaj streams straight from your pocket!  🎬📱 