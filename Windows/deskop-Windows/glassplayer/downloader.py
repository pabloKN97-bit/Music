"""Descarga de canciones como MP3 (con etiquetas y portada) usando yt-dlp + ffmpeg incluidos en la app.
Úsalo con contenido que tengas derecho a descargar."""
import glob
import os
import re
import shutil
import subprocess
import tempfile

from . import library, tools, youtube

QUALITY = "192"


class DownloadError(Exception):
    pass


def available():
    return youtube.available() and tools.which("ffmpeg") is not None


def _unique_path(folder, name):
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", os.path.basename(name)).strip(" .") or "audio"
    if not name.lower().endswith(".mp3"):
        name += ".mp3"
    base, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return path


def convert(url, filename, dest_dir=None, quality=QUALITY):
    """Descarga el audio de un enlace de YouTube, lo convierte a MP3 y lo guarda en dest_dir. Devuelve la ruta."""
    if not available():
        raise DownloadError("Faltan yt-dlp o ffmpeg (reinstala GlassPlayer)")
    dest_dir = dest_dir or library.DOWNLOADS
    os.makedirs(dest_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="glassplayer_")
    try:
        cmd = [tools.which("yt-dlp"), "-f", "bestaudio/best", "--no-playlist", "--no-warnings", "-x",
               "--audio-format", "mp3", "--audio-quality", f"{quality}K",
               "--ffmpeg-location", os.path.dirname(tools.which("ffmpeg")),
               "-o", os.path.join(tmp, "%(id)s.%(ext)s"), url]
        r = tools.run(cmd, capture_output=True, text=True, timeout=900)
        files = glob.glob(os.path.join(glob.escape(tmp), "*.mp3"))
        if r.returncode != 0 or not files:
            last = (r.stdout + r.stderr).strip().splitlines()[-1:] or ["error desconocido"]
            raise DownloadError("No se pudo descargar: " + last[0][:200])
        path = _unique_path(dest_dir, filename)
        shutil.move(files[0], path)
        return path
    except subprocess.TimeoutExpired:
        raise DownloadError("La descarga tardó demasiado")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def download_track(t):
    """Descarga la pista de YouTube `t`, le escribe etiquetas y portada, y devuelve la pista local
    (mismo formato que la biblioteca). Se ejecuta en un hilo, nunca en el hilo de la interfaz."""
    path = convert(t["uri"], f"{t['artist']} - {t['title']}")
    cover = (youtube.download(t["cover_url"]) if t.get("cover_url") else None) or youtube.thumbnail(t["uri"])
    try:
        library.tag_file(path, t["title"], t["artist"], t.get("album") or "YouTube", cover)
    except Exception:
        pass  # sin etiquetas el MP3 sigue siendo válido
    track = library.read_track(path)
    track["title"], track["artist"], track["album"] = t["title"], t["artist"], t.get("album") or "YouTube"
    if not track.get("duration"):
        track["duration"] = t.get("duration") or 0
    if not track.get("cover") and cover:
        track["cover"] = library.save_cover(cover)
    return track
