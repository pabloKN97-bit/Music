"""Herramientas externas (yt-dlp, ffmpeg, deno) que van dentro del instalador, en la carpeta «tools».

Todas las llamadas ocultan la ventana de consola de Windows y ponen la carpeta tools la primera en el PATH.
"""
import os
import shutil
import subprocess
import threading
import time

from . import paths

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BELOW_NORMAL = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)


def tools_dir():
    for d in (os.environ.get("GLASSPLAYER_TOOLS"), paths.resource("tools")):
        if d and os.path.isdir(d):
            return d
    return None


def env():
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    d = tools_dir()
    if d:
        e["PATH"] = d + os.pathsep + e.get("PATH", "")
    return e


def which(name):
    d = tools_dir()
    return shutil.which(name, path=(d + os.pathsep + os.environ.get("PATH", "")) if d else None)


def _prepare(cmd, kw, low):
    kw.setdefault("env", env())
    if os.name == "nt":
        flags = kw.pop("creationflags", 0) | NO_WINDOW
        if low:
            flags |= BELOW_NORMAL
        kw["creationflags"] = flags
    elif low and shutil.which("nice"):
        cmd = ["nice", "-n", "19"] + list(cmd)
    if kw.get("text") or kw.get("universal_newlines"):
        kw.setdefault("encoding", "utf-8")
        kw.setdefault("errors", "replace")
    return cmd, kw


def run(cmd, low=False, **kw):
    cmd, kw = _prepare(cmd, kw, low)
    return subprocess.run(cmd, **kw)


def popen(cmd, low=False, **kw):
    cmd, kw = _prepare(cmd, kw, low)
    return subprocess.Popen(cmd, **kw)


def update_ytdlp_async(max_age=24 * 3600):
    """YouTube cambia a menudo: una vez al día se actualiza yt-dlp en segundo plano (si la carpeta es escribible)."""
    exe, d = which("yt-dlp"), tools_dir()
    if not exe or not d or not os.path.abspath(exe).startswith(os.path.abspath(d)):
        return
    stamp = os.path.join(paths.DATA, "ytdlp_update.txt")
    try:
        if time.time() - os.path.getmtime(stamp) < max_age:
            return
    except OSError:
        pass

    def work():
        try:
            run([exe, "-U"], capture_output=True, timeout=180)
        except Exception:
            pass
        try:
            with open(stamp, "w") as f:
                f.write(str(time.time()))
        except OSError:
            pass
    threading.Thread(target=work, daemon=True).start()
