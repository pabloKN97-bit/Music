# -*- mode: python ; coding: utf-8 -*-
# Genera dist/GlassPlayer/GlassPlayer.exe  (pyinstaller packaging/glassplayer.spec --noconfirm)
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(ROOT, "assets"), "assets")]
tools = os.path.join(ROOT, "tools")
if os.path.isdir(tools):  # yt-dlp.exe, ffmpeg.exe y deno.exe (los descarga packaging/fetch_tools.ps1)
    datas.append((tools, "tools"))
else:
    print("AVISO: no existe la carpeta tools: ejecuta packaging/fetch_tools.ps1 antes de empaquetar")

a = Analysis(
    [os.path.join(ROOT, "run_glassplayer.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=["PySide6.QtMultimedia", "PySide6.QtSvg"],
    excludes=["tkinter", "matplotlib", "numpy", "PIL", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtCharts"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GlassPlayer",
    console=False,                       # sin ventana negra
    icon=os.path.join(ROOT, "assets", "glassplayer.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="GlassPlayer")
