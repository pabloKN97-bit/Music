"""Ventana principal de GlassPlayer: biblioteca, listas, Novedades, YouTube, cola, aleatorio y descargas."""
import os
import random
import threading
import time

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QColorDialog, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QMenu, QMessageBox, QScrollArea, QSlider, QStackedWidget, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

from . import audiocache, downloader, library, news, paths, settings, style, youtube
from .player import Player
from .widgets import Bus, GenreTile, Images, TrackRow, make_button, set_prop

NAV = [("recent", "🕘  Recientes"), ("songs", "🎵  Canciones"), ("favs", "♥  Favoritos"),
       ("news", "✨  Novedades"), ("yt", "🔎  YouTube"), ("queue", "☰  Cola")]
TITLES = {"recent": "Recientes", "songs": "Canciones", "favs": "Favoritos", "news": "Novedades", "yt": "YouTube",
          "queue": "Cola"}
AUDIO_FILTER = "Audio (*.mp3 *.m4a *.aac *.flac *.wav *.ogg *.opus *.wma);;Todos los archivos (*)"


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def label(text="", role=None):
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    return lb


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GlassPlayer")
        self.resize(1180, 760)
        self.setMinimumSize(920, 600)
        self.lib = library.load()
        self.theme = settings.load()
        self.bus = Bus()
        self.images = Images(self.bus)
        self.player = Player(self.theme["volume"] / 100, self)

        self.view = "recent"
        self.cur = None            # canción actual
        self.queue, self.idx = [], -1
        self.up_next = []          # «Reproducir a continuación» / cola del usuario
        self.shuffle_on = False    # interruptor «Aleatorio» (listas creadas por el usuario)
        self._shuffled = False     # la cola actual está barajada
        self._orig_queue = []      # la cola en su orden original, para volver a él al desactivar
        self._token = 0
        self._preload_token, self._prefetch_uri = None, None
        self.yt_results, self.yt_status = [], ""
        self.news_genres, self.news_tracks, self.news_status = [], {}, {}
        self._news_busy, self._genres_busy, self.genres_status = set(), False, ""
        self.dl_status, self._dl_busy, self._flash = "", False, ""
        self.rows, self._rendered_view, self._seeking = [], None, False

        self._build_ui()
        self.apply_theme()
        self._connect()
        self._build_tray()
        self.render_sidebar()
        self.render()
        self.show_track()

    # ------------------------------------------------------------------ construcción de la interfaz
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setSpacing(0)
        outer.addLayout(body, 1)

        # Barra lateral
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(238)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 14, 12, 12)
        sl.setSpacing(2)
        sl.addWidget(label("♪  GlassPlayer", "logo"))
        sl.addSpacing(8)
        sl.addWidget(label("BIBLIOTECA", "caption"))
        self.nav = {}
        for key, text in NAV:
            b = make_button(text, "nav", lambda k=key: self.set_view(k), checkable=True)
            self.nav[key] = b
            sl.addWidget(b)
        sl.addSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label("LISTAS", "caption"), 1)
        head.addWidget(make_button("＋", "icon", self.new_playlist_dialog, "Nueva lista"))
        sl.addLayout(head)
        self.pl_scroll = QScrollArea()
        self.pl_scroll.setWidgetResizable(True)
        self.pl_host = QWidget()
        self.pl_lay = QVBoxLayout(self.pl_host)
        self.pl_lay.setContentsMargins(0, 0, 0, 0)
        self.pl_lay.setSpacing(2)
        self.pl_lay.addStretch(1)
        self.pl_scroll.setWidget(self.pl_host)
        sl.addWidget(self.pl_scroll, 1)
        sl.addWidget(make_button("＋  Añadir MP3 del equipo", "nav", self.add_files))
        sl.addWidget(make_button("🎨  Estilo", "nav", self.open_style))
        body.addWidget(side)

        # Zona principal
        main = QVBoxLayout()
        main.setContentsMargins(26, 18, 26, 8)
        main.setSpacing(4)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar canciones en YouTube…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(380)
        self.search.returnPressed.connect(lambda: self.yt_search(self.search.text()))
        top.addWidget(self.search)
        top.addStretch(1)
        main.addLayout(top)
        hdr = QHBoxLayout()
        self.btn_back = make_button("←  Novedades", "ghost", lambda: self.set_view("news"))
        hdr.addWidget(self.btn_back)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        self.l_crumb, self.l_page = label("", "crumb"), label("", "title")
        tcol.addWidget(self.l_crumb)
        tcol.addWidget(self.l_page)
        hdr.addLayout(tcol, 1)
        self.btn_gfav = make_button("☆  Favorito", "ghost", lambda: self.toggle_genre(self.view[5:]))
        self.btn_shuffle = make_button("🔀  Aleatorio", "ghost", self.toggle_shuffle,
                                       "Reproducir la lista en orden aleatorio (pulsa de nuevo para desactivarlo)",
                                       checkable=True)
        self.btn_clear = make_button("Vaciar cola", "ghost", self.clear_queue)
        self.btn_add = make_button("＋  Añadir MP3", "ghost", self.add_files)
        self.btn_dl = make_button("⬇  Descargar", "ghost", self.download_view, "Descargar las canciones de esta lista como MP3")
        self.btn_all = make_button("▶  Reproducir", "primary", self.play_all)
        for b in (self.btn_gfav, self.btn_shuffle, self.btn_clear, self.btn_add, self.btn_dl, self.btn_all):
            hdr.addWidget(b)
        main.addLayout(hdr)
        self.l_status = label("", "status")
        main.addWidget(self.l_status)
        self.stack = QStackedWidget()
        self.list = QListWidget()
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setSpacing(2)
        self.grid_area = QScrollArea()
        self.grid_area.setWidgetResizable(True)
        self.grid_area.setFrameShape(QFrame.NoFrame)
        self.grid_host = QWidget()
        self.grid_lay = QVBoxLayout(self.grid_host)
        self.grid_lay.setContentsMargins(0, 0, 8, 0)
        self.grid_area.setWidget(self.grid_host)
        self.stack.addWidget(self.list)
        self.stack.addWidget(self.grid_area)
        main.addWidget(self.stack, 1)
        body.addLayout(main, 1)

        # Barra de reproducción
        bar = QFrame()
        bar.setObjectName("transport")
        bar.setFixedHeight(96)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(18, 8, 18, 8)
        left = QHBoxLayout()
        left.setSpacing(12)
        self.t_cover = QLabel()
        self.t_cover.setFixedSize(56, 56)
        left.addWidget(self.t_cover)
        info = QVBoxLayout()
        info.setSpacing(1)
        info.addStretch(1)
        self.t_title, self.t_artist = label("", "now"), label("", "muted")
        info.addWidget(self.t_title)
        info.addWidget(self.t_artist)
        info.addStretch(1)
        left.addLayout(info)
        self.t_heart = make_button("♡", "heart", lambda: self.cur and self.toggle_fav(self.cur), "Favorito")
        left.addWidget(self.t_heart)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(330)
        bl.addWidget(left_w)
        center = QVBoxLayout()
        center.setSpacing(2)
        ctr = QHBoxLayout()
        ctr.addStretch(1)
        self.b_prev = make_button("⏮", "icon", self.go_prev, "Anterior")
        self.b_play = make_button("▶", "play", self.toggle, "Reproducir / pausa")
        self.b_next = make_button("⏭", "icon", self.go_next, "Siguiente")
        for b in (self.b_prev, self.b_play, self.b_next):
            ctr.addWidget(b)
        ctr.addStretch(1)
        center.addLayout(ctr)
        seek = QHBoxLayout()
        self.l_pos, self.l_dur = label("0:00", "muted"), label("0:00", "muted")
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 1)
        seek.addWidget(self.l_pos)
        seek.addWidget(self.seek, 1)
        seek.addWidget(self.l_dur)
        center.addLayout(seek)
        bl.addLayout(center, 1)
        right = QHBoxLayout()
        right.addStretch(1)
        right.addWidget(label("🔊"))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(self.theme["volume"])
        self.vol.setFixedWidth(110)
        right.addWidget(self.vol)
        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setFixedWidth(200)
        bl.addWidget(right_w)
        outer = self.centralWidget().layout()
        outer.addWidget(bar)

    def _connect(self):
        p = self.player
        p.position.connect(self.on_position)
        p.duration.connect(self.on_duration)
        p.playing_changed.connect(self.show_state)
        p.ended.connect(self.go_next)
        p.failed.connect(self.on_player_error)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek.sliderReleased.connect(self._seek_released)
        self.seek.sliderMoved.connect(lambda v: self.l_pos.setText(library.fmt(v / 1000)))
        self.vol.valueChanged.connect(self.on_volume)
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.toggle)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))
        for key in (Qt.Key_MediaTogglePlayPause, Qt.Key_MediaPlay, Qt.Key_MediaPause):
            QShortcut(QKeySequence(key), self, activated=self.toggle)
        QShortcut(QKeySequence(Qt.Key_MediaNext), self, activated=self.go_next)
        QShortcut(QKeySequence(Qt.Key_MediaPrevious), self, activated=self.go_prev)

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        menu = QMenu(self)
        for text, fn in (("Mostrar GlassPlayer", self.show_window), ("Reproducir / pausa", self.toggle),
                         ("Siguiente", self.go_next), ("Anterior", self.go_prev),
                         ("Salir", QApplication.instance().quit)):
            act = QAction(text, self)
            act.triggered.connect(lambda _=False, f=fn: f())
            menu.addAction(act)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.Trigger else None)
        self.tray.setToolTip("GlassPlayer")
        self.tray.show()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def apply_theme(self):
        QApplication.instance().setStyleSheet(style.build_qss(self.theme))

    def closeEvent(self, e):
        self.player.stop()
        if self.tray:
            self.tray.hide()
        super().closeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.view == "news" and self.news_genres and self._grid_cols() != getattr(self, "_cols", None):
            QTimer.singleShot(0, self.render_news_grid)

    # ------------------------------------------------------------------ hilos
    def spawn(self, work, done=None):
        """Ejecuta work() en un hilo y done(resultado, error) en el hilo de la interfaz."""
        def run():
            try:
                res, err = work(), None
            except Exception as e:  # noqa: BLE001
                res, err = None, e
            if done:
                self.bus.call.emit(lambda: done(res, err))
        threading.Thread(target=run, daemon=True).start()

    def flash(self, text, secs=4):
        self._flash = text
        self.refresh_status()

        def clear():
            if self._flash == text:
                self._flash = ""
                self.refresh_status()
        QTimer.singleShot(int(secs * 1000), clear)

    # ------------------------------------------------------------------ vistas
    def set_view(self, key):
        self.view = key
        self._flash = ""  # un aviso temporal no debe tapar el estado de la nueva pantalla
        self.render_sidebar()
        self.render()
        if key == "news":
            self.load_genres()
        elif key.startswith("news:"):
            self.load_chart(key[5:])

    def track_by_uri(self):
        return {t["uri"]: t for t in self.lib["tracks"]}

    def view_tracks(self):
        v, by = self.view, self.track_by_uri()
        if v == "recent":
            return list(self.lib["recent"])
        if v == "songs":
            return list(self.lib["tracks"])
        if v == "favs":
            return [by[u] for u in self.lib["favorites"] if u in by]
        if v == "yt":
            return self.yt_results
        if v == "queue":
            return self.queue_items()
        if v.startswith("pl:"):
            return [by[u] for u in self.lib["playlists"].get(v[3:], []) if u in by]
        if v.startswith("news:"):  # solo las ya encontradas en YouTube
            return [t for t in self.news_tracks.get(v[5:], []) if t.get("uri")]
        return []

    def queue_items(self):
        upcoming = self.queue[self.idx + 1:] if self.idx >= 0 else []
        return list(self.up_next) + list(upcoming)

    def is_fav(self, t):
        return t["uri"] in self.lib["favorites"]

    def local_for(self, t):
        """Ruta del MP3 descargado de una canción de YouTube (o None)."""
        uri = self.lib["downloads"].get(t["uri"])
        path = library.path_of(uri) if uri else None
        return path if path and os.path.isfile(path) else None

    def dl_state(self, t):
        return "done" if self.local_for(t) else "none"

    def render_sidebar(self):
        key = "news" if self.view.startswith("news:") else self.view
        for k, b in self.nav.items():
            b.setChecked(k == key)
        clear_layout(self.pl_lay)
        for name in self.lib["playlists"]:
            text = library.DOWNLOADS_LABEL if name == library.DOWNLOADS_PLAYLIST else name
            b = make_button("📃  " + text, "nav", lambda n=name: self.set_view("pl:" + n), checkable=True)
            b.setChecked(self.view == "pl:" + name)
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, n=name, w=b: self.playlist_menu(n, w.mapToGlobal(pos)))
            self.pl_lay.addWidget(b)
        self.pl_lay.addStretch(1)

    def playlist_menu(self, name, global_pos):
        if name == library.DOWNLOADS_PLAYLIST:
            return
        m = QMenu(self)
        m.addAction("Eliminar lista", lambda: self.delete_playlist(name))
        m.exec(global_pos)

    def status_text(self):
        tr, v = self.view_tracks(), self.view
        if self.dl_status:
            return self.dl_status
        if self._flash:
            return self._flash
        if v == "news":
            return self.genres_status or ("" if self.news_genres else "Sin géneros")
        if v.startswith("news:"):
            return self.news_status.get(v[5:], "") or ("" if tr else "Sin canciones por ahora")
        if v == "yt":
            return self.yt_status or ("" if tr else "Escribe en la barra superior y pulsa Intro para buscar en YouTube")
        if v == "recent":
            return "" if tr else "Aún no has escuchado nada"
        if v == "queue":
            return "" if tr else "La cola está vacía. Usa «⋯ → Añadir a la cola» en cualquier canción"
        return "" if tr else "Aún no hay canciones aquí"

    def refresh_status(self):
        self.l_status.setText(self.status_text())

    def render(self):
        v, tr = self.view, self.view_tracks()
        in_genre, is_pl, grid = v.startswith("news:"), v.startswith("pl:"), v == "news"
        self.stack.setCurrentIndex(1 if grid else 0)
        if in_genre:
            g = self.genre(v[5:])
            self.l_page.setText(g["name"] if g else "Género")
            self.l_crumb.setText("NOVEDADES · TENDENCIAS")
            self.btn_gfav.setText("★  Favorito" if v[5:] in self.lib["news_genres"] else "☆  Favorito")
        elif is_pl:
            name = v[3:]
            self.l_page.setText(library.DOWNLOADS_LABEL if name == library.DOWNLOADS_PLAYLIST else name)
            self.l_crumb.setText("LISTA")
        else:
            self.l_page.setText(TITLES.get(v, ""))
            self.l_crumb.setText("BIBLIOTECA")
        has_dl = any(youtube.is_yt(t["uri"]) and not self.local_for(t) for t in tr)
        self.btn_back.setVisible(in_genre)
        self.btn_gfav.setVisible(in_genre)
        self.btn_shuffle.setVisible(is_pl and len(tr) > 1)
        self.btn_shuffle.setChecked(self.shuffle_on)
        self.btn_add.setVisible(is_pl or v == "songs")
        self.btn_clear.setVisible(v == "queue" and bool(tr))
        self.btn_dl.setVisible(has_dl and not grid)
        self.btn_all.setVisible(bool(tr) and not grid and v != "queue")
        self.refresh_status()
        if grid:
            self.render_news_grid()
            return
        bar = self.list.verticalScrollBar()
        keep = bar.value() if self._rendered_view == v else 0
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        self.rows = []
        for i, t in enumerate(tr):
            row = TrackRow(self, t, i, self.is_current(t), self.is_fav(t), self.dl_state(t))
            row.clicked.connect(lambda i=i: self.on_row(i))
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            self.rows.append(row)
        self.list.setUpdatesEnabled(True)
        bar.setValue(keep)
        self._rendered_view = v

    def is_current(self, t):
        return bool(self.cur) and self.cur["uri"] == t["uri"]

    def refresh_playing(self):
        for r in self.rows:
            r.set_playing(self.is_current(r.t))

    def on_row(self, i):
        tr = self.view_tracks()
        if i >= len(tr):
            return
        if self.view == "queue":
            if i < len(self.up_next):
                self._play(self.up_next.pop(i))
            else:
                self.play_index(self.idx + 1 + (i - len(self.up_next)))
            self.render()
        else:
            self.play_list(tr, i)

    def row_menu(self, t, anchor):
        m = QMenu(self)
        m.addAction("Reproducir a continuación", lambda: self.queue_add(t, front=True))
        m.addAction("Añadir a la cola", lambda: self.queue_add(t))
        m.addSeparator()
        sub = m.addMenu("Añadir a una lista")
        for name in self.lib["playlists"]:
            text = library.DOWNLOADS_LABEL if name == library.DOWNLOADS_PLAYLIST else name
            sub.addAction(text, lambda n=name: self.add_to_playlist(n, t))
        sub.addSeparator()
        sub.addAction("Nueva lista…", lambda: self.add_to_new_playlist(t))
        if not any(x["uri"] == t["uri"] for x in self.lib["tracks"]):
            m.addAction("Añadir a la biblioteca", lambda: (self.add_to_library(t), self.commit()))
        if youtube.is_yt(t["uri"]) and not self.local_for(t):
            m.addAction("Descargar como MP3", lambda: self.download_tracks([t]))
        if self.view.startswith("pl:"):
            m.addAction("Quitar de esta lista", lambda: self.remove_from_playlist(self.view[3:], t))
        if self.view == "queue":
            m.addAction("Quitar de la cola", lambda: self.queue_remove(t))
        if self.view in ("songs", "favs", "recent") and any(x["uri"] == t["uri"] for x in self.lib["tracks"]):
            m.addSeparator()
            m.addAction("Eliminar de la biblioteca", lambda: self.remove_track(t))
        m.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))

    # ------------------------------------------------------------------ cola
    def queue_add(self, t, front=False):
        if front:
            self.up_next.insert(0, dict(t))
        else:
            self.up_next.append(dict(t))
        self.flash("Añadida a la cola" if not front else "Sonará a continuación")
        if self.view == "queue":
            self.render()

    def queue_remove(self, t):
        for k, x in enumerate(self.up_next):
            if x["uri"] == t["uri"]:
                del self.up_next[k]
                break
        else:
            pos = next((k for k in range(self.idx + 1, len(self.queue)) if self.queue[k]["uri"] == t["uri"]), None)
            if pos is not None:
                del self.queue[pos]
        self.render()

    def clear_queue(self):
        self.up_next.clear()
        if self.idx >= 0:
            del self.queue[self.idx + 1:]
        self.render()

    # ------------------------------------------------------------------ biblioteca
    def commit(self, sidebar=False):
        library.save(self.lib)
        if sidebar:
            self.render_sidebar()
        self.render()
        self.update_heart()

    def add_to_library(self, t):
        if not any(x["uri"] == t["uri"] for x in self.lib["tracks"]):
            self.lib["tracks"].append(dict(t))

    def toggle_fav(self, t):
        favs = self.lib["favorites"]
        if t["uri"] in favs:
            favs.remove(t["uri"])
        else:
            self.add_to_library(t)
            favs.append(t["uri"])
        self.commit()

    def create_playlist(self, name):
        name = (name or "").strip()
        if not name or name in self.lib["playlists"]:
            return None
        self.lib["playlists"][name] = []
        self.commit(sidebar=True)
        return name

    def new_playlist_dialog(self):
        name, ok = QInputDialog.getText(self, "Nueva lista", "Nombre de la lista:")
        if ok and name.strip():
            if self.create_playlist(name) is None:
                self.flash("Ya existe una lista con ese nombre o el nombre no es válido")
            return name.strip()
        return None

    def delete_playlist(self, name):
        if name == library.DOWNLOADS_PLAYLIST:
            return
        if QMessageBox.question(self, "Eliminar lista", f"¿Eliminar la lista «{name}»?\nLas canciones no se borran.") \
                != QMessageBox.Yes:
            return
        self.lib["playlists"].pop(name, None)
        if self.view == "pl:" + name:
            self.view = "songs"
        self.commit(sidebar=True)

    def add_to_playlist(self, name, t):
        self.add_to_library(t)
        lst = self.lib["playlists"].setdefault(name, [])
        if t["uri"] not in lst:
            lst.append(t["uri"])
        self.commit()
        self.flash(f"Añadida a «{library.DOWNLOADS_LABEL if name == library.DOWNLOADS_PLAYLIST else name}»")

    def add_to_new_playlist(self, t):
        name = self.new_playlist_dialog()
        if name and name in self.lib["playlists"]:
            self.add_to_playlist(name, t)

    def remove_from_playlist(self, name, t):
        lst = self.lib["playlists"].get(name, [])
        if t["uri"] in lst:
            lst.remove(t["uri"])
        self.commit()

    def remove_track(self, t):
        uri = t["uri"]
        self.lib["tracks"] = [x for x in self.lib["tracks"] if x["uri"] != uri]
        self.lib["favorites"] = [u for u in self.lib["favorites"] if u != uri]
        self.lib["recent"] = [x for x in self.lib["recent"] if x["uri"] != uri]
        for lst in self.lib["playlists"].values():
            while uri in lst:
                lst.remove(uri)
        library.drop_cover(t.get("cover"), self.lib["tracks"] + self.lib["recent"])
        self.commit()

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Añadir canciones", os.path.expanduser("~/Music"), AUDIO_FILTER)
        if not files:
            return
        target = self.view[3:] if self.view.startswith("pl:") else None
        self.spawn(lambda: [library.read_track(f) for f in files], lambda res, err: self._files_read(res, target))

    def _files_read(self, tracks, target):
        known = {t["uri"] for t in self.lib["tracks"]}
        for t in tracks or []:
            if t["uri"] not in known:
                self.lib["tracks"].append(t)
            if target:
                lst = self.lib["playlists"].setdefault(target, [])
                if t["uri"] not in lst:
                    lst.append(t["uri"])
        self.commit()
        self.flash(f"{len(tracks or [])} canciones añadidas")

    # ------------------------------------------------------------------ YouTube
    def yt_search(self, q):
        q = q.strip()
        if not q:
            return
        self.yt_results, self.yt_status = [], f"Buscando «{q}»…"
        self.set_view("yt")
        if not youtube.available():
            self.yt_status = "Falta yt-dlp: reinstala GlassPlayer"
            self.refresh_status()
            return
        self.spawn(lambda: youtube.search(q), lambda res, err: self._yt_done(q, res, err))

    def _yt_done(self, q, res, err):
        if err or not res:
            self.yt_results, self.yt_status = [], ("No se pudo buscar en YouTube. Comprueba tu conexión." if err
                                                   else f"Sin resultados para «{q}»")
        else:
            self.yt_results, self.yt_status = res, ""
        if self.view == "yt":
            self.render()

    # ------------------------------------------------------------------ Novedades (Deezer + YouTube)
    def genre(self, gid):
        return next((g for g in self.news_genres if g["id"] == gid), None)

    def load_genres(self):
        if self.news_genres or self._genres_busy:
            return
        self._genres_busy, self.genres_status = True, "Cargando géneros…"
        self.refresh_status()
        self.spawn(news.genres, self._genres_done)

    def _genres_done(self, res, err):
        self._genres_busy = False
        self.news_genres = res or []
        self.genres_status = "" if res else "No se pudo conectar con Deezer. Comprueba tu conexión."
        if self.view == "news" or self.view.startswith("news:"):
            self.render()

    def _grid_cols(self):
        return max(2, (self.stack.width() - 24) // 206)

    def render_news_grid(self):
        self._cols = self._grid_cols()
        clear_layout(self.grid_lay)
        favs = [g for g in self.news_genres if g["id"] in self.lib["news_genres"]]
        rest = [g for g in self.news_genres if g["id"] not in self.lib["news_genres"]]
        for title, items in (("TUS GÉNEROS", favs), ("TODOS LOS GÉNEROS" if favs else "GÉNEROS", rest)):
            if not items:
                continue
            self.grid_lay.addWidget(label(title, "caption"))
            grid = QGridLayout()
            grid.setSpacing(14)
            for k, g in enumerate(items):
                tile = GenreTile(self, g, g["id"] in self.lib["news_genres"])
                tile.clicked.connect(lambda gid=g["id"]: self.set_view("news:" + gid))
                grid.addWidget(tile, k // self._cols, k % self._cols)
            grid.setColumnStretch(self._cols, 1)
            self.grid_lay.addLayout(grid)
            self.grid_lay.addSpacing(14)
        self.grid_lay.addStretch(1)

    def toggle_genre(self, gid):
        favs = self.lib["news_genres"]
        favs.remove(gid) if gid in favs else favs.append(gid)
        library.save(self.lib)
        self.render()

    def load_chart(self, gid):
        """Tendencias de Deezer y, después, búsqueda en YouTube de las canciones que aún no tienen enlace."""
        if gid in self._news_busy:
            return
        self._news_busy.add(gid)
        if gid not in self.news_tracks:
            self.news_status[gid] = "Cargando tendencias…"
            self.refresh_status()
        self.spawn(lambda: news.chart(gid), lambda res, err: self._chart_done(gid, res))

    def _chart_done(self, gid, tracks):
        if tracks is None:
            self._news_busy.discard(gid)
            if gid not in self.news_tracks:
                self.news_status[gid] = "No se pudo conectar con Deezer. Comprueba tu conexión."
            if self.view == "news:" + gid:
                self.render()
            return
        self.news_tracks[gid] = tracks
        pending = [t for t in tracks if not t.get("uri")]
        if pending and not youtube.available():
            self._news_busy.discard(gid)
            self.news_status[gid] = "Falta yt-dlp: reinstala GlassPlayer"
        elif pending:
            self.news_status[gid] = f"Buscando en YouTube… 0/{len(pending)}"

            def work():  # una búsqueda cada vez, con prioridad mínima y esperando a que la canción pulsada esté cargada
                for i, t in enumerate(pending, 1):
                    news.resolve(t, self.wait_playback_idle)
                    self.bus.call.emit(lambda i=i: self._chart_progress(gid, i, len(pending)))
            threading.Thread(target=work, daemon=True).start()
        else:
            self._news_busy.discard(gid)
            self.news_status[gid] = ""
        if self.view == "news:" + gid:
            self.render()

    def _chart_progress(self, gid, done, total):
        finished = done == total
        if finished:
            self._news_busy.discard(gid)
            news.save()
            self.news_status[gid] = ""
        else:
            self.news_status[gid] = f"Buscando en YouTube… {done}/{total}"
        if self.view != "news:" + gid:
            return
        if finished or done == 1 or done % 4 == 0:  # redibujar solo de vez en cuando para que la lista no parpadee
            self.render()
        else:
            self.refresh_status()

    def wait_playback_idle(self):
        """Hilo de fondo: espera (máx. 90 s) a que la canción que se acaba de pulsar esté cargada."""
        end = time.monotonic() + 90
        while self._preload_token is not None and time.monotonic() < end:
            time.sleep(0.5)

    # ------------------------------------------------------------------ reproducción
    def play_list(self, tracks, i):
        self._orig_queue = list(tracks)
        # con «Aleatorio» activo, en una lista creada: la pulsada va primero y el resto se baraja
        self._shuffled = self.shuffle_on and self.view.startswith("pl:") and len(tracks) > 1
        if self._shuffled:
            rest = [t for k, t in enumerate(tracks) if k != i]
            random.shuffle(rest)
            self.queue, i = [tracks[i]] + rest, 0
        else:
            self.queue = list(tracks)
        self.play_index(i)

    def play_all(self):
        tr = self.view_tracks()
        if tr:
            shuffle = self.shuffle_on and self.view.startswith("pl:")
            self.play_list(tr, random.randrange(len(tr)) if shuffle else 0)

    def toggle_shuffle(self):
        """Interruptor «Aleatorio»: al activarlo baraja la lista y la reproduce; al desactivarlo vuelve al orden
        original sin cortar la canción que está sonando."""
        self.shuffle_on = not self.shuffle_on
        tr, cur = list(self.view_tracks()), self.cur
        pos = next((k for k, t in enumerate(tr) if cur and t["uri"] == cur["uri"]), None)
        if self.shuffle_on and tr:
            if pos is not None:  # ya hay una de esta lista cargada: sigue con ella y baraja el resto
                self.queue = [tr[pos]] + random.sample(tr[:pos] + tr[pos + 1:], len(tr) - 1)
                self.idx, self._orig_queue, self._shuffled = 0, tr, True
            else:  # empieza por una al azar
                self.play_list(tr, random.randrange(len(tr)))
        elif not self.shuffle_on and self._shuffled:
            orig = self._orig_queue
            self.queue, self._shuffled = list(orig), False
            here = next((k for k, t in enumerate(orig) if cur and t["uri"] == cur["uri"]), None)
            if here is not None:
                self.idx = here  # la siguiente es la que sigue a la actual en el orden original
        self.render()

    def play_index(self, i):
        if 0 <= i < len(self.queue):
            self.idx = i
            self._play(self.queue[i])

    def _play(self, t):
        self._token += 1
        token = self._token
        self.cur = t
        self.player.stop()
        library.push_recent(self.lib, t)
        library.save(self.lib)
        local = self.local_for(t)
        yt = youtube.is_yt(t["uri"]) and not local
        self._preload_token = token if yt else None  # las búsquedas de fondo esperan
        self.show_track()
        self.refresh_playing()
        if local:
            self._start(library.uri_of(local))
            self.prefetch_next()
        elif yt:
            self.t_artist.setText("Cargando canción… 0 %")
            threading.Thread(target=self._resolve, args=(t, token), daemon=True).start()
        else:
            self._start(t["uri"])
            self.prefetch_next()

    def _start(self, uri):
        self.player.load(uri)

    def _resolve(self, t, token):
        """Hilo: descarga la canción ENTERA (con progreso) y solo entonces empieza a sonar, desde disco: sin cortes
        aunque la conexión falle después. Si la descarga falla, plan B: streaming directo."""
        play = None
        try:
            play = library.uri_of(audiocache.fetch(
                t["uri"], on_progress=lambda p: self.bus.call.emit(lambda: self._load_progress(token, p)),
                cancel=lambda: token != self._token))
        except audiocache.Cancelled:
            return  # el usuario cambió de canción: la nueva se encarga
        except Exception:  # noqa: BLE001
            if token == self._token:
                try:
                    play = youtube.stream_url(t["uri"])
                except Exception:  # noqa: BLE001
                    play = None
        finally:
            if self._preload_token == token:
                self._preload_token = None
        self.bus.call.emit(lambda: self._resolved(t, token, play))
        if play and not t.get("cover"):  # la portada llega después: no retrasa el inicio de la canción
            data = youtube.download(t["cover_url"]) if t.get("cover_url") else None
            data = data or youtube.thumbnail(t["uri"])
            path = library.save_cover(data) if data else None
            if path:
                self.bus.call.emit(lambda: self._cover_ready(t, path))

    def _load_progress(self, token, pct):
        if token == self._token:
            self.t_artist.setText(f"Cargando canción… {pct:.0f} %")

    def _resolved(self, t, token, play):
        if token != self._token:
            return
        if play:
            self._start(play)
            self.show_track()
            self.prefetch_next()
        else:
            self.t_artist.setText("No se pudo cargar la canción")
            self.show_state(False)

    def _cover_ready(self, t, path):
        if not t.get("cover"):
            t["cover"] = path
            for lst in (self.lib["tracks"], self.lib["recent"]):
                for x in lst:
                    if x["uri"] == t["uri"] and not x.get("cover"):
                        x["cover"] = path
            library.save(self.lib)
        if self.cur is t:
            self.images.show(self.t_cover, path, 56, 10)

    def prefetch_next(self):
        """Mientras suena la actual, descarga ya la siguiente (cola o lista) para que el cambio sea instantáneo."""
        if self.up_next:
            nxt = self.up_next[0]
        elif self.queue:
            nxt = self.queue[(self.idx + 1) % len(self.queue)]
        else:
            return
        uri = nxt["uri"]
        if not youtube.is_yt(uri) or self.local_for(nxt) or self._prefetch_uri == uri or audiocache.cached(uri):
            return
        self._prefetch_uri, token = uri, self._token

        def work():
            try:
                audiocache.fetch(uri, low_priority=True, cancel=lambda: token != self._token)
            except Exception:  # noqa: BLE001
                pass
            finally:
                if self._prefetch_uri == uri:
                    self._prefetch_uri = None
        threading.Thread(target=work, daemon=True).start()

    def toggle(self):
        if self.cur is None:
            tr = self.view_tracks()
            if tr:
                self.play_list(tr, 0)
            return
        self.player.toggle()

    def stop(self):
        self._token += 1
        self._preload_token = None
        self.player.stop()
        self.cur = None
        self.show_track()
        self.refresh_playing()

    def go_next(self):
        if self.up_next:
            self._play(self.up_next.pop(0))
            if self.view == "queue":
                self.render()
            return
        if self.queue:
            nxt = self.idx + 1
            if nxt >= len(self.queue) and self._shuffled and len(self.queue) > 1:
                last = self.queue[-1]
                random.shuffle(self.queue)
                if self.queue[0] is last:  # que la última no se repita justo al empezar la nueva vuelta
                    self.queue[0], self.queue[-1] = self.queue[-1], self.queue[0]
            self.play_index(nxt % len(self.queue))
            if self.view == "queue":
                self.render()
        else:
            self.stop()

    def go_prev(self):
        if not self.queue or self.player.pos() > 3000:
            self.player.seek(0)
            return
        self.play_index((self.idx - 1) % len(self.queue))

    # ------------------------------------------------------------------ barra de reproducción
    def on_position(self, ms):
        if not self._seeking:
            self.seek.setValue(ms)
            self.l_pos.setText(library.fmt(ms / 1000))

    def on_duration(self, ms):
        if ms > 0:
            self.seek.setRange(0, ms)
            self.l_dur.setText(library.fmt(ms / 1000))

    def _seek_released(self):
        self._seeking = False
        self.player.seek(self.seek.value())

    def on_volume(self, v):
        self.player.set_volume(v)
        self.theme["volume"] = v
        QTimer.singleShot(600, lambda: settings.save(self.theme) if self.theme["volume"] == v else None)

    def on_player_error(self, msg):
        if self.cur:
            self.t_artist.setText("Error de reproducción: " + msg[:80])

    def show_state(self, playing=None):
        playing = self.player.is_playing() if playing is None else playing
        self.b_play.setText("⏸" if playing else "▶")

    def update_heart(self):
        fav = bool(self.cur) and self.is_fav(self.cur)
        self.t_heart.setText("♥" if fav else "♡")
        set_prop(self.t_heart, "on", fav)

    def show_track(self):
        t = self.cur
        if t is None:
            self.t_title.setText("Nada en reproducción")
            self.t_artist.setText("")
            self.images.show(self.t_cover, None, 56, 10)
            self.l_pos.setText("0:00")
            self.l_dur.setText("0:00")
            self.seek.setRange(0, 1)
            self.seek.setValue(0)
            self.setWindowTitle("GlassPlayer")
        else:
            self.t_title.setText(t.get("title") or "")
            self.t_artist.setText(t.get("artist") or "")
            self.images.show(self.t_cover, t.get("cover") or t.get("thumb"), 56, 10)
            self.l_dur.setText(library.fmt(t.get("duration")))
            self.seek.setRange(0, max(1, int((t.get("duration") or 0) * 1000)))
            self.seek.setValue(0)
            self.setWindowTitle(f"♪ {t.get('title')} — {t.get('artist')} · GlassPlayer")
        if self.tray:
            self.tray.setToolTip(self.windowTitle())
        self.update_heart()
        self.show_state()

    # ------------------------------------------------------------------ descargas MP3
    def download_view(self):
        self.download_tracks(self.view_tracks())

    def download_tracks(self, tracks):
        todo = [t for t in tracks if youtube.is_yt(t["uri"]) and not self.local_for(t)]
        if not todo:
            self.flash("No hay nada que descargar")
            return
        if self._dl_busy:
            self.flash("Ya hay una descarga en curso")
            return
        if not downloader.available():
            self.flash("Faltan yt-dlp o ffmpeg: reinstala GlassPlayer")
            return
        self._dl_busy = True
        total = len(todo)

        def work():
            ok, fail, err = 0, 0, ""
            for i, t in enumerate(todo, 1):
                self.bus.call.emit(lambda i=i: self.set_dl_status(f"Descargando {i}/{total}…"))
                try:
                    track = downloader.download_track(t)
                    self.bus.call.emit(lambda t=t, tr=track: self._dl_done(t, tr))
                    ok += 1
                except Exception as e:  # noqa: BLE001
                    fail, err = fail + 1, str(e)
            self.bus.call.emit(lambda: self._dl_finish(ok, fail, err))
        threading.Thread(target=work, daemon=True).start()

    def set_dl_status(self, text):
        self.dl_status = text
        self.refresh_status()

    def _dl_done(self, t, track):
        if not any(x["uri"] == track["uri"] for x in self.lib["tracks"]):
            self.lib["tracks"].append(track)
        lst = self.lib["playlists"].setdefault(library.DOWNLOADS_PLAYLIST, [])
        if track["uri"] not in lst:
            lst.append(track["uri"])
        self.lib["downloads"][t["uri"]] = track["uri"]
        library.save(self.lib)
        self.render_sidebar()

    def _dl_finish(self, ok, fail, err):
        self._dl_busy, self.dl_status = False, ""
        self.render()
        msg = f"{ok} descargadas en «{library.DOWNLOADS_LABEL}»" if ok else ""
        if fail:
            msg += (" · " if msg else "") + f"{fail} con error ({err[:90]})"
        self.flash(msg or "Descarga terminada", 8)

    # ------------------------------------------------------------------ estilo
    def open_style(self):
        StyleDialog(self).exec()


class StyleDialog(QDialog):
    """Paletas predefinidas y colores personalizados."""

    KEYS = (("accent", "Acento"), ("bg_top", "Fondo arriba"), ("bg_bottom", "Fondo abajo"), ("text", "Texto"))

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Estilo")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Paletas", "caption"))
        row = QHBoxLayout()
        for pr in settings.PRESETS:
            b = make_button("", "swatch", lambda p=pr: self.apply_preset(p), pr["name"])
            b.setFixedSize(30, 30)
            b.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {pr['bg_top']}, stop:0.5 {pr['bg_top']},"
                            f" stop:0.5 {pr['accent']}, stop:1 {pr['accent']});")
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(8)
        lay.addWidget(label("Colores personalizados", "caption"))
        self.btns = {}
        for key, text in self.KEYS:
            r = QHBoxLayout()
            r.addWidget(label(text), 1)
            b = make_button("", "swatch", lambda k=key: self.pick(k))
            b.setFixedSize(64, 28)
            self.btns[key] = b
            r.addWidget(b)
            lay.addLayout(r)
        lay.addSpacing(8)
        foot = QHBoxLayout()
        foot.addWidget(make_button("Restablecer", "ghost", self.reset))
        foot.addStretch(1)
        foot.addWidget(make_button("Cerrar", "primary", self.accept))
        lay.addLayout(foot)
        self.sync()

    def sync(self):
        for k, b in self.btns.items():
            b.setStyleSheet(f"background: {self.win.theme[k]};")

    def changed(self):
        settings.save(self.win.theme)
        self.win.apply_theme()
        self.sync()

    def apply_preset(self, pr):
        self.win.theme.update({k: pr[k] for k in settings.COLOR_KEYS})
        self.changed()

    def pick(self, key):
        from PySide6.QtGui import QColor
        c = QColorDialog.getColor(QColor(self.win.theme[key]), self, "Elige un color")
        if c.isValid():
            self.win.theme[key] = c.name()
            self.changed()

    def reset(self):
        self.win.theme.update({k: settings.DEFAULT_THEME[k] for k in settings.COLOR_KEYS})
        self.changed()
