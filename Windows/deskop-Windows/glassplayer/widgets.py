"""Componentes de la interfaz: carga de imágenes, fila de canción y caja de género."""
from concurrent.futures import ThreadPoolExecutor

import shiboken6
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from . import library, youtube

# Degradados de las cajas de género (se elige uno según el id del género).
GRADIENTS = [("#ff5d8f", "#b03060"), ("#5b8def", "#2a3f9e"), ("#3ec9a7", "#1b6f78"), ("#f5a623", "#b5541a"),
             ("#a66bff", "#5a2a9e"), ("#ff7a59", "#a82f3c"), ("#4cc3ff", "#1f5f9e"), ("#8bd450", "#3d7a2e")]


class Bus(QObject):
    """Permite que un hilo en segundo plano ejecute una función en el hilo de la interfaz."""
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run)

    @Slot(object)
    def _run(self, fn):
        try:
            fn()
        except Exception:  # un fallo en un callback no debe tumbar la app
            import traceback
            traceback.print_exc()


def rounded(pix, size, radius):
    """Recorta la imagen en cuadrado, la escala a size×size y redondea las esquinas."""
    pix = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x, y = (pix.width() - size) // 2, (pix.height() - size) // 2
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(-x, -y, pix)
    p.end()
    return out


def placeholder(size, radius):
    """Carátula por defecto (nota musical sobre fondo oscuro) para canciones sin portada."""
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.fillPath(path, QColor(255, 255, 255, 30))
    p.setPen(QColor(255, 255, 255, 120))
    f = QFont()
    f.setPixelSize(int(size * 0.5))
    p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "♪")
    p.end()
    return out


class Images:
    """Descarga miniaturas en segundo plano (3 a la vez) con caché en memoria y las pone en un QLabel."""

    def __init__(self, bus):
        self.bus, self.cache, self.pool = bus, {}, ThreadPoolExecutor(max_workers=3)

    def show(self, label, source, size, radius=8):
        """source: ruta local, URL http o None (deja el hueco vacío)."""
        label.setFixedSize(size, size)
        label.setPixmap(placeholder(size, radius))
        if not source:
            return
        if not source.startswith("http"):
            pm = QPixmap(source)
            if not pm.isNull():
                label.setPixmap(rounded(pm, size, radius))
            return

        def work():
            data = self.cache.get(source)
            if data is None:
                data = youtube.download(source)
                if data:
                    self.cache[source] = data
            if data:
                self.bus.call.emit(lambda: self._apply(label, data, size, radius))
        self.pool.submit(work)

    @staticmethod
    def _apply(label, data, size, radius):
        if not shiboken6.isValid(label):  # la fila ya se redibujó
            return
        pm = QPixmap()
        if pm.loadFromData(data):
            label.setPixmap(rounded(pm, size, radius))


class Clickable(QFrame):
    clicked = Signal()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


def make_button(text, kind, cb=None, tip=None, checkable=False):
    b = QPushButton(text)
    b.setProperty("kind", kind)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    b.setCheckable(checkable)
    if tip:
        b.setToolTip(tip)
    if cb:
        b.clicked.connect(lambda _=False: cb())
    return b


def set_prop(widget, name, value):
    """Cambia una propiedad usada por el QSS y fuerza que se vuelva a aplicar el estilo."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class TrackRow(Clickable):
    """Una canción en la lista: portada, título, artista, duración, corazón, descarga y menú."""

    def __init__(self, win, t, index, playing, fav, dl_state):
        super().__init__()
        self.t, self.index = t, index
        self.setObjectName("row")
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("playing", playing)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(12)
        self.cover = QLabel()
        win.images.show(self.cover, t.get("cover") or t.get("thumb"), 44, 8)
        lay.addWidget(self.cover)
        col = QVBoxLayout()
        col.setSpacing(1)
        title = QLabel(t.get("title") or "Sin título")
        title.setProperty("role", "rtitle")
        sub = QLabel(" · ".join(x for x in (t.get("artist"), t.get("album")) if x))
        sub.setProperty("role", "muted")
        col.addWidget(title)
        col.addWidget(sub)
        lay.addLayout(col, 1)
        dur = QLabel(library.fmt(t.get("duration")) if t.get("duration") else "")
        dur.setProperty("role", "muted")
        lay.addWidget(dur)
        self.heart = make_button("♥" if fav else "♡", "heart", lambda: win.toggle_fav(t), "Favorito")
        self.heart.setProperty("on", fav)
        lay.addWidget(self.heart)
        if youtube.is_yt(t["uri"]):  # descargable
            label = {"done": "✓", "none": "⬇"}.get(dl_state, "⬇")
            tip = "Descargada: suena sin conexión" if dl_state == "done" else "Descargar como MP3"
            dl = make_button(label, "icon", (lambda: win.download_tracks([t])) if dl_state != "done" else None, tip)
            lay.addWidget(dl)
        more = make_button("⋯", "icon", None, "Más opciones")
        more.clicked.connect(lambda _=False: win.row_menu(t, more))
        lay.addWidget(more)

    def set_playing(self, on):
        if self.property("playing") != on:
            set_prop(self, "playing", on)


class GenreTile(Clickable):
    """Caja de género de Novedades: degradado, nombre, imagen y estrella de favorito."""

    def __init__(self, win, g, fav):
        super().__init__()
        self.setFixedSize(190, 116)
        self.setCursor(Qt.PointingHandCursor)
        c1, c2 = GRADIENTS[int(g["id"]) % len(GRADIENTS)]
        self.setObjectName("tile")
        self.setStyleSheet(f"QFrame#tile {{ border-radius: 14px; background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
                           f" stop:0 {c1}, stop:1 {c2}); }} QFrame#tile:hover {{ border: 2px solid rgba(255,255,255,0.55); }}")
        self.pic = QLabel(self)
        win.images.show(self.pic, g.get("picture"), 78, 10)
        self.pic.move(190 - 78 - 10, 116 - 78 - 10)
        name = QLabel(g["name"], self)
        name.setWordWrap(True)
        name.setStyleSheet("font-size: 17px; font-weight: 800; color: #ffffff; background: transparent;")
        name.setGeometry(14, 12, 112, 60)
        name.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        name.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.pic.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.star = make_button("★" if fav else "☆", "star", lambda: win.toggle_genre(g["id"]),
                                "Quitar de favoritos" if fav else "Marcar como favorito")
        self.star.setProperty("on", fav)
        self.star.setParent(self)
        self.star.move(190 - 28 - 8, 8)
        self.star.raise_()
