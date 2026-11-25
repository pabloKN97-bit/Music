#!/usr/bin/env python3
"""Construye GlassPlayer para Windows (ejecutar DENTRO de MSYS2 UCRT64, tras patch_compat.py).

Empaqueta con PyInstaller y copia al lado el runtime GTK4/GStreamer/gdk-pixbuf de MSYS2,
yt-dlp.exe standalone, ffmpeg.exe, iconos y tipelibs. Resultado: dist-windows/GlassPlayer/
(portable; el .exe arranca sin instalar nada).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UC = Path(os.environ.get("MSYSTEM_PREFIX", "/ucrt64"))
WORK, DIST = ROOT / "build-windows", ROOT / "dist-windows"
APP = DIST / "GlassPlayer"
INTERNAL = APP / "_internal"


def sh(*args):
    print("+", *args)
    subprocess.run([str(a) for a in args], check=True)


def venv_python():
    for p in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if p.exists():
            return p
    raise SystemExit("No hay .venv: crea uno con 'python -m venv .venv' e instala mutagen pyinstaller flask yt-dlp")


def make_venv():
    py = venv_python() if (ROOT / ".venv").exists() else None
    if py:
        sh(py, "-m", "pip", "install", "-q", "-U", "pip")
        sh(py, "-m", "pip", "install", "-q", "mutagen", "pyinstaller", "flask", "yt-dlp")
        return py
    sh("python", "-m", "venv", ROOT / ".venv")
    return make_venv()


def copy_runtime():
    """Copia el runtime UCRT64 junto al .exe."""
    INTERNAL.mkdir(parents=True, exist_ok=True)
    n = 0
    # 1) TODAS las DLL de /ucrt64/bin (el .exe de MSYS2 depende de ellas; es la forma mas fiable)
    for src in sorted((UC / "bin").glob("*.dll")):
        if src.name.startswith(("libpython", "python3")):
            continue
        dst = INTERNAL / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            n += 1
    print(f"copiadas {n} DLL de {UC / 'bin'}")

    def copydir(src, dst, pattern="*"):
        if not src.is_dir():
            print(f"AVISO: no existe {src}")
            return
        dst.mkdir(parents=True, exist_ok=True)
        c = 0
        for p in sorted(src.rglob(pattern)):
            if p.is_file():
                q = dst / p.relative_to(src)
                q.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, q)
                c += 1
        print(f"copiados {c} ficheros: {src} -> {dst}")

    # 2) tipelibs de GObject-Introspection
    copydir(UC / "share" / "gir-1.0", INTERNAL / "gir-1.0")
    # 3) plugins de GStreamer
    copydir(UC / "lib" / "gstreamer-1.0", INTERNAL / "gst-plugins", "*.dll")
    # 4) loaders de gdk-pixbuf (JPEG/PNG para las portadas) + herramienta de caché
    copydir(UC / "lib" / "gdk-pixbuf-2.0" / "2.10.0" / "loaders", INTERNAL / "loaders", "*.dll")
    q = UC / "bin" / "gdk-pixbuf-query-loaders.exe"
    if q.exists():
        shutil.copy2(q, INTERNAL / q.name)
    # 5) iconos del tema + icono de la app
    copydir(UC / "share" / "icons" / "Adwaita", INTERNAL / "share" / "icons" / "Adwaita")
    hicolor = INTERNAL / "share" / "icons" / "hicolor" / "scalable" / "apps"
    hicolor.mkdir(parents=True, exist_ok=True)
    for icon in list(ROOT.glob("**/com.pablo.glassplayer.svg"))[:1]:
        shutil.copy2(icon, hicolor / icon.name)
        print("icono de la app copiado")
    # 6) esquemas GLib/GTK
    copydir(UC / "share" / "glib-2.0" / "schemas", INTERNAL / "share" / "glib-2.0" / "schemas")
    # 7) ffmpeg (conversión a MP3) junto al exe
    ff = UC / "bin" / "ffmpeg.exe"
    if ff.exists():
        shutil.copy2(ff, APP / "ffmpeg.exe")
        print("ffmpeg.exe copiado")
    else:
    yt = ROOT / "yt-dlp.exe"
    if yt.exists():
        shutil.copy2(yt, APP / "yt-dlp.exe")
        print("yt-dlp.exe copiado")

    else:
        print("AVISO: yt-dlp.exe no encontrado en la raiz; descargalo desde github.com/yt-dlp/yt-dlp/releases")


def build():
    WORK.mkdir(exist_ok=True)
    runner = WORK / "_gp_run.py"
    runner.write_text(

        "import sys\n"
        "if sys.platform == 'win32':\n"
        "    from glassplayer import windows_runtime\n"

        "    windows_runtime.setup()\n"

        "from glassplayer.app import App\n"
        "sys.exit(App().run(sys.argv))\n",

        encoding="utf-8")
    py = make_venv()
    sh(py, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",

       "--name", "GlassPlayer", "--paths", ROOT,
       "--distpath", DIST, "--workpath", WORK / "work", "--specpath", WORK,

       runner)
    copy_runtime()
    print(f"\nListo: {APP}")



if __name__ == "__main__":
    build()

