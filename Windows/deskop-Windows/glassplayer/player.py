"""Reproductor de audio (QMediaPlayer): envuelve Qt Multimedia con las señales que usa la interfaz."""
import os

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class Player(QObject):
    position = Signal(int)   # milisegundos
    duration = Signal(int)
    playing_changed = Signal(bool)
    ended = Signal()
    failed = Signal(str)

    def __init__(self, volume=0.8, parent=None):
        super().__init__(parent)
        self.mp = QMediaPlayer(self)
        self._end_sent = False
        self.out = None
        if not os.environ.get("GLASSPLAYER_NO_AUDIO"):  # solo para pruebas sin tarjeta de sonido
            self.out = QAudioOutput(self)
            self.out.setVolume(volume)
            self.mp.setAudioOutput(self.out)
        self.mp.positionChanged.connect(self._on_position)
        self.mp.durationChanged.connect(lambda v: self.duration.emit(int(v)))
        self.mp.playbackStateChanged.connect(lambda s: self.playing_changed.emit(s == QMediaPlayer.PlayingState))
        self.mp.mediaStatusChanged.connect(self._status)
        self.mp.errorOccurred.connect(lambda _e, msg: self.failed.emit(msg or "Error de reproducción"))

    def _emit_ended(self):
        if not self._end_sent:
            self._end_sent = True
            self.ended.emit()

    def _on_position(self, v):
        self.position.emit(int(v))
        d = self.mp.duration()
        if d > 0 and v >= d - 20 and not self._end_sent and self.mp.playbackState() == QMediaPlayer.PlayingState:
            QTimer.singleShot(700, self._end_guard)  # normalmente EndOfMedia llega antes; si no, se da por terminada

    def _end_guard(self):
        d = self.mp.duration()
        if d > 0 and self.mp.position() >= d - 50 and self.mp.playbackState() == QMediaPlayer.PlayingState:
            self._emit_ended()

    def _status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self._emit_ended()
        elif status == QMediaPlayer.InvalidMedia:
            self.failed.emit("formato de audio no compatible")

    def load(self, uri):
        """Carga y reproduce un archivo (file:///...) o una dirección http."""
        self._end_sent = False
        self.mp.setSource(QUrl(uri))
        self.mp.play()

    def stop(self):
        self._end_sent = True  # al parar a mano no debe saltar a la siguiente canción
        self.mp.stop()
        self.mp.setSource(QUrl())

    def toggle(self):
        if self.mp.playbackState() == QMediaPlayer.PlayingState:
            self.mp.pause()
        elif self.mp.source().isValid():
            self.mp.play()

    def is_playing(self):
        return self.mp.playbackState() == QMediaPlayer.PlayingState

    def seek(self, ms):
        self.mp.setPosition(int(ms))

    def pos(self):
        return self.mp.position()

    def set_volume(self, percent):
        if self.out:
            self.out.setVolume(max(0, min(100, percent)) / 100)
