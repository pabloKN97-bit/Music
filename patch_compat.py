#!/usr/bin/env python3
"""Vuelve GlassPlayer multiplataforma (parche minimo para Windows).

Aplica cambios quirurgicos sobre el codigo original, sin reescribir archivos a mano:
  1. __main__.py   -> arranca windows_runtime antes de importar gi.
  2. app.py        -> Mpris (D-Bus, Linux-only) y la bandeja se desactivan en win32.
  3. youtube.py    -> resuelve yt-dlp.exe empaquetado junto al .exe.
  4. audiocache.py -> usa youtube.cmd() en vez de "yt-dlp" a pelo.
  5. downloader.py -> en Windows descarga con "yt-dlp -x --audio-format mp3" directo
                      (sin el servidor Flask convertidor.py, que no hace falta).

Uso:  python windows/patch_compat.py [raiz-del-repo]
"""
import pathlib
import shutil
import sys

REPL = [
    # 1) arranque: preparar el entorno Windows antes de importar Gtk
    ("__main__.py",
     'import sys\n\nfrom .app import App\n',
     'import sys\n\nif sys.platform == "win32":\n'
     '    from . import windows_runtime\n'
     '    windows_runtime.setup()\n\n'
     'from .app import App\n'),

    # 2a) MPRIS es D-Bus/Linux-only
    ("app.py",
     'from .mpris import Mpris\nfrom .style import build_css\n',
     'if sys.platform == "win32":\n'
     '    Mpris = None  # MPRIS/D-Bus es de Linux (en Windows tocaria SMTC via python-winsdk)\n'
     'else:\n'
     '    from .mpris import Mpris\n'
     'from .style import build_css\n'),
    ("app.py",
     '        self.mpris = Mpris(self)\n',
     '        self.mpris = Mpris(self) if Mpris else None\n'),
    ("app.py",
     '        if os.environ.get("GLASSPLAYER_NO_TRAY"):\n            return\n',
     '        if sys.platform == "win32" or os.environ.get("GLASSPLAYER_NO_TRAY"):\n'
     '            return  # en Windows no hay AppIndicator/StatusNotifier\n'),

    # 3) yt-dlp: tambien puede venir empaquetado junto al exe
    ("youtube.py",
     'def available():\n    return shutil.which("yt-dlp") is not None\n',
     'def available():\n'
     '    if shutil.which("yt-dlp"):\n'
     '        return True\n'
     '    exe = bundled_ytdlp()\n'
     '    return bool(exe and os.path.exists(exe))\n\n\n'
     'def bundled_ytdlp():\n'
     '    """yt-dlp.exe empaquetado junto a la app (PyInstaller en Windows)."""\n'
     '    for d in (os.path.dirname(sys.executable), getattr(sys, "_MEIPASS", None)):\n'
     '        if d:\n'
     '            for name in ("yt-dlp.exe", "yt-dlp"):\n'
     '                p = os.path.join(d, name)\n'
     '                if os.path.exists(p):\n'
     '                    return p\n'
     '    return None\n\n\n'
     'def cmd():\n'
     '    """Comando base de yt-dlp (resuelve el .exe empaquetado en Windows)."""\n'
     '    exe = shutil.which("yt-dlp") or bundled_ytdlp()\n'
     '    if not exe:\n'
     '        raise RuntimeError("yt-dlp no esta disponible")\n'
     '    return [exe]\n'),
    ("youtube.py",
     'out = subprocess.run(pre + ["yt-dlp", "--flat-playlist",',
     'out = subprocess.run(pre + cmd() + ["--flat-playlist",'),
    ("youtube.py",
     'out = subprocess.run(["yt-dlp", "-f", "bestaudio/best", "-g", "--no-playlist", "--no-warnings", uri],',
     'out = subprocess.run(cmd() + ["-f", "bestaudio/best", "-g", "--no-playlist", "--no-warnings", uri],'),

    # 4) caché de audio
    ("audiocache.py",
     'cmd = pre + ["yt-dlp", "-f", "bestaudio/best",',
     'cmd = pre + youtube.cmd() + ["-f", "bestaudio/best",'),

    # 5) descargas: en Windows sin servidor Flask, yt-dlp + ffmpeg directo
    ("downloader.py",
     'def available():\n'
     '    if not script_path():\n'
     '        return False\n'
     '    if os.path.exists(VENV_PY):\n'
     '        return True\n'
     '    return all(importlib.util.find_spec(m) for m in ("flask", "yt_dlp"))\n',
     'def available():\n'
     '    if os.name == "nt":\n'
     '        return bool(shutil.which("yt-dlp") or youtube.bundled_ytdlp()) and (\n'
     '            shutil.which("ffmpeg")\n'
     '            or os.path.exists(os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe")))\n'
     '    if not script_path():\n'
     '        return False\n'
     '    if os.path.exists(VENV_PY):\n'
     '        return True\n'
     '    return all(importlib.util.find_spec(m) for m in ("flask", "yt_dlp"))\n'),
    ("downloader.py",
     'def download_track(t):\n'
     '    """Descarga la pista de YouTube `t`, le escribe etiquetas y portada, y devuelve la pista local\n'
     '    (mismo formato que la biblioteca). Se ejecuta en un hilo, nunca en el hilo de la interfaz."""\n'
     '    path = convert(t["uri"])\n',
     'def _convert_direct(t):\n'
     '    """Windows: sin servidor Flask; yt-dlp extrae el audio y ffmpeg lo convierte a MP3."""\n'
     '    exe = shutil.which("yt-dlp") or youtube.bundled_ytdlp()\n'
     '    if not exe:\n'
     '        raise DownloadError("No se encuentra yt-dlp")\n'
     '    out_dir = library.DOWNLOADS\n'
     '    os.makedirs(out_dir, exist_ok=True)\n'
     '    app_dir = os.path.dirname(sys.executable)\n'
     '    if not shutil.which("ffmpeg") and not os.path.exists(os.path.join(app_dir, "ffmpeg.exe")):\n'
     '        raise DownloadError("No se encuentra ffmpeg junto a la app")\n'
     '    safe = re.sub(r\'[\\\\/:*?"<>|\\x00-\\x1f]+\', "_", f"{t[\'artist\']} - {t[\'title\']}") or "audio"\n'
     '    template = os.path.join(out_dir, safe + ".%(ext)s")\n'
     '    subprocess.run([exe, "-x", "--audio-format", "mp3", "--audio-quality", QUALITY,\n'
     '                    "--no-playlist", "--no-warnings", "--ffmpeg-location", app_dir,\n'
     '                    "-o", template, t["uri"]], check=True, timeout=900)\n'
     '    base = template[: template.rfind(".")]\n'
     '    for ext in ("mp3", "m4a", "opus", "webm"):\n'
     '        p = base + "." + ext\n'
     '        if os.path.exists(p):\n'
     '            return p\n'
     '    raise DownloadError("No se genero el archivo de audio")\n\n\n'
     'def download_track(t):\n'
     '    """Descarga la pista de YouTube `t`, le escribe etiquetas y portada, y devuelve la pista local\n'
     '    (mismo formato que la biblioteca). Se ejecuta en un hilo, nunca en el hilo de la interfaz."""\n'
     '    path = _convert_direct(t) if os.name == "nt" else convert(t["uri"])\n'),
]


def main():
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path.cwd()
    pkg = root / "glassplayer"
    if not pkg.is_dir():
        # permite ejecutarlo con los .py sueltos (sin carpeta glassplayer)
        pkg = root
    errors = []
    for fname, old, new in REPL:
        p = pkg / fname
        src = p.read_text(encoding="utf-8")
        if old not in src:
            errors.append(f"{fname}: NO se encontro el fragmento esperado (el archivo ya esta parcheado?)")
            continue
        p.chmod(p.stat().st_mode | 0o200)  # por si el fichero venia de solo lectura
        p.write_text(src.replace(old, new, 1), encoding="utf-8")
        print(f"OK  {fname}")
    # copia windows_runtime.py dentro del paquete (junto al script o en <raiz>/windows)
    dst = pkg / "windows_runtime.py"
    for cand in (pathlib.Path(__file__).resolve().parent / "windows_runtime.py",
                 root / "windows" / "windows_runtime.py"):
        if cand.exists():
            shutil.copy2(cand, dst)
            break
    else:
        raise SystemExit("No encuentro windows_runtime.py (deberia estar junto a patch_compat.py)")
    print(f"OK  {dst.name} (copiado en el paquete)")
    if errors:
        print("\nAVISOS:")
        print("\n".join(errors))
        sys.exit(1)
    print("\nParche aplicado.")


if __name__ == "__main__":
    main()
