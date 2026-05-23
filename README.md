# Pro YouTube Downloader

Cross-platform YouTube downloader with hardware-accelerated video conversion.

## 📁 Folders

- **`mac-downloader/`** - For macOS (Apple Silicon & Intel)
- **`windows-downloader/`** - For Windows (x86_64 & ARM64)

---

## 🍀 macOS Instructions

### Quick Start
1. Navigate to the `mac-downloader` folder
2. Double-click `run_app.command`
3. The app will open in your browser at http://localhost:8501

### What It Does Automatically
- Detects Apple Silicon vs Intel Mac
- Installs Homebrew if missing
- Installs Python 3 and FFmpeg if missing
- Creates virtual environment
- Opens browser automatically

### Hardware Encoding
- **Apple Silicon (M1/M2/M3)**: Uses `hevc_videotoolbox` (GPU)
- **Intel Mac**: Uses `hevc_videotoolbox` if available, otherwise `libx265` (CPU)

---

## 🪟 Windows Instructions

### Prerequisites
Ensure you have:
- **Python 3.8+** installed from [python.org](https://python.org)
- **FFmpeg** installed via one of these methods:

```powershell
# Method 1: Scoop (recommended)
scoop install ffmpeg

# Method 2: Chocolatey
choco install ffmpeg

# Method 3: winget
winget install Gyan.FFmpeg
```

### Quick Start
1. Navigate to the `windows-downloader` folder
2. Double-click `run_app.bat`
3. The app will open in your browser at http://localhost:8501

### What It Does Automatically
- Detects system architecture (x86_64 or ARM64)
- Checks for Python and FFmpeg
- Creates virtual environment
- Installs required packages
- Opens browser automatically

### Hardware Encoding
- **NVIDIA GPU**: Uses `hevc_nvenc` (GPU)
- **AMD GPU**: Uses `hevc_amf` (GPU)
- **Intel GPU**: Uses `hevc_qsv` (GPU)
- **No GPU**: Falls back to `libx265` (CPU)

---

## ✨ Features

### Video Downloads
- Select quality from 144p to 8K
- Direct download for ≤1080p (native H.264)
- Download + convert for >1080p (AV1/VP9 → H.265/HEVC)
- Conversion modes: Speed, Balanced, High Quality

### Audio Downloads
- MP3 (192 kbps)
- M4A (AAC)
- WAV (Lossless)
- FLAC (Lossless)

### Smart Features
- Auto-cleanup of files older than 2 hours
- Safe filename handling (removes OS-unsafe characters)
- Progress tracking with speed and ETA
- Browser-based download button for final file

---

## 🛠️ Manual Installation (Alternative)

If you prefer manual setup:

```bash
# Create virtual environment
python -m venv .venv

# Activate it
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install -U yt-dlp streamlit

# Run the app
streamlit run app.py
```

---

## ⚠️ Notes

- Files are stored in `temp_downloads/` folder
- Files auto-delete after 2 hours
- Requires internet connection for YouTube downloads
- First run may take longer due to dependency installation

---

## 📄 License

For personal use only. Respect content creators' rights and YouTube's Terms of Service.
