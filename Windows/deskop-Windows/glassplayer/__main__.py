"""Punto de entrada: python -m glassplayer   (el .exe de PyInstaller arranca aquí con run_glassplayer.py)."""
import os
import sys
import traceback

from . import __version__, paths, tools


def _log_crash(exc_type, exc, tb):
    """Si algo falla, queda escrito en %APPDATA%\\GlassPlayer\\error.log (para que me lo puedan mandar)."""
    try:
        with open(os.path.join(paths.DATA, "error.log"), "a", encoding="utf-8") as f:
            f.write("".join(traceback.format_exception(exc_type, exc, tb)) + "\n")
    except OSError:
        pass
    sys.__excepthook__(exc_type, exc, tb)


def _probe_decoder():
    """Genera un WAV de 1 s y comprueba que Qt Multimedia (FFmpeg) lo abre: detecta paquetes sin los DLL de audio."""
    import math
    import struct
    import tempfile
    import wave
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QMediaPlayer
    path = os.path.join(tempfile.gettempdir(), "glassplayer_probe.wav")
    with wave.open(path, "w") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(i / 8))) for i in range(22050)))
    mp, loop = QMediaPlayer(), QEventLoop()
    mp.durationChanged.connect(lambda d: loop.quit() if d > 0 else None)
    QTimer.singleShot(5000, loop.quit)
    mp.setSource(QUrl.fromLocalFile(path))
    loop.exec()
    return mp.duration() > 0


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    sys.excepthook = _log_crash
    if os.name == "nt":  # agrupa la ventana con su icono en la barra de tareas
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.pablo.glassplayer")
        except Exception:  # noqa: BLE001
            pass

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from .window import MainWindow

    app = QApplication(argv)
    app.setApplicationName("GlassPlayer")
    app.setApplicationVersion(__version__)
    icon_path = paths.resource("assets", "glassplayer.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    win = MainWindow()

    if "--selftest" in argv:  # lo usa la construcción automática para comprobar que el .exe funciona
        i = argv.index("--selftest")
        out = argv[i + 1] if len(argv) > i + 1 else None

        def finish():
            names = ("yt-dlp", "ffmpeg", "deno")
            line = "OK decode=%s " % _probe_decoder() + " ".join(f"{n}={bool(tools.which(n))}" for n in names)
            if out:
                with open(out, "w", encoding="utf-8") as f:
                    f.write(line + "\n")
            print(line)
            app.quit()
        QTimer.singleShot(800, finish)
        return app.exec()

    win.show()
    tools.update_ytdlp_async()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
