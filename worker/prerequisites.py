"""Read-only local prerequisites; no implicit installation or model download."""
import importlib.util,shutil,sys
from .tools import media_tool
from pathlib import Path

def tool_ready(name):
    try:return bool(media_tool(name)) if getattr(sys,'frozen',False) else bool(shutil.which(name))
    except (OSError,RuntimeError):return False

def prerequisites(model_directory=None):
    return {'ffmpeg':tool_ready('ffmpeg'),'ffprobe':tool_ready('ffprobe'),'captureInstalled':tool_ready('yt-dlp') if getattr(sys,'frozen',False) else importlib.util.find_spec('yt_dlp') is not None,'transcriptionInstalled':importlib.util.find_spec('faster_whisper') is not None,'metricsInstalled':importlib.util.find_spec('psutil') is not None,'modelDownloaded':bool(model_directory and (Path(model_directory)/'model.bin').is_file())}
