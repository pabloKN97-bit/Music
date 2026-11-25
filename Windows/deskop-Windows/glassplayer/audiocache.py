"""Caché de audio: la canción de YouTube se descarga ENTERA antes de empezar a sonar y se reproduce desde disco,
así que una conexión lenta o inestable ya no puede cortar la reproducción a media canción.

Son archivos temporales (%APPDATA%/GlassPlayer/audio): se conservan los últimos MAX_FILES para que repetir o
volver a una canción sea instantáneo, y el resto se borra solo. No son descargas de la biblioteca (para eso está el
botón «Descargar», que genera MP3 etiquetados).
"""
import glob
import os
import re
import shutil
import subprocess
import threading

from . import paths, tools, youtube

DIR = paths.AUDIO
MAX_FILES = 40
TIMEOUT = 300  # segundos máximos para una descarga
_PCT = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_TEMP = (".part", ".ytdl", ".temp")


class Cancelled(Exception):
    """La descarga se abandonó porque ya no hace falta (el usuario cambió de canción)."""


def _vid(uri):
    return uri[len(youtube.WATCH):]


def cached(uri):
    """Ruta del audio ya descargado (completo) o None."""
    for p in glob.glob(os.path.join(glob.escape(DIR), glob.escape(_vid(uri)) + ".*")):
        if ".part" not in os.path.basename(p) and not p.endswith(_TEMP) and os.path.getsize(p) > 0:
            return p
    return None


def fetch(uri, on_progress=None, cancel=None, low_priority=False):
    """Descarga la canción completa (si no está ya) y devuelve la ruta del archivo.
    on_progress(porcentaje) se llama durante la descarga; cancel() -> True aborta con Cancelled."""
    hit = cached(uri)
    if hit:
        os.utime(hit)  # la marca como la más reciente para que trim() no la borre
        return hit
    if not youtube.available():
        raise RuntimeError("yt-dlp no está instalado")
    os.makedirs(DIR, exist_ok=True)
    cmd = [tools.which("yt-dlp"), "-f", "bestaudio/best", "--no-playlist", "--no-warnings", "--newline", "--progress",
                 "-o", os.path.join(DIR, "%(id)s.%(ext)s"), uri]
    proc = tools.popen(cmd, low=low_priority, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    watchdog = threading.Timer(TIMEOUT, proc.kill)
    watchdog.start()
    try:
        for line in proc.stdout:
            if cancel and cancel():
                proc.kill()
                raise Cancelled()
            m = _PCT.search(line)
            if m and on_progress:
                on_progress(float(m.group(1)))
        rc = proc.wait()
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            proc.kill()
    path = cached(uri)
    if rc != 0 or not path:
        raise RuntimeError("no se pudo descargar el audio")
    trim()
    return path


def trim(keep=MAX_FILES):
    """Borra los archivos más antiguos de la caché, dejando los `keep` más recientes."""
    try:
        files = sorted((os.path.join(DIR, f) for f in os.listdir(DIR)), key=os.path.getmtime, reverse=True)
        for p in files[keep:]:
            os.remove(p)
    except OSError:
        pass


def clear():
    shutil.rmtree(DIR, ignore_errors=True)
