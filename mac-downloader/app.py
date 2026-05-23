#!/usr/bin/env python3
"""
Pro YouTube Downloader - Streamlit App
Supports macOS with hardware-accelerated encoding via VideoToolbox
"""

import os
import re
import sys
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st
import yt_dlp

# Constants
DOWNLOAD_DIR = Path("temp_downloads")
MAX_FILE_AGE_SECONDS = 7200  # 2 hours
UNSAFE_CHARS = r'[<>:"/\\|?*\x00-\x1f]'


def detect_mac_chip() -> str:
    """Detect if running on Apple Silicon or Intel Mac."""
    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=5
        )
        if "Apple" in result.stdout:
            return "apple_silicon"
        return "intel"
    except Exception:
        return "intel"


def check_videotoolbox() -> bool:
    """Check if hevc_videotoolbox encoder is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10
        )
        return "hevc_videotoolbox" in result.stdout
    except Exception:
        return False


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available in PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def safe_filename(filename: str) -> str:
    """Create a safe filename for macOS."""
    # Remove unsafe characters
    name = re.sub(UNSAFE_CHARS, "", filename)
    # Remove path separators
    name = name.replace("/", "").replace(":", "")
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)
    # Strip leading/trailing dots and spaces
    name = name.strip(". ").strip()
    # Max length
    if len(name) > 120:
        name = name[:120]
    return name if name else "unnamed_video"


def cleanup_old_files():
    """Delete files older than MAX_FILE_AGE_SECONDS."""
    if not DOWNLOAD_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(seconds=MAX_FILE_AGE_SECONDS)
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file():
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                try:
                    f.unlink()
                except Exception:
                    pass


def get_ffmpeg_command(input_path: str, output_path: str, mode: str, use_videotoolbox: bool) -> list:
    """Build FFmpeg command based on hardware availability."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-map", "0:v:0", "-map", "0:a:0?", "-sn",
        "-pix_fmt", "yuv420p",
        "-tag:v", "hvc1",
        "-c:a", "aac", "-b:a", "128k"
    ]
    
    if use_videotoolbox:
        cmd.extend(["-c:v", "hevc_videotoolbox"])
        if mode == "speed":
            cmd.extend(["-q:v", "65", "-realtime", "1"])
        elif mode == "balanced":
            cmd.extend(["-q:v", "55", "-realtime", "0"])
        else:  # quality
            cmd.extend(["-q:v", "40", "-realtime", "0"])
    else:
        cmd.extend(["-c:v", "libx265"])
        if mode == "speed":
            cmd.extend(["-preset", "ultrafast", "-crf", "28"])
        elif mode == "balanced":
            cmd.extend(["-preset", "medium", "-crf", "24"])
        else:  # quality
            cmd.extend(["-preset", "slow", "-crf", "20"])
    
    cmd.append(output_path)
    return cmd


def get_video_options(info: dict) -> list:
    """Build quality options from video info."""
    formats = info.get("formats", [])
    options = []
    seen_heights = set()
    
    # Sort by height descending
    sorted_formats = sorted(
        [f for f in formats if f.get("height") and f.get("vcodec") != "none"],
        key=lambda x: x.get("height", 0),
        reverse=True
    )
    
    for fmt in sorted_formats:
        height = fmt.get("height")
        if not height or height < 144 or height in seen_heights:
            continue
        seen_heights.add(height)
        
        filesize = fmt.get("filesize")
        size_str = f"{filesize // (1024 * 1024)} MB" if filesize else "N/A"
        
        vcodec = fmt.get("vcodec", "").lower()
        is_high_res = height > 1080
        
        if height <= 1080:
            label = f"⚡ {height}p – Native H.264 • {size_str}"
            selector = f"bestvideo[height<={height}][vcodec^=avc]+bestaudio/best[height<={height}]"
        else:
            label = f"🌟 {height}p (AV1/VP9) • {size_str}"
            selector = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        
        options.append({
            "label": label,
            "selector": selector,
            "height": height,
            "is_high_res": is_high_res
        })
    
    # Ensure at least one option
    if not options:
        options.append({
            "label": "Best Available",
            "selector": "bestvideo+bestaudio/best",
            "height": 1080,
            "is_high_res": False
        })
    
    return options


class ProgressHandler:
    """Handle download progress updates with throttling."""
    
    def __init__(self):
        self.progress_bar = st.progress(0)
        self.status_text = st.empty()
        self.last_update = 0
        self.throttle_interval = 0.4
    
    def update(self, downloaded: float, total: float, speed: float, eta: int):
        """Update progress bar (throttled)."""
        now = time.time()
        if now - self.last_update < self.throttle_interval:
            return
        
        if total > 0:
            progress = min(downloaded / total, 1.0)
        else:
            progress = 0
        
        speed_mbs = speed / (1024 * 1024) if speed else 0
        status = f"{downloaded:.0f}MB / {total:.0f}MB | {speed_mbs:.1f} MB/s | ETA: {eta}s"
        
        self.progress_bar.progress(progress)
        self.status_text.text(status)
        self.last_update = now
    
    def finish(self):
        """Mark download as complete."""
        self.progress_bar.progress(1.0)
        self.status_text.text("✅ Download complete. Processing…")


def download_video(url: str, quality_option: dict, convert: bool, 
                   encode_mode: str, use_videotoolbox: bool) -> dict:
    """Download video with optional conversion."""
    cleanup_old_files()
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    try:
        # Fetch fresh info
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        
        safe_title = safe_filename(info.get("title", "video"))
        
        handler = ProgressHandler()
        
        def progress_hook(d):
            if d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes", 0) / (1024 * 1024)
                total = d.get("total_bytes", 0) / (1024 * 1024) or d.get("total_bytes_estimate", 0) / (1024 * 1024)
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)
                handler.update(downloaded, total, speed, eta)
        
        if convert and quality_option["is_high_res"]:
            # PATH B: Download + Convert
            raw_template = str(DOWNLOAD_DIR / f"raw_{safe_title}.%(ext)s")
            
            ydl_opts = {
                "format": quality_option["selector"],
                "outtmpl": raw_template,
                "merge_output_format": "mkv",
                "concurrent_fragment_downloads": 8,
                "retries": 3,
                "progress_hooks": [progress_hook],
                "quiet": True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            handler.finish()
            
            # Find raw file
            raw_file = None
            for f in DOWNLOAD_DIR.iterdir():
                if f.name.startswith(f"raw_{safe_title}"):
                    raw_file = f
                    break
            
            if not raw_file:
                st.error("❌ Raw file not found after download.")
                return None
            
            # Encode
            output_path = DOWNLOAD_DIR / f"{safe_title}_finalcut.mp4"
            cmd = get_ffmpeg_command(str(raw_file), str(output_path), encode_mode, use_videotoolbox)
            
            st.info(f"🎬 Encoding with {'VideoToolbox GPU' if use_videotoolbox else 'libx265 CPU'}...")
            
            process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True
            )
            
            encode_progress = st.progress(0)
            encode_status = st.empty()
            last_encode_update = 0
            duration_match = None
            
            for line in process.stderr:
                if "Duration:" in line:
                    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", line)
                    if match:
                        h, m, s = map(float, match.groups())
                        duration_match = h * 3600 + m * 60 + s
                
                if "time=" in line:
                    match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                    if match and duration_match:
                        now = time.time()
                        if now - last_encode_update >= 0.5:
                            h, m, s = map(float, match.groups())
                            current = h * 3600 + m * 60 + s
                            progress = min(current / duration_match, 1.0)
                            encode_progress.progress(progress)
                            encode_status.text(f"Encoding: {progress*100:.1f}%")
                            last_encode_update = now
            
            process.wait()
            
            if process.returncode != 0:
                st.error("❌ FFmpeg encoding failed. Try: brew install ffmpeg")
                return None
            
            # Delete raw file
            try:
                raw_file.unlink()
            except Exception:
                pass
            
            encode_progress.progress(1.0)
            encode_status.text("✅ Encoding complete!")
            final_file = output_path
            
        else:
            # PATH A: Direct Download
            out_template = str(DOWNLOAD_DIR / f"{safe_title}.%(ext)s")
            
            ydl_opts = {
                "format": quality_option["selector"],
                "outtmpl": out_template,
                "merge_output_format": "mp4",
                "concurrent_fragment_downloads": 8,
                "retries": 3,
                "progress_hooks": [progress_hook],
                "quiet": True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            handler.finish()
            
            # Find actual file (extension may differ)
            final_file = None
            for f in DOWNLOAD_DIR.iterdir():
                if f.name.startswith(safe_title) and not f.name.startswith("raw_"):
                    final_file = f
                    break
            
            if not final_file:
                st.error("❌ Downloaded file not found.")
                return None
        
        return {"path": final_file, "name": final_file.name}
        
    except Exception as e:
        st.error(f"❌ Download failed: {str(e)}")
        return None


def download_audio(url: str, audio_format: str) -> dict:
    """Download audio only."""
    cleanup_old_files()
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    try:
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        
        safe_title = safe_filename(info.get("title", "audio"))
        
        handler = ProgressHandler()
        
        def progress_hook(d):
            if d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes", 0) / (1024 * 1024)
                total = d.get("total_bytes", 0) / (1024 * 1024) or d.get("total_bytes_estimate", 0) / (1024 * 1024)
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)
                handler.update(downloaded, total, speed, eta)
        
        ext_map = {"MP3": "mp3", "M4A": "m4a", "WAV": "wav", "FLAC": "flac"}
        ext = ext_map.get(audio_format, "mp3")
        
        bitrate_map = {"MP3": "192k", "M4A": "5", "WAV": "", "FLAC": ""}
        
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(DOWNLOAD_DIR / f"{safe_title}.%(ext)s"),
            "concurrent_fragment_downloads": 8,
            "retries": 3,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": ext,
                "preferredquality": bitrate_map.get(audio_format, "192")
            }]
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        handler.finish()
        
        # Find output file
        audio_file = None
        for f in DOWNLOAD_DIR.iterdir():
            if f.name.startswith(safe_title) and f.suffix == f".{ext}":
                audio_file = f
                break
        
        if not audio_file:
            # Try to find any matching file
            for f in DOWNLOAD_DIR.iterdir():
                if f.name.startswith(safe_title):
                    audio_file = f
                    break
        
        if not audio_file:
            st.error("❌ Audio file not found.")
            return None
        
        return {"path": audio_file, "name": audio_file.name}
        
    except Exception as e:
        st.error(f"❌ Audio download failed: {str(e)}")
        return None


def get_video_info(url: str) -> dict:
    """Fetch video information."""
    try:
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        st.error(f"❌ Failed to fetch video info: {str(e)}")
        return None


# Main App
st.set_page_config(
    page_title="Pro YT Downloader",
    page_icon="🚀",
    layout="centered"
)

# System Detection
chip = detect_mac_chip()
has_videotoolbox = check_videotoolbox()
has_ffmpeg = check_ffmpeg()

encoder_name = "VideoToolbox GPU" if has_videotoolbox else "libx265 CPU"
chip_icon = "🍎" if chip == "apple_silicon" else "💻"

# Header
st.title("🚀 Pro YouTube Downloader")
st.caption(f"{chip_icon} {chip.replace('_', ' ').title()} | Encoder: {encoder_name} | ✅ Bypassed YT Throttling")

# FFmpeg Warning
if not has_ffmpeg:
    st.error("❌ **FFmpeg not found!** Install with: `brew install ffmpeg`")

# Cleanup old files
cleanup_old_files()

# URL Input
url = st.text_input("Paste YouTube URL:", placeholder="https://youtu.be/ …")

if url:
    video_info = get_video_info(url)
    
    if video_info:
        st.subheader(video_info.get("title", "Unknown Video"))
        
        thumbnail = video_info.get("thumbnail")
        if thumbnail:
            st.image(thumbnail, use_container_width=True)
        
        tabs = st.tabs(["🎥 Video", "🎵 Audio"])
        
        with tabs[0]:
            options = get_video_options(video_info)
            opt_labels = [o["label"] for o in options]
            selected_idx = st.selectbox("Quality", opt_labels, index=0)
            selected_option = options[opt_labels.index(selected_idx)]
            
            convert = False
            encode_mode = "balanced"
            
            if selected_option["is_high_res"]:
                st.info(f"ℹ️ This resolution uses AV1/VP9. Convert to H.265/HEVC for Final Cut Pro / QuickTime compatibility.")
                convert = st.checkbox(
                    f"Convert with {encoder_name} (H.265/HEVC – smaller file)",
                    value=True
                )
                
                if convert:
                    encode_mode = st.radio(
                        "Encoding Mode",
                        ["Speed", "Balanced (Recommended)", "High Quality"],
                        index=1
                    )
                    encode_mode = encode_mode.split()[0].lower()
            
            btn_disabled = not has_ffmpeg and convert and selected_option["is_high_res"]
            
            if st.button("📥 Download Video", disabled=btn_disabled):
                result = download_video(url, selected_option, convert, encode_mode, has_videotoolbox)
                if result:
                    st.session_state.result = result
                    st.rerun()
        
        with tabs[1]:
            audio_format = st.selectbox("Format", ["MP3", "M4A", "WAV", "FLAC"])
            
            if st.button("🎵 Download Audio"):
                result = download_audio(url, audio_format)
                if result:
                    st.session_state.result = result
                    st.rerun()

# Result Section
if "result" in st.session_state:
    result = st.session_state.result
    st.success("🎉 File Ready!")
    st.balloons()
    
    with open(result["path"], "rb") as f:
        st.download_button(
            label=f"📥 Download {result['name']}",
            data=f.read(),
            file_name=result["name"],
            mime="video/mp4" if result["path"].suffix == ".mp4" else "audio/mpeg"
        )
    
    if st.button("🗑️ Clear / Reset"):
        try:
            result["path"].unlink()
        except Exception:
            pass
        del st.session_state.result
        st.rerun()
