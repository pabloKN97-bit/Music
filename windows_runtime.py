"""Ajustes de arranque de la versión .exe para Windows (PyInstaller sobre MSYS2 UCRT64).

Se ejecuta ANTES de importar gi/Gtk para poder fijar GI_TYPELIB_PATH, GST_PLUGIN_PATH,
GDK_PIXBUF_MODULE_FILE, etc., porque GObject-Introspection solo lee esas variables la
primera vez que se usa un espacio de nombres.
"""
import os
import subprocess
import sys
from pathlib import Path


def _base():
    # PyInstaller onedir: sys._MEIPASS = <app>/_internal (ahí copiamos las DLL del runtime)
    return Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).parent)


def setup():
    b = _base()
    # Las DLL del runtime UCRT64 viven en _internal: las ponemos al principio del PATH
    # para que los subprocesos (ffmpeg, gdk-pixbuf-query-loaders) también las encuentren.
    os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")
    share = b / "share"
    if share.is_dir():
        os.environ.setdefault("XDG_DATA_DIRS", str(share))
    gir = b / "gir-1.0"
    if gir.is_dir():
        os.environ.setdefault("GI_TYPELIB_PATH", str(gir))
    gst = b / "gst-plugins"
    if gst.is_dir():
        os.environ.setdefault("GST_PLUGIN_PATH", str(gst))
    _pixbuf_cache(b)


def _pixbuf_cache(b):
    """GdkPixbuf necesita un loaders.cache apuntando a los loaders JPEG/PNG.
    Se genera una vez por equipo (en %LOCALAPPDATA%/glassplayer) con rutas reales."""
    query = b / "gdk-pixbuf-query-loaders.exe"
    loaders = b / "loaders"
    if not (query.exists() and loaders.is_dir()):
        return
    cache_dir = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "glassplayer"
    cache = cache_dir / "loaders.cache"
    if cache.exists() and not _cache_ok(cache):
        try:
            cache.unlink()
        except OSError:
            pass
    if not cache.exists():
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            out = subprocess.check_output(
                [str(query)] + [str(p) for p in sorted(loaders.glob("*.dll"))],
                text=True, timeout=60)
            cache.write_text(out, encoding="utf-8")
        except Exception:
            return
    os.environ["GDK_PIXBUF_MODULE_FILE"] = str(cache)


def _cache_ok(cache):
    try:
        for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith('"'):
                p = line.strip('"')
                if (p.startswith("/") or p[1:3] == ":\\") and not os.path.exists(p):
                    return False
                break
    except OSError:
        return False
    return True
