"""Descarga de canciones en segundo plano.

Se toma el enlace de YouTube de la pista y se envía a convertidor.py (servidor Flask local que usa
yt-dlp + ffmpeg para generar el MP3). Todo ocurre con los permisos del usuario: el convertidor se
lanza como proceso hijo, escucha solo en 127.0.0.1 en un puerto libre y no abre ningún navegador.
Úsalo con contenido que tengas derecho a descargar.
"""
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import unquote

from . import library, youtube

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(library.DATA, "venv", "bin", "python")
LOG = os.path.join(library.DATA, "convertidor.log")
QUALITY = "192"

_server = {"proc": None, "port": None}
# Sin proxies: el convertidor está en este mismo equipo.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class DownloadError(Exception):
    pass


def script_path():
    """convertidor.py junto al paquete (instalado) o en la raíz del repositorio (desarrollo)."""
    for d in (os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))):
        p = os.path.join(d, "convertidor.py")
        if os.path.isfile(p):
            return p
    return None


def python_bin():
    """Python del entorno virtual del usuario (creado por install.sh) o, si no existe, el actual."""
    return VENV_PY if os.path.exists(VENV_PY) else sys.executable


def available():
    if not script_path():
        return False
    if os.path.exists(VENV_PY):
        return True
    return all(importlib.util.find_spec(m) for m in ("flask", "yt_dlp"))


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ready(port):
    try:
        _opener.open(f"http://127.0.0.1:{port}/", timeout=1).close()
        return True
    except urllib.error.HTTPError:
        return True  # responde, aunque sea con error
    except Exception:
        return False


def ensure_server():
    """Arranca convertidor.py si no está en marcha y devuelve su puerto."""
    proc = _server["proc"]
    if proc and proc.poll() is None and _server["port"]:
        return _server["port"]
    script = script_path()
    if not script:
        raise DownloadError("No se encuentra convertidor.py (ejecuta ./install.sh)")
    port = _free_port()
    env = dict(os.environ, CONVERTIDOR_PORT=str(port))
    env["PATH"] = os.pathsep.join([os.path.expanduser("~/.local/bin"), env.get("PATH", "")])
    os.makedirs(library.DATA, exist_ok=True)
    with open(LOG, "ab") as log:
        proc = subprocess.Popen([python_bin(), script], env=env, cwd=library.DATA,
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    for _ in range(40):  # hasta ~10 s
        if proc.poll() is not None:
            break
        if _ready(port):
            _server.update(proc=proc, port=port)
            return port
        time.sleep(0.25)
    if proc.poll() is None:
        proc.terminate()
    raise DownloadError("No arrancó el convertidor (¿falta flask/yt-dlp? ejecuta ./install.sh; log: " + LOG + ")")


def stop_server():
    proc = _server["proc"]
    if proc and proc.poll() is None:
        proc.terminate()
    _server.update(proc=None, port=None)


def _unique_path(folder, name):
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", os.path.basename(name)).strip() or "audio.mp3"
    if not name.lower().endswith(".mp3"):
        name += ".mp3"
    base, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return path


def convert(url, dest_dir=None, quality=QUALITY):
    """Pide el MP3 de un enlace de YouTube al convertidor y lo guarda en dest_dir. Devuelve la ruta."""
    dest_dir = dest_dir or library.DOWNLOADS
    port = ensure_server()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/convert", data=json.dumps({"url": url, "quality": quality}).encode(),
        headers={"Content-Type": "application/json"})
    tmp = None
    try:
        with _opener.open(req, timeout=900) as r:
            os.makedirs(dest_dir, exist_ok=True)
            path = _unique_path(dest_dir, unquote(r.headers.get("X-Filename") or "audio.mp3"))
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
        os.replace(tmp, path)
        return path
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace")).get("error")
        except Exception:
            msg = None
        raise DownloadError(msg or f"El convertidor respondió con el error {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise DownloadError(f"No se pudo contactar con el convertidor: {e}")
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def download_track(t):
    """Descarga la pista de YouTube `t`, le escribe etiquetas y portada, y devuelve la pista local
    (mismo formato que la biblioteca). Se ejecuta en un hilo, nunca en el hilo de la interfaz."""
    path = convert(t["uri"])
    cover = youtube.thumbnail(t["uri"])
    try:
        library.tag_file(path, t["title"], t["artist"], "YouTube", cover)
    except Exception:
        pass  # sin etiquetas el MP3 sigue siendo válido
    track = library.read_track(path)
    track["title"], track["artist"], track["album"] = t["title"], t["artist"], "YouTube"
    if not track.get("duration"):
        track["duration"] = t.get("duration") or 0
    if not track.get("cover") and cover:
        track["cover"] = library.save_cover(cover)
    return track
