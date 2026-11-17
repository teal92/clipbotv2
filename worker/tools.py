"""Frozen apps execute only their bundled tools, never CWD/PATH substitutes."""
import sys
from pathlib import Path


def media_tool(name):
    if name not in ('ffmpeg','ffprobe','yt-dlp'):
        raise ValueError('Unsupported media tool.')
    if not getattr(sys,'frozen',False):
        return name
    root=Path(sys._MEIPASS)
    path=root/'bin'/(name+('.exe' if sys.platform=='win32' else ''))
    for part in (root,root/'bin',path):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise RuntimeError('The bundled media tool is unsafe. Reinstall the Companion.')
    if not root.is_absolute() or not path.is_file():
        raise RuntimeError('The bundled media tool is missing. Reinstall the Companion.')
    return str(path.resolve())
