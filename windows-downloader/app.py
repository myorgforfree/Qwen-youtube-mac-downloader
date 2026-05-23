import streamlit as st
import yt_dlp
import subprocess
import sys
import os
import re
import time
from pathlib import Path
from datetime import datetime
import asyncio

# ═══════════════════════════════════════════════
# FIX FOR WINDOWS ASYNCIO ERROR (WinError 10054)
# ═══════════════════════════════════════════════
if sys.platform == "win32":
    # Force SelectorEventLoop to avoid ProactorEventLoop pipe errors
    # This prevents the "connection forcibly closed" error after downloads
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ═══════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════

DOWNLOAD_DIR = Path("temp_downloads")
FILE_MAX_AGE = 7200  # 2 hours in seconds

# ═══════════════════════════════════════════════
# SYSTEM DETECTION (Windows)
# ═══════════════════════════════════════════════

def detect_windows_arch():
    """Detect Windows architecture (x86_64 or ARM64)."""
    try:
        result = subprocess.run(
            ["wmic", "os", "get", "OSArchitecture"],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout.lower()
        if "arm" in output:
            return "arm64"
        elif "x64" in output or "64-bit" in output:
            return "x86_64"
        else:
            return "x86_64"  # Default fallback
    except Exception:
        return "x86_64"


def check_videotoolbox_or_nvenc():
    """
    Check for hardware encoders on Windows:
    - NVIDIA: hevc_nvenc
    - AMD: hevc_amf
    - Intel QSV: hevc_qsv
    Returns tuple: (encoder_name, encoder_type)
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout
        
        # Priority: NVIDIA > AMD > Intel QSV
        if "hevc_nvenc" in output:
            return ("hevc_nvenc", "GPU (NVIDIA NVENC)")
        elif "hevc_amf" in output:
            return ("hevc_amf", "GPU (AMD AMF)")
        elif "hevc_qsv" in output:
            return ("hevc_qsv", "GPU (Intel QSV)")
        else:
            return (None, None)
    except Exception:
        return (None, None)


def check_ffmpeg():
    """Check if ffmpeg is available in PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# ═══════════════════════════════════════════════
# FILE MANAGEMENT
# ═══════════════════════════════════════════════

def cleanup_old_files():
    """Delete files older than FILE_MAX_AGE seconds."""
    if not DOWNLOAD_DIR.exists():
        return
    
    now = time.time()
    for file_path in DOWNLOAD_DIR.iterdir():
        if file_path.is_file():
            age = now - file_path.stat().st_mtime
            if age > FILE_MAX_AGE:
                try:
                    file_path.unlink()
                except Exception:
                    pass


def safe_filename(name):
    """Create a Windows-safe filename."""
    # Remove Windows-unsafe chars: < > : " / \ | ? * and control chars
    unsafe_chars = r'[<>:"/\\|?*\x00-\x1f]'
    name = re.sub(unsafe_chars, '', name)
    # Replace with underscore
    name = name.replace(':', '_').replace('/', '_').replace('\\', '_')
    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name)
    # Strip leading/trailing dots and spaces
    name = name.strip('. ').strip()
    # Max length (Windows MAX_PATH is 260, but we leave room for path)
    name = name[:120]
    return name if name else "video"


# ═══════════════════════════════════════════════
# VIDEO INFO FETCHING
# ═══════════════════════════════════════════════

def get_video_info(url):
    """Fetch video information from YouTube."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        st.error(f"❌ Failed to fetch video info: {str(e)}")
        return None


def get_video_options(info):
    """Build quality options dropdown."""
    formats = info.get('formats', [])
    
    # Filter and sort by height descending
    video_formats = []
    seen_heights = set()
    
    for fmt in formats:
        height = fmt.get('height')
        vcodec = fmt.get('vcodec', '')
        filesize = fmt.get('filesize')
        
        if not height or height < 144:
            continue
        
        # Skip duplicates
        if height in seen_heights:
            continue
        
        # Calculate size string
        if filesize:
            size_mb = filesize / (1024 * 1024)
            size_str = f"{size_mb:.1f} MB"
        else:
            size_str = "N/A"
        
        # Determine codec type
        is_avc = vcodec.startswith('avc1') or vcodec.startswith('avc')
        is_high_res = height > 1080
        
        if is_high_res:
            label = f"🌟 {height}p (AV1/VP9) • {size_str}"
            selector = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        else:
            if is_avc:
                label = f"⚡ {height}p – Native H.264 • {size_str}"
                selector = f"bestvideo[height<={height}][vcodec^=avc]+bestaudio/best[height<={height}]"
            else:
                label = f"🌟 {height}p (AV1/VP9) • {size_str}"
                selector = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        
        video_formats.append({
            'label': label,
            'selector': selector,
            'height': height,
            'is_high_res': is_high_res,
            'size_str': size_str
        })
        seen_heights.add(height)
    
    # Sort by height descending
    video_formats.sort(key=lambda x: x['height'], reverse=True)
    
    if not video_formats:
        # Fallback option
        video_formats.append({
            'label': 'Best Available',
            'selector': 'bestvideo+bestaudio/best',
            'height': 1080,
            'is_high_res': False,
            'size_str': 'N/A'
        })
    
    return video_formats


# ═══════════════════════════════════════════════
# PROGRESS HANDLER
# ═══════════════════════════════════════════════

class ProgressHandler:
    def __init__(self):
        self.progress_bar = st.progress(0)
        self.status_text = st.empty()
        self.last_update = 0
        self.throttle_interval = 0.4
    
    def update(self, progress, message):
        now = time.time()
        if now - self.last_update >= self.throttle_interval:
            self.progress_bar.progress(progress)
            self.status_text.text(message)
            self.last_update = now
    
    def finish_download(self):
        self.progress_bar.progress(1.0)
        self.status_text.text("✅ Download complete. Processing…")


# ═══════════════════════════════════════════════
# FFMPEG COMMAND BUILDER (Windows Hardware Encoders)
# ═══════════════════════════════════════════════

def get_ffmpeg_command(input_path, output_path, mode, encoder):
    """Build FFmpeg command based on available hardware encoder."""
    
    common_args = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-map", "0:v:0", "-map", "0:a:0?", "-sn",
        "-pix_fmt", "yuv420p",
        "-c:v", encoder,
        "-tag:v", "hvc1",
        "-c:a", "aac", "-b:a", "128k"
    ]
    
    # Mode-specific settings
    if encoder == "hevc_nvenc":
        # NVIDIA NVENC settings
        if mode == "speed":
            common_args.extend(["-preset", "p1", "-tune", "hq"])
        elif mode == "balanced":
            common_args.extend(["-preset", "p4", "-tune", "hq"])
        elif mode == "quality":
            common_args.extend(["-preset", "p7", "-tune", "hq"])
    
    elif encoder == "hevc_amf":
        # AMD AMF settings
        if mode == "speed":
            common_args.extend(["-usage", "ultrafast", "-quality", "speed"])
        elif mode == "balanced":
            common_args.extend(["-usage", "speed", "-quality", "balanced"])
        elif mode == "quality":
            common_args.extend(["-usage", "quality", "-quality", "quality"])
    
    elif encoder == "hevc_qsv":
        # Intel QSV settings
        if mode == "speed":
            common_args.extend(["-preset", "veryfast"])
        elif mode == "balanced":
            common_args.extend(["-preset", "medium"])
        elif mode == "quality":
            common_args.extend(["-preset", "slow"])
    
    else:
        # Software fallback (libx265)
        common_args[7] = "libx265"  # Replace encoder
        if mode == "speed":
            common_args.extend(["-preset", "ultrafast", "-crf", "28"])
        elif mode == "balanced":
            common_args.extend(["-preset", "medium", "-crf", "24"])
        elif mode == "quality":
            common_args.extend(["-preset", "slow", "-crf", "20"])
    
    common_args.append(str(output_path))
    
    return common_args


# ═══════════════════════════════════════════════
# DOWNLOAD FUNCTIONS
# ═══════════════════════════════════════════════

def download_video(url, quality_option, convert, conversion_mode, progress_handler):
    """Download video with optional conversion."""
    
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    safe_title = safe_filename(quality_option.get('title', 'video'))
    is_high_res = quality_option.get('is_high_res', False)
    
    # Get hardware encoder info
    encoder_name, encoder_type = check_videotoolbox_or_nvenc()
    
    if is_high_res and convert and encoder_name:
        # PATH B: Download + Convert
        raw_filename = f"raw_{safe_title}.mkv"
        raw_path = DOWNLOAD_DIR / raw_filename
        final_filename = f"{safe_title}_finalcut.mp4"
        final_path = DOWNLOAD_DIR / final_filename
        
        # Step 1: Download raw file
        ydl_opts = {
            'format': quality_option['selector'],
            'outtmpl': str(raw_path),
            'merge_output_format': 'mkv',
            'concurrent_fragment_downloads': 8,
            'retries': 3,
            'progress_hooks': [lambda d: download_progress_hook(d, progress_handler)]
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            st.error(f"❌ Download failed: {str(e)}")
            return None
        
        # Step 2: Locate raw file (extension may vary)
        raw_file = None
        for f in DOWNLOAD_DIR.iterdir():
            if f.name.startswith(f"raw_{safe_title}") and f.is_file():
                raw_file = f
                break
        
        if not raw_file:
            st.error("❌ Raw file not found after download.")
            return None
        
        # Step 3: Encode with FFmpeg
        progress_handler.update(0.5, f"🔄 Converting with {encoder_type}...")
        
        cmd = get_ffmpeg_command(raw_file, final_path, conversion_mode, encoder_name)
        
        try:
            process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            duration = None
            current_time = 0
            
            # Parse duration from input
            dur_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2})', process.stderr.read())
            if dur_match:
                h, m, s = map(int, dur_match.groups())
                duration = h * 3600 + m * 60 + s
            
            # Re-run to capture progress
            process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            for line in process.stderr:
                time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2})', line)
                if time_match and duration:
                    h, m, s = map(int, time_match.groups())
                    current_time = h * 3600 + m * 60 + s
                    progress = min(0.5 + (current_time / duration) * 0.5, 1.0)
                    progress_handler.update(progress, f"🔄 Encoding: {current_time}s / {duration}s")
            
            process.wait()
            
            if process.returncode != 0:
                st.error(f"❌ FFmpeg conversion failed. Exit code: {process.returncode}")
                return None
            
            # Delete raw file
            try:
                raw_file.unlink()
            except Exception:
                pass
            
            progress_handler.finish_download()
            return final_path
            
        except Exception as e:
            st.error(f"❌ Conversion failed: {str(e)}")
            return None
    
    else:
        # PATH A: Direct Download
        output_filename = f"{safe_title}.mp4"
        output_path = DOWNLOAD_DIR / output_filename
        
        ydl_opts = {
            'format': quality_option['selector'],
            'outtmpl': str(output_path),
            'merge_output_format': 'mp4',
            'concurrent_fragment_downloads': 8,
            'retries': 3,
            'progress_hooks': [lambda d: download_progress_hook(d, progress_handler)]
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            st.error(f"❌ Download failed: {str(e)}")
            return None
        
        # Scan for actual file (yt-dlp may change extension)
        actual_file = None
        for f in DOWNLOAD_DIR.iterdir():
            if f.name.startswith(safe_title) and f.suffix in ['.mp4', '.mkv', '.webm'] and f.is_file():
                actual_file = f
                break
        
        if not actual_file:
            st.error("❌ File not found after download.")
            return None
        
        progress_handler.finish_download()
        return actual_file


def download_audio(url, audio_format, progress_handler):
    """Download audio only."""
    
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    # Fetch title for filename
    info = get_video_info(url)
    if not info:
        return None
    
    safe_title = safe_filename(info.get('title', 'audio'))
    output_filename = f"{safe_title}.{audio_format.lower()}"
    output_path = DOWNLOAD_DIR / output_filename
    
    # Audio format settings
    audio_settings = {
        'mp3': {'codec': 'mp3', 'bitrate': '192k'},
        'm4a': {'codec': 'aac', 'quality': '5'},
        'wav': {'codec': 'pcm_s16le', 'bitrate': None},
        'flac': {'codec': 'flac', 'bitrate': None}
    }
    
    settings = audio_settings.get(audio_format.lower(), audio_settings['mp3'])
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_path),
        'concurrent_fragment_downloads': 8,
        'retries': 3,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': settings['codec'],
            'preferredquality': settings.get('bitrate') or settings.get('quality', '192')
        }],
        'progress_hooks': [lambda d: download_progress_hook(d, progress_handler)]
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Find actual file (extension may have changed)
        actual_file = None
        for f in DOWNLOAD_DIR.iterdir():
            if f.name.startswith(safe_title) and f.suffix == f".{audio_format.lower()}":
                actual_file = f
                break
        
        if not actual_file:
            # Try any audio file with matching base name
            for f in DOWNLOAD_DIR.iterdir():
                if f.name.startswith(safe_title) and f.suffix in ['.mp3', '.m4a', '.wav', '.flac']:
                    actual_file = f
                    break
        
        if not actual_file:
            st.error("❌ Audio file not found after download.")
            return None
        
        progress_handler.finish_download()
        return actual_file
        
    except Exception as e:
        st.error(f"❌ Audio download failed: {str(e)}")
        return None


def download_progress_hook(d, progress_handler):
    """Handle yt-dlp progress updates."""
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        downloaded = d.get('downloaded_bytes', 0)
        speed = d.get('speed', 0)
        eta = d.get('eta', 0)
        
        if total > 0:
            progress = downloaded / total
            total_mb = total / (1024 * 1024)
            downloaded_mb = downloaded / (1024 * 1024)
            speed_mb = (speed / (1024 * 1024)) if speed else 0
            
            message = f"{downloaded_mb:.1f}MB / {total_mb:.1f}MB | {speed_mb:.2f} MB/s | ETA: {eta}s"
            progress_handler.update(progress * 0.9, f"📥 Downloading: {message}")
        else:
            progress_handler.update(0.5, "📥 Downloading... (calculating size)")
    
    elif d['status'] == 'finished':
        progress_handler.update(0.95, "✅ Download complete. Processing…")


# ═══════════════════════════════════════════════
# STREAMLIT APP
# ═══════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Pro YT Downloader",
        page_icon="🚀",
        layout="centered"
    )
    
    # Cleanup old files on startup
    cleanup_old_files()
    
    # System detection
    arch = detect_windows_arch()
    encoder_name, encoder_type = check_videotoolbox_or_nvenc()
    has_ffmpeg = check_ffmpeg()
    
    # Header
    st.title("🚀 Pro YouTube Downloader")
    
    # System info caption
    arch_icon = "💻" if arch == "x86_64" else "🦾"
    encoder_display = encoder_type if encoder_type else "No hardware encoder detected"
    
    st.caption(
        f"{arch_icon} Windows ({arch}) | "
        f"Encoder: {encoder_display} | "
        f"Bypassed YT Throttling"
    )
    
    # FFmpeg warning
    if not has_ffmpeg:
        st.error(
            "❌ **FFmpeg not found!** Please install FFmpeg:\n\n"
            "```powershell\n"
            "# Using Scoop (recommended)\n"
            "scoop install ffmpeg\n\n"
            "# Or using Chocolatey\n"
            "choco install ffmpeg\n"
            "```"
        )
    
    # URL Input
    url = st.text_input("Paste YouTube URL:", placeholder="https://youtu.be/…")
    
    if url:
        # Fetch video info
        with st.spinner("🔍 Fetching video info..."):
            info = get_video_info(url)
        
        if not info:
            st.stop()
        
        # Display video info
        title = info.get('title', 'Unknown Title')
        thumbnail = info.get('thumbnail', '')
        
        st.subheader(title)
        
        if thumbnail:
            st.image(thumbnail, use_container_width=True)
        
        # Tabs
        tab_video, tab_audio = st.tabs(["🎥 Video", "🎵 Audio"])
        
        # ────────────────────────────────────────
        # VIDEO TAB
        # ────────────────────────────────────────
        with tab_video:
            video_options = get_video_options(info)
            
            # Build dropdown options
            option_labels = [opt['label'] for opt in video_options]
            selected_idx = st.selectbox("Select Quality:", option_labels, index=0)
            
            # Get selected option details
            selected_option = video_options[option_labels.index(selected_idx)]
            selected_option['title'] = title  # Add title for filename
            
            is_high_res = selected_option.get('is_high_res', False)
            
            # Show conversion options for high-res
            convert = False
            conversion_mode = "balanced"
            
            if is_high_res:
                st.info(
                    "ℹ️ **High Resolution Video**\n\n"
                    "This video is encoded with AV1/VP9 codec which may not be compatible with "
                    "QuickTime Player or Final Cut Pro. Enable conversion to H.265/HEVC for better compatibility."
                )
                
                convert = st.checkbox(
                    f"Convert with {encoder_display if encoder_name else 'Software Encoder'} (H.265/HEVC – smaller file)",
                    value=True
                )
                
                if convert:
                    conversion_mode = st.radio(
                        "Conversion Quality:",
                        ["Speed", "Balanced (Recommended)", "High Quality"],
                        index=1,
                        horizontal=True
                    )
                    mode_map = {
                        "Speed": "speed",
                        "Balanced (Recommended)": "balanced",
                        "High Quality": "quality"
                    }
                    conversion_mode = mode_map[conversion_mode]
            
            # Download button state
            download_disabled = not has_ffmpeg and convert and is_high_res
            
            if download_disabled:
                st.warning("⚠️ FFmpeg required for conversion. Please install FFmpeg first.")
            
            if st.button("📥 Download Video", disabled=download_disabled, key="video_dl"):
                progress_handler = ProgressHandler()
                
                result_path = download_video(
                    url,
                    selected_option,
                    convert,
                    conversion_mode,
                    progress_handler
                )
                
                if result_path:
                    st.session_state.result = {
                        'path': str(result_path),
                        'type': 'video'
                    }
                    st.rerun()
        
        # ────────────────────────────────────────
        # AUDIO TAB
        # ────────────────────────────────────────
        with tab_audio:
            audio_format = st.selectbox(
                "Select Format:",
                ["MP3", "M4A", "WAV", "FLAC"],
                index=0
            )
            
            if st.button("📥 Download Audio", key="audio_dl"):
                progress_handler = ProgressHandler()
                
                result_path = download_audio(url, audio_format, progress_handler)
                
                if result_path:
                    st.session_state.result = {
                        'path': str(result_path),
                        'type': 'audio'
                    }
                    st.rerun()
    
    # ────────────────────────────────────────
    # RESULT SECTION
    # ────────────────────────────────────────
    if 'result' in st.session_state:
        result = st.session_state.result
        file_path = Path(result['path'])
        
        if file_path.exists():
            st.success("🎉 File Ready!")
            st.balloons()
            
            # Read file for download button
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            
            st.download_button(
                label=f"💾 Download {file_path.name}",
                data=file_bytes,
                file_name=file_path.name,
                mime='video/mp4' if result['type'] == 'video' else 'audio/mpeg'
            )
            
            # Clear/Reset button
            if st.button("🗑️ Clear / Reset"):
                try:
                    file_path.unlink()
                except Exception:
                    pass
                del st.session_state.result
                st.rerun()
        else:
            # File no longer exists
            del st.session_state.result
            st.warning("⚠️ File was not found. It may have been auto-deleted.")
            st.rerun()


if __name__ == "__main__":
    main()
