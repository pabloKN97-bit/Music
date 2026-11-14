"""Interfaz GTK4 estilo Apple Music "glass": barra de título, barra lateral, lista y barra de reproducción.
Incluye modo móvil, estilo personalizable, descarga de canciones y control desde la barra superior."""
import os
import subprocess
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gst", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gst, Gtk, Pango

from . import downloader, library, settings, youtube
from .mpris import Mpris
from .style import build_css

V, H = Gtk.Orientation.VERTICAL, Gtk.Orientation.HORIZONTAL
START, CENTER = Gtk.Align.START, Gtk.Align.CENTER
TITLES = {"songs": "Canciones", "favs": "Favoritos", "yt": "YouTube"}
PHONE_W, PHONE_H, PHONE_COVER = 390, 780, 300
COLOR_FIELDS = (("accent", "Color de acento"), ("bg_top", "Fondo (arriba)"),
                ("bg_bottom", "Fondo (abajo)"), ("text", "Texto"))


def label(text="", css=None, **kw):
    l = Gtk.Label(label=text, xalign=0, ellipsize=Pango.EllipsizeMode.END, **kw)
    if css:
        l.add_css_class(css)
    return l


def button(css, cb, icon=None, text=None, tip=None):
    b = Gtk.Button(icon_name=icon) if icon else Gtk.Button(label=text)
    for c in css.split():
        b.add_css_class(c)
    if tip:
        b.set_tooltip_text(tip)
    b.connect("clicked", lambda _b: cb())
    return b


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.pablo.glassplayer")
        Gst.init(None)
        self.lib = library.load()
        self.queue, self.idx, self.playing = [], -1, False
        self.view, self.yt_results, self.yt_status, self.yt_query = "songs", [], "", ""
        self.win = self.mpris = self._dlg = None
        self._token = 0
        # estilo, modo móvil, descargas y bandeja
        self.theme = settings.load()
        self.css = self.phone = self.panel = self.p_bg = self._tray = None
        self.mode = "desktop"
        self._syncing, self._save_id = False, 0
        self.dl_pending, self.dl_status, self._dl_lock = set(), "", threading.Lock()
        self.gst = Gst.ElementFactory.make("playbin", "player")
        bus = self.gst.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", lambda *_: self.go_next())
        bus.connect("message::error", self.on_gst_error)

    # ------------------------------------------------------------ ciclo de vida
    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gtk.Window.set_default_icon_name("com.pablo.glassplayer")
        self.css = Gtk.CssProvider()
        self.apply_css()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css, 800)
        # Acciones para el menú contextual del icono en la barra de tareas (gapplication action ...)
        for name, cb in (("play-pause", self.toggle), ("next", self.go_next), ("prev", self.go_prev), ("quit", self.quit)):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda _a, _p, cb=cb: cb())
            self.add_action(act)

    def do_activate(self):
        if self.win:
            self.show_window()
            return
        self.win = Gtk.ApplicationWindow(application=self, title="GlassPlayer", default_width=1180, default_height=720)
        self.win.connect("close-request", self.on_close)
        self.build()
        self.win.present()
        self.mpris = Mpris(self)
        GLib.timeout_add(500, self.tick)
        self.render_sidebar()
        self.show_track()
        self.start_tray()

    def do_shutdown(self):
        self.gst.set_state(Gst.State.NULL)
        if self._save_id:
            GLib.source_remove(self._save_id)
            self._save_id = 0
            settings.save(self.theme)
        if self._tray and self._tray.poll() is None:
            self._tray.terminate()
        downloader.stop_server()
        Gtk.Application.do_shutdown(self)

    def on_close(self, win):
        """Si está sonando, cerrar la ventana la oculta y la música sigue (controles en el icono de la barra
        de tareas, en la barra superior y en la pantalla de bloqueo). Si no suena, se cierra la aplicación."""
        if self.playing:
            win.set_visible(False)
            return True
        self.quit()  # hay dos ventanas posibles (escritorio y móvil): cerrar una cierra la app
        return False

    def cur_win(self):
        return self.phone if self.mode == "mobile" and self.phone else self.win

    def show_window(self):
        w = self.cur_win()
        w.set_visible(True)
        w.present()

    def start_tray(self):
        """Lanza el icono de la barra superior (proceso aparte, ver tray.py)."""
        if os.environ.get("GLASSPLAYER_NO_TRAY"):
            return
        env = dict(os.environ)
        parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env["PYTHONPATH"] = os.pathsep.join(x for x in (parent, env.get("PYTHONPATH")) if x)
        try:
            self._tray = subprocess.Popen([sys.executable, "-m", "glassplayer.tray"], env=env,
                                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except OSError as e:
            print("GlassPlayer: no se pudo iniciar el icono de la barra superior:", e)

    def on_gst_error(self, _bus, msg):
        print("GStreamer:", msg.parse_error()[0])
        self.playing = False
        self.show_state()

    # ------------------------------------------------------------ construcción de la interfaz
    def build(self):
        w = self.win
        w.add_css_class("glass")
        hb = Gtk.HeaderBar()
        hb.add_css_class("glass-bar")
        hb.pack_start(label("GlassPlayer", "brand"))
        self.search = Gtk.SearchEntry(placeholder_text="Buscar canciones en YouTube…")
        self.search.add_css_class("global-search")
        self.search.connect("activate", lambda e: self.yt_search(e.get_text()))
        hb.set_title_widget(self.search)
        hb.pack_end(button("ibtn", self.add_files, icon="list-add-symbolic", tip="Añadir MP3"))
        hb.pack_end(button("ibtn", self.open_style, icon="applications-graphics-symbolic", tip="Personalizar estilo"))
        hb.pack_end(button("ibtn", lambda: self.set_mode("mobile"), icon="phone-symbolic", tip="Modo móvil"))
        w.set_titlebar(hb)

        ov = Gtk.Overlay()
        self.bg = Gtk.Picture(opacity=0.55)
        self.bg.set_keep_aspect_ratio(False)
        ov.set_child(self.bg)
        shell = Gtk.Box(orientation=V)
        shell.add_css_class("shell")
        ov.add_overlay(shell)
        w.set_child(ov)

        mid = Gtk.Box(vexpand=True)
        self.side_box = Gtk.Box(orientation=V, spacing=2, width_request=260)
        self.side_box.add_css_class("side")
        mid.append(self.side_box)
        main = Gtk.Box(orientation=V, spacing=8, hexpand=True)
        main.add_css_class("main")
        mid.append(main)
        shell.append(mid)

        head = Gtk.Box(spacing=12)
        titles = Gtk.Box(orientation=V, hexpand=True, valign=CENTER)
        self.l_crumb, self.l_page = label("", "crumb"), label("", "page-title")
        titles.append(self.l_crumb)
        titles.append(self.l_page)
        self.btn_all = button("btn-primary", self.play_all, text="▶  Reproducir")
        self.btn_all.set_valign(CENTER)
        self.btn_dl = button("btn-ghost", self.download_view, text="⬇  Descargar")
        self.btn_dl.set_valign(CENTER)
        head.append(titles)
        head.append(self.btn_dl)
        head.append(self.btn_all)
        self.l_status = label("", "sub")
        self.lst = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.lst.connect("row-activated", lambda _l, row: self.play_list(self.view_tracks(), row.get_index()))
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.lst)
        for x in (head, self.l_status, sc):
            main.append(x)
        shell.append(self.build_transport())

    def build_transport(self):
        t = Gtk.Box(spacing=18)
        t.add_css_class("transport")
        left = Gtk.Box(spacing=12, width_request=300)
        self.t_cover = self.thumb(None, 54)
        self.t_cover.set_tooltip_text("Clic para cambiar la portada")
        g = Gtk.GestureClick()
        g.connect("released", lambda *_: self.pick_image())
        self.t_cover.add_controller(g)
        info = Gtk.Box(orientation=V, valign=CENTER, hexpand=True)
        self.l_title, self.l_artist = label("GlassPlayer", "nm", max_width_chars=24), label("", "sub", max_width_chars=26)
        info.append(self.l_title)
        info.append(self.l_artist)
        self.t_heart = button("heart", lambda: self.toggle_fav(self.current()), icon="emblem-favorite-symbolic", tip="Favorito")
        self.t_dl = Gtk.Button()
        self.t_dl.add_css_class("ibtn")
        self.t_dl.connect("clicked", lambda _b: self.current() and self.download_tracks([self.current()]))
        for x in (self.t_cover, info, self.t_heart, self.t_dl):
            left.append(x)

        center = Gtk.Box(orientation=V, spacing=4, hexpand=True, valign=CENTER)
        ctr = Gtk.Box(spacing=14, halign=CENTER)
        ctr.append(button("cbtn", self.go_prev, icon="media-skip-backward-symbolic"))
        self.btn_play = button("play", self.toggle, icon="media-playback-start-symbolic")
        ctr.append(self.btn_play)
        ctr.append(button("cbtn", self.go_next, icon="media-skip-forward-symbolic"))
        scrub = Gtk.Box(spacing=10)
        self.l_pos, self.l_dur = label("0:00", "sub"), label("0:00", "sub")
        self.scale = Gtk.Scale.new_with_range(H, 0, 100, 1)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.connect("change-value", self.on_seek)
        for x in (self.l_pos, self.scale, self.l_dur):
            scrub.append(x)
        center.append(ctr)
        center.append(scrub)

        right = Gtk.Box(spacing=8, width_request=240, halign=Gtk.Align.END, valign=CENTER)
        vol = Gtk.Scale.new_with_range(H, 0, 1, 0.05)
        vol.set_value(1.0)
        vol.set_draw_value(False)
        vol.set_size_request(120, -1)
        vol.connect("value-changed", lambda s: self.gst.set_property("volume", s.get_value()))
        right.append(Gtk.Image(icon_name="audio-volume-high-symbolic"))
        right.append(vol)
        for x in (left, center, right):
            t.append(x)
        return t

    # ------------------------------------------------------------ utilidades de imagen
    def set_pic(self, pic, path, size):
        pic.set_paintable(None)
        if path and os.path.exists(path):
            try:
                pic.set_paintable(Gdk.Texture.new_for_pixbuf(
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size * 2, size * 2, True)))
            except Exception:
                pass

    def thumb(self, path, size):
        p = Gtk.Picture(halign=START, valign=CENTER)
        p.set_can_shrink(True)
        p.set_size_request(size, size)
        p.add_css_class("cv")
        self.set_pic(p, path, size)
        return p

    def async_thumb(self, pic, url):
        def work():
            d = youtube.download(url)
            if d:
                GLib.idle_add(self._set_tex, pic, d)
        threading.Thread(target=work, daemon=True).start()

    def _set_tex(self, pic, data):
        try:
            ld = GdkPixbuf.PixbufLoader()
            ld.write(data)
            ld.close()
            pic.set_paintable(Gdk.Texture.new_for_pixbuf(ld.get_pixbuf()))
        except Exception:
            pass

    @staticmethod
    def clear(box):
        while (c := box.get_first_child()):
            box.remove(c)

    # ------------------------------------------------------------ barra lateral y vistas
    def nav_item(self, key, icon, text):
        b = Gtk.Button()
        box = Gtk.Box(spacing=10)
        box.append(Gtk.Image(icon_name=icon))
        box.append(label(text, hexpand=True))
        b.set_child(box)
        b.add_css_class("side-item")
        if key == self.view:
            b.add_css_class("on")
        b.connect("clicked", lambda _b: self.set_view(key))
        return b

    def render_sidebar(self):
        self.clear(self.side_box)
        sb = self.side_box
        sb.append(label("BIBLIOTECA", "side-title"))
        for key, icon in (("songs", "audio-x-generic-symbolic"), ("favs", "emblem-favorite-symbolic"), ("yt", "web-browser-symbolic")):
            sb.append(self.nav_item(key, icon, TITLES[key]))
        sb.append(label("LISTAS", "side-title"))
        for name in self.lib["playlists"]:
            row = Gtk.Box()
            fixed = name == library.DOWNLOADS_PLAYLIST  # lista de descargas: siempre existe
            item = self.nav_item("pl:" + name, "folder-download-symbolic" if fixed else "view-list-symbolic", name)
            item.set_hexpand(True)
            row.append(item)
            if not fixed:
                row.append(button("ibtn", lambda n=name: self.delete_playlist(n), icon="user-trash-symbolic", tip="Eliminar lista"))
            sb.append(row)
        self.new_pl = Gtk.Entry(placeholder_text="＋ Nueva lista…")
        self.new_pl.add_css_class("new-list")
        self.new_pl.connect("activate", lambda e: self.create_playlist(e.get_text()))
        sb.append(self.new_pl)

    def set_view(self, key):
        self.view = key
        self.render_sidebar()
        self.render_main()

    def view_tracks(self):
        if self.view == "songs":
            return self.lib["tracks"]
        if self.view == "favs":
            return [t for t in self.lib["tracks"] if t["uri"] in self.lib["favorites"]]
        if self.view == "yt":
            return self.yt_results
        by = {t["uri"]: t for t in self.lib["tracks"]}
        return [by[u] for u in self.lib["playlists"].get(self.view[3:], []) if u in by]

    def render_main(self):
        tr = self.view_tracks()
        if self.view.startswith("pl:"):
            self.l_page.set_label(self.view[3:])
            self.l_crumb.set_label("LISTA")
        else:
            self.l_page.set_label(TITLES[self.view])
            self.l_crumb.set_label(f"RESULTADOS DE «{self.yt_query.upper()}»" if self.view == "yt" and self.yt_query else "BIBLIOTECA")
        self.refresh_status()
        self.btn_all.set_visible(bool(tr))
        todo = [t for t in tr if self.dl_state(t) == "todo"]
        self.btn_dl.set_visible(bool(todo))
        self.btn_dl.set_label(f"⬇  Descargar ({len(todo)})" if len(todo) > 1 else "⬇  Descargar")
        self.clear(self.lst)
        cur = self.current()
        for i, t in enumerate(tr):
            self.lst.append(self.make_row(t, i, bool(cur) and cur["uri"] == t["uri"]))

    def status_text(self):
        if self.dl_status:
            return self.dl_status
        tr = self.view_tracks()
        if self.view == "yt":
            return self.yt_status or ("" if tr else "Escribe en la barra superior y pulsa Intro para buscar en YouTube")
        return "" if tr else "Aún no hay canciones aquí"

    def refresh_status(self):
        self.l_status.set_label(self.status_text())

    def make_row(self, t, i, playing):
        row = Gtk.Box(spacing=12)
        row.add_css_class("row-item")
        if playing:
            row.add_css_class("playing")
        th = self.thumb(t.get("cover"), 40)
        if not t.get("cover") and t.get("thumb"):
            self.async_thumb(th, t["thumb"])
        col = Gtk.Box(orientation=V, hexpand=True, valign=CENTER)
        col.append(label(t["title"], "nm"))
        col.append(label(t["artist"], "sub"))
        heart = Gtk.Button(icon_name="emblem-favorite-symbolic")
        heart.add_css_class("heart")
        if t["uri"] in self.lib["favorites"]:
            heart.add_css_class("on")
        heart.connect("clicked", lambda _b: self.toggle_fav(t))
        cells = [label("▶" if playing else str(i + 1), "num", width_chars=3), th, col, heart]
        if youtube.is_yt(t["uri"]):
            cells.append(self.dl_button(t))
        cells += [self.row_menu(t), label(library.fmt(t["duration"]), "sub", width_chars=5)]
        for x in cells:
            row.append(x)
        return row

    def dl_button(self, t):
        b = Gtk.Button()
        b.add_css_class("ibtn")
        self.style_dl_button(b, self.dl_state(t))
        b.connect("clicked", lambda _b: self.download_tracks([t]))
        return b

    @staticmethod
    def style_dl_button(b, state):
        icon, tip = {
            "todo": ("folder-download-symbolic", "Descargar MP3 (se añade a DescargadasSinConexion)"),
            "busy": ("content-loading-symbolic", "Descargando…"),
            "done": ("object-select-symbolic", "Descargada: disponible sin conexión"),
        }.get(state, ("folder-download-symbolic", ""))
        b.set_icon_name(icon)
        b.set_tooltip_text(tip)
        b.set_sensitive(state == "todo")
        b.set_visible(state is not None)

    def row_menu(self, t):
        mb = Gtk.MenuButton(icon_name="view-more-symbolic")
        mb.add_css_class("ibtn")
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=V, spacing=2)

        def item(text, cb):
            b = Gtk.Button(label=text)
            b.add_css_class("menu-item")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b: (pop.popdown(), cb()))
            box.append(b)
        in_lib = any(x["uri"] == t["uri"] for x in self.lib["tracks"])
        if self.dl_state(t) == "todo":
            item("Descargar MP3", lambda: self.download_tracks([t]))
        if not in_lib:
            item("Añadir a la biblioteca", lambda: self.add_to_library(t, commit=True))
        for name in self.lib["playlists"]:
            item(f"Añadir a «{name}»", lambda n=name: self.add_to_playlist(n, t))
        if self.view.startswith("pl:"):
            item("Quitar de esta lista", lambda: self.remove_from_playlist(self.view[3:], t))
        if in_lib:
            item("Eliminar de la biblioteca", lambda: self.remove_track(t))
        pop.set_child(box)
        mb.set_popover(pop)
        return mb

    # ------------------------------------------------------------ biblioteca, listas y favoritos
    def commit(self, sidebar=False):
        library.save(self.lib)
        if sidebar:
            self.render_sidebar()
        self.render_main()
        self.update_heart()
        self.update_dl_button()

    def add_to_library(self, t, commit=False):
        if not any(x["uri"] == t["uri"] for x in self.lib["tracks"]):
            self.lib["tracks"].append(dict(t))
        if commit:
            self.commit()

    def add_tracks(self, new):
        for t in new:
            self.add_to_library(t)
        self.commit()

    def toggle_fav(self, t):
        if not t:
            return
        self.add_to_library(t)
        fav = self.lib["favorites"]
        fav.remove(t["uri"]) if t["uri"] in fav else fav.append(t["uri"])
        self.commit()

    def create_playlist(self, name):
        name = name.strip()
        if name and name not in self.lib["playlists"]:
            self.lib["playlists"][name] = []
            library.save(self.lib)
            self.set_view("pl:" + name)

    def delete_playlist(self, name):
        if name == library.DOWNLOADS_PLAYLIST:
            return
        self.lib["playlists"].pop(name, None)
        if self.view == "pl:" + name:
            self.view = "songs"
        self.commit(sidebar=True)

    def add_to_playlist(self, name, t):
        self.add_to_library(t)
        if t["uri"] not in self.lib["playlists"][name]:
            self.lib["playlists"][name].append(t["uri"])
        self.commit()

    def remove_from_playlist(self, name, t):
        if t["uri"] in self.lib["playlists"].get(name, []):
            self.lib["playlists"][name].remove(t["uri"])
        self.commit()

    def remove_track(self, t):
        uri = t["uri"]
        cur = self.current()
        self.lib["tracks"] = [x for x in self.lib["tracks"] if x["uri"] != uri]
        if uri in self.lib["favorites"]:
            self.lib["favorites"].remove(uri)
        # si era una descarga, el enlace de YouTube vuelve a poder descargarse (el archivo no se borra)
        self.lib["downloads"] = {k: v for k, v in self.lib["downloads"].items() if v != uri}
        for lst in self.lib["playlists"].values():
            while uri in lst:
                lst.remove(uri)
        if cur and cur["uri"] == uri:
            self.stop()
            self.queue, self.idx = [], -1
            self.show_track()
        library.drop_cover(t.get("cover"), self.lib["tracks"] + self.queue)
        self.commit()

    def add_files(self):
        d = Gtk.FileChooserNative.new("Añadir MP3", self.win, Gtk.FileChooserAction.OPEN, "Añadir", "Cancelar")
        d.set_select_multiple(True)
        f = Gtk.FileFilter()
        f.set_name("MP3")
        f.add_mime_type("audio/mpeg")
        f.add_suffix("mp3")
        d.add_filter(f)

        def done(dlg, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                fl = dlg.get_files()
                paths = [fl.get_item(i).get_path() for i in range(fl.get_n_items())]
                threading.Thread(target=lambda: GLib.idle_add(
                    self.add_tracks, [library.read_track(p) for p in paths]), daemon=True).start()
        d.connect("response", done)
        self._dlg = d
        d.show()

    # ------------------------------------------------------------ portadas
    def pick_image(self):
        if not self.current():
            return
        d = Gtk.FileChooserNative.new("Elegir portada", self.win, Gtk.FileChooserAction.OPEN, "Elegir", "Cancelar")
        f = Gtk.FileFilter()
        f.set_name("Imágenes")
        f.add_pixbuf_formats()
        d.add_filter(f)

        def done(dlg, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                with open(dlg.get_file().get_path(), "rb") as fh:
                    self.apply_cover(fh.read())
        d.connect("response", done)
        self._dlg = d
        d.show()

    def apply_cover(self, data):
        t = self.current()
        path = library.save_cover(data) if t else None
        if path:
            old, t["cover"] = t.get("cover"), path
            for x in self.lib["tracks"]:  # la copia de la biblioteca también
                if x["uri"] == t["uri"]:
                    x["cover"] = path
            library.drop_cover(old, self.lib["tracks"] + self.queue)
            self.show_track()
            library.save(self.lib)

    # ------------------------------------------------------------ YouTube
    def yt_search(self, q):
        q = q.strip()
        if not q:
            return
        self.yt_query, self.yt_results = q, []
        if not youtube.available():
            self.yt_status = "Falta yt-dlp: ejecuta ./install.sh"
            self.set_view("yt")
            return
        self.yt_status = f"Buscando «{q}» en YouTube…"
        self.set_view("yt")

        def work():
            try:
                res = youtube.search(q)
            except Exception:
                res = None
            GLib.idle_add(self._yt_done, q, res)
        threading.Thread(target=work, daemon=True).start()

    def _yt_done(self, q, res):
        if q != self.yt_query:
            return
        if res is None:
            self.yt_status = "No se pudo buscar (sin conexión o yt-dlp desactualizado: ejecuta 'yt-dlp -U')"
        else:
            self.yt_results, self.yt_status = res, "" if res else "Sin resultados"
        self.render_main()

    # ------------------------------------------------------------ reproducción
    def current(self):
        return self.queue[self.idx] if 0 <= self.idx < len(self.queue) else None

    def position_us(self):
        ok, pos = self.gst.query_position(Gst.Format.TIME)
        return pos // 1000 if ok else 0

    def play_list(self, tracks, i):
        self.queue = list(tracks)
        self.play_index(i)

    def play_all(self):
        tr = self.view_tracks()
        if tr:
            self.play_list(tr, 0)

    def play_index(self, i):
        if not (0 <= i < len(self.queue)):
            return
        self.idx, self.playing = i, True
        self._token += 1
        t = self.queue[i]
        self.gst.set_state(Gst.State.NULL)
        self.show_track()
        if youtube.is_yt(t["uri"]):
            self.set_subtitle("Cargando desde YouTube…")
            threading.Thread(target=self._resolve, args=(t, self._token), daemon=True).start()
        else:
            self._start(t["uri"])

    def _start(self, uri):
        self.gst.set_property("uri", uri)
        self.gst.set_state(Gst.State.PLAYING)

    def _resolve(self, t, token):
        """Hilo: obtiene la URL de audio y, si falta, la portada (miniatura del vídeo)."""
        try:
            url = youtube.stream_url(t["uri"])
        except Exception:
            url = None
        path = None
        if url and not t.get("cover"):
            data = youtube.thumbnail(t["uri"])
            path = library.save_cover(data) if data else None
        GLib.idle_add(self._resolved, t, token, url, path)

    def _resolved(self, t, token, url, path):
        if path and not t.get("cover"):
            t["cover"] = path
            for x in self.lib["tracks"]:
                if x["uri"] == t["uri"]:
                    x["cover"] = path
            library.save(self.lib)
        if token != self._token:
            return
        if url:
            self._start(url)
        else:
            self.playing = False
        self.show_track()
        if not url:
            self.set_subtitle("No se pudo cargar (actualiza yt-dlp: 'yt-dlp -U')")

    def toggle(self):
        if not self.current():
            if self.lib["tracks"]:
                self.play_list(self.lib["tracks"], 0)
            return
        self.playing = not self.playing
        self.gst.set_state(Gst.State.PLAYING if self.playing else Gst.State.PAUSED)
        self.show_state()

    def stop(self):
        self.gst.set_state(Gst.State.NULL)
        self.playing = False
        self.show_state()

    def go_next(self):
        if self.queue:
            self.play_index((self.idx + 1) % len(self.queue))

    def go_prev(self):
        if self.queue:
            self.play_index((self.idx - 1) % len(self.queue))

    def on_seek(self, _scale, _scroll, value):
        self.gst.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, int(value * Gst.SECOND))
        return False

    def seek_rel(self, offset_us):
        self.gst.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, max(0, self.position_us() + offset_us) * 1000)

    # ------------------------------------------------------------ estado en pantalla
    def update_heart(self):
        t = self.current()
        if t and t["uri"] in self.lib["favorites"]:
            self.t_heart.add_css_class("on")
        else:
            self.t_heart.remove_css_class("on")

    def show_track(self):
        t = self.current()
        self.l_title.set_label(t["title"] if t else "GlassPlayer")
        self.l_artist.set_label(t["artist"] if t else "Elige una canción")
        dur = t["duration"] if t else 0
        self.scale.set_range(0, max(1, dur))
        self.scale.set_value(0)
        self.l_pos.set_label("0:00")
        self.l_dur.set_label(library.fmt(dur))
        path = t.get("cover") if t else None
        self.set_pic(self.t_cover, path, 54)
        self.update_bg()
        self.update_phone()
        self.update_heart()
        self.render_main()
        self.show_state()

    def set_subtitle(self, text):
        self.l_artist.set_label(text)
        if self.phone:
            self.p_artist.set_label(text)

    def show_state(self):
        icon = "media-playback-pause-symbolic" if self.playing else "media-playback-start-symbolic"
        self.btn_play.set_icon_name(icon)
        if self.phone:
            self.p_play.set_icon_name(icon)
        if self.mpris:
            self.mpris.notify()

    def update_dl_button(self):
        t = self.current()
        state = self.dl_state(t) if t else None
        self.style_dl_button(self.t_dl, state)
        if state is None:
            self.t_dl.set_visible(False)

    def tick(self):
        t = self.current()
        if t:
            ok, pos = self.gst.query_position(Gst.Format.TIME)
            if ok:
                self.scale.set_value(pos / Gst.SECOND)
                self.l_pos.set_label(library.fmt(pos / Gst.SECOND))
            if t["duration"] <= 0:
                ok, d = self.gst.query_duration(Gst.Format.TIME)
                if ok and d > 0:
                    t["duration"] = d / Gst.SECOND
                    self.scale.set_range(0, t["duration"])
                    self.l_dur.set_label(library.fmt(t["duration"]))
        return True

    # ------------------------------------------------------------ tema: paleta, fondo y transparencia
    def apply_css(self):
        css = build_css(self.theme)
        if hasattr(self.css, "load_from_string"):
            self.css.load_from_string(css)
        else:
            self.css.load_from_data(css.encode())

    def bg_pictures(self):
        return [p for p in (self.bg, self.p_bg) if p is not None]

    def apply_opacity(self):
        """La transparencia afecta a fondos y capas (el texto se mantiene legible)."""
        op = 1 - self.theme["transparency"] / 100
        base = 0.9 if self.theme.get("bg_image") else 0.55
        for pic in self.bg_pictures():
            pic.set_opacity(base * op)

    def update_bg(self):
        """Fondo: la imagen elegida por el usuario o, si no hay, la portada de la canción desenfocada."""
        tex, cover_fit = None, False
        custom = self.theme.get("bg_image")
        if custom and os.path.exists(custom):
            try:
                tex = Gdk.Texture.new_for_pixbuf(GdkPixbuf.Pixbuf.new_from_file(custom))
                cover_fit = True
            except Exception:
                tex = None
        if tex is None:
            t = self.current()
            path = t.get("cover") if t else None
            if path and os.path.exists(path):
                try:
                    tex = Gdk.Texture.new_for_pixbuf(library.blur(GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 400, 400, True)))
                except Exception:
                    pass
        for pic in self.bg_pictures():
            pic.set_paintable(tex)
            if hasattr(pic, "set_content_fit"):
                pic.set_content_fit(Gtk.ContentFit.COVER if cover_fit else Gtk.ContentFit.FILL)
            else:
                pic.set_keep_aspect_ratio(cover_fit)
        self.apply_opacity()

    def theme_changed(self):
        self.apply_css()
        self.apply_opacity()
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(300, self._flush_theme)

    def _flush_theme(self):
        self._save_id = 0
        settings.save(self.theme)
        return False

    # ------------------------------------------------------------ panel «Personalizar estilo»
    def open_style(self):
        if not self.panel:
            self.build_style_panel()
        self.panel.set_transient_for(self.cur_win())
        self.panel.present()

    def build_style_panel(self):
        p = Gtk.Window(title="Personalizar estilo", hide_on_close=True, resizable=False, default_width=380)
        p.add_css_class("style-panel")
        box = Gtk.Box(orientation=V, spacing=12, margin_top=18, margin_bottom=18, margin_start=22, margin_end=22)
        p.set_child(box)
        box.append(label("Personalizar estilo", "panel-h"))

        box.append(label("PALETAS", "panel-sec"))
        sw = Gtk.Box(spacing=10)
        for i, pr in enumerate(settings.PRESETS):
            b = Gtk.Button()
            b.add_css_class("swatch")
            b.add_css_class(f"sw{i}")
            b.set_tooltip_text(pr["name"])
            b.connect("clicked", lambda _b, pr=pr: self.apply_preset(pr))
            sw.append(b)
        box.append(sw)

        box.append(label("COLORES", "panel-sec"))
        self.pickers = {}
        for key, text in COLOR_FIELDS:
            row = Gtk.Box(spacing=10)
            row.append(label(text, hexpand=True))
            self.pickers[key] = self.color_button(key)
            row.append(self.pickers[key])
            box.append(row)

        box.append(label("FONDO", "panel-sec"))
        row = Gtk.Box(spacing=8)
        row.append(button("panel-btn", self.pick_background, text="Elegir imagen…"))
        row.append(button("panel-btn", self.clear_background, text="Quitar imagen"))
        box.append(row)
        self.l_bgfile = label("", "panel-hint")
        box.append(self.l_bgfile)

        box.append(label("TRANSPARENCIA", "panel-sec"))
        trow = Gtk.Box(spacing=10)
        self.tr_scale = Gtk.Scale.new_with_range(H, 0, 90, 1)
        self.tr_scale.set_draw_value(False)
        self.tr_scale.set_hexpand(True)
        self.tr_scale.set_value(self.theme["transparency"])
        self.tr_scale.connect("value-changed", self.on_transparency)
        self.l_tr = label("", "sub", width_chars=5)
        trow.append(self.tr_scale)
        trow.append(self.l_tr)
        box.append(trow)
        hint = label("Con más transparencia se ven las ventanas que hay detrás (necesita un escritorio con composición, como GNOME o KDE).", "panel-hint")
        hint.set_wrap(True)
        hint.set_ellipsize(Pango.EllipsizeMode.NONE)
        box.append(hint)

        foot = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=6)
        foot.append(button("panel-btn", self.reset_theme, text="Restablecer"))
        foot.append(button("panel-btn", lambda: p.set_visible(False), text="Cerrar"))
        box.append(foot)
        self.panel = p
        self.sync_panel()

    def color_button(self, key):
        rgba = Gdk.RGBA()
        rgba.parse(self.theme[key])
        if hasattr(Gtk, "ColorDialogButton"):  # GTK 4.10+
            dlg = Gtk.ColorDialog()
            dlg.set_with_alpha(False)
            btn = Gtk.ColorDialogButton(dialog=dlg)
            btn.set_rgba(rgba)
        else:
            btn = Gtk.ColorButton.new_with_rgba(rgba)
            btn.set_use_alpha(False)
        btn.connect("notify::rgba", lambda b, _p, k=key: self.on_color(k, b.get_rgba()))
        return btn

    def on_color(self, key, rgba):
        if self._syncing:
            return
        self.theme[key] = "#%02x%02x%02x" % tuple(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue))
        self.theme_changed()

    def apply_preset(self, pr):
        for k in settings.COLOR_KEYS:
            self.theme[k] = pr[k]
        self.sync_panel()
        self.theme_changed()

    def on_transparency(self, scale):
        if self._syncing:
            return
        self.theme["transparency"] = int(scale.get_value())
        self.l_tr.set_label(f"{self.theme['transparency']} %")
        self.theme_changed()

    def sync_panel(self):
        """Refleja el tema actual en los controles del panel sin disparar sus señales."""
        self._syncing = True
        for key, btn in self.pickers.items():
            rgba = Gdk.RGBA()
            rgba.parse(self.theme[key])
            btn.set_rgba(rgba)
        self.tr_scale.set_value(self.theme["transparency"])
        self.l_tr.set_label(f"{self.theme['transparency']} %")
        img = self.theme.get("bg_image")
        self.l_bgfile.set_label("Imagen de fondo personalizada" if img else "Sin imagen: se usa la portada de la canción")
        self._syncing = False

    def pick_background(self):
        d = Gtk.FileChooserNative.new("Elegir fondo", self.panel, Gtk.FileChooserAction.OPEN, "Elegir", "Cancelar")
        f = Gtk.FileFilter()
        f.set_name("Imágenes")
        f.add_pixbuf_formats()
        d.add_filter(f)

        def done(dlg, resp):
            if resp != Gtk.ResponseType.ACCEPT:
                return
            path = library.save_background(dlg.get_file().get_path())
            if path:
                library.drop_background(self.theme.get("bg_image"))
                self.theme["bg_image"] = path
                self.update_bg()
                self.sync_panel()
                self.theme_changed()
            else:
                self.l_bgfile.set_label("No se pudo leer esa imagen")
        d.connect("response", done)
        self._dlg = d
        d.show()

    def clear_background(self):
        library.drop_background(self.theme.get("bg_image"))
        self.theme["bg_image"] = None
        self.update_bg()
        self.sync_panel()
        self.theme_changed()

    def reset_theme(self):
        library.drop_background(self.theme.get("bg_image"))
        self.theme = dict(settings.DEFAULT_THEME)
        self.update_bg()
        self.sync_panel()
        self.theme_changed()

    # ------------------------------------------------------------ modo móvil
    def set_mode(self, mode):
        if mode == "mobile":
            if not self.phone:
                self.build_phone()
            self.mode = "mobile"
            self.win.set_visible(False)
            self.phone.present()
        else:
            self.mode = "desktop"
            if self.phone:
                self.phone.set_visible(False)
            self.win.present()
        if self.panel and self.panel.get_visible():
            self.panel.set_transient_for(self.cur_win())

    def build_phone(self):
        """Ventana con forma de teléfono: portada, título y Anterior / Pausa / Siguiente."""
        w = Gtk.Window(application=self, title="GlassPlayer", decorated=False, resizable=False,
                       default_width=PHONE_W, default_height=PHONE_H)
        w.add_css_class("phone-win")
        w.connect("close-request", self.on_close)
        ov = Gtk.Overlay()
        ov.add_css_class("phone")
        ov.set_overflow(Gtk.Overflow.HIDDEN)  # recorta el fondo a las esquinas redondeadas del «teléfono»
        self.p_bg = Gtk.Picture(opacity=0.55)
        self.p_bg.set_keep_aspect_ratio(False)
        ov.set_child(self.p_bg)
        col = Gtk.Box(orientation=V, spacing=10, margin_top=12, margin_bottom=14, margin_start=20, margin_end=20)
        ov.add_overlay(col)

        top = Gtk.CenterBox()
        notch = Gtk.Box(valign=CENTER)
        notch.add_css_class("notch")
        top.set_center_widget(notch)
        back = Gtk.Button()
        back.add_css_class("back-desktop")
        back.set_tooltip_text("Volver al modo escritorio")
        bx = Gtk.Box(spacing=6)
        bx.append(Gtk.Image(icon_name="computer-symbolic"))
        bx.append(Gtk.Label(label="Escritorio"))
        back.set_child(bx)
        back.connect("clicked", lambda _b: self.set_mode("desktop"))
        top.set_end_widget(back)
        col.append(top)

        col.append(Gtk.Box(vexpand=True))
        self.p_cover = self.thumb(None, PHONE_COVER)
        self.p_cover.set_halign(CENTER)
        self.p_cover.add_css_class("p-cover")
        self.p_cover.set_overflow(Gtk.Overflow.HIDDEN)
        col.append(self.p_cover)
        self.p_title = Gtk.Label(label="GlassPlayer", ellipsize=Pango.EllipsizeMode.END, max_width_chars=24, margin_top=10)
        self.p_title.add_css_class("p-title")
        self.p_artist = Gtk.Label(label="", ellipsize=Pango.EllipsizeMode.END, max_width_chars=30)
        self.p_artist.add_css_class("p-artist")
        col.append(self.p_title)
        col.append(self.p_artist)
        col.append(Gtk.Box(vexpand=True))

        ctr = Gtk.Box(spacing=22, halign=CENTER)
        ctr.append(button("cbtn p-ctl", self.go_prev, icon="media-skip-backward-symbolic", tip="Anterior"))
        self.p_play = button("play p-play", self.toggle, icon="media-playback-start-symbolic", tip="Reproducir / Pausa")
        ctr.append(self.p_play)
        ctr.append(button("cbtn p-ctl", self.go_next, icon="media-skip-forward-symbolic", tip="Siguiente"))
        col.append(ctr)
        col.append(Gtk.Box(vexpand=True))
        home = Gtk.Box(halign=CENTER)
        home.add_css_class("home-bar")
        col.append(home)

        handle = Gtk.WindowHandle()  # arrastrar la ventana desde cualquier zona libre
        handle.set_child(ov)
        w.set_child(handle)
        self.phone = w
        self.update_bg()
        self.update_phone()
        self.show_state()

    def update_phone(self):
        if not self.phone:
            return
        t = self.current()
        self.p_title.set_label(t["title"] if t else "GlassPlayer")
        self.p_artist.set_label(t["artist"] if t else "Elige una canción")
        self.set_pic(self.p_cover, t.get("cover") if t else None, PHONE_COVER)

    # ------------------------------------------------------------ descargas (convertidor.py)
    def dl_state(self, t):
        """None si no es de YouTube; si lo es: 'todo', 'busy' o 'done' (ya hay un MP3 local)."""
        if not youtube.is_yt(t["uri"]):
            return None
        if t["uri"] in self.dl_pending:
            return "busy"
        f = self.lib["downloads"].get(t["uri"])
        if f and Gio.File.new_for_uri(f).query_exists(None):
            return "done"
        return "todo"

    def set_dl_status(self, text):
        self.dl_status = text
        self.refresh_status()

    def download_view(self):
        self.download_tracks(self.view_tracks())

    def download_tracks(self, tracks):
        if not downloader.available():
            self.set_dl_status("Falta el convertidor (flask / yt-dlp): ejecuta ./install.sh")
            return
        todo = [t for t in tracks if self.dl_state(t) == "todo"]
        if not todo:
            return
        self.dl_pending.update(t["uri"] for t in todo)
        self.set_dl_status(f"Descargando 0/{len(todo)}…")
        self.render_main()
        self.update_dl_button()
        threading.Thread(target=self._dl_run, args=(todo,), daemon=True).start()

    def _dl_run(self, todo):
        """Hilo: una descarga detrás de otra (extraer enlace -> convertidor.py -> MP3 etiquetado)."""
        ok, fail, last_err = 0, 0, ""
        with self._dl_lock:
            for n, t in enumerate(todo, 1):
                GLib.idle_add(self.set_dl_status, f"Descargando {n}/{len(todo)}: {t['title']}")
                try:
                    track, err = downloader.download_track(t), None
                except Exception as e:  # DownloadError u otros: se informa y se sigue con la siguiente
                    track, err = None, str(e)
                ok, fail = ok + (track is not None), fail + (track is None)
                last_err = err or last_err
                GLib.idle_add(self._dl_done, t, track)
        GLib.idle_add(self._dl_finish, ok, fail, last_err)

    def _dl_done(self, t, track):
        self.dl_pending.discard(t["uri"])
        if track:
            self.add_to_library(track)
            self.lib["downloads"][t["uri"]] = track["uri"]
            pl = self.lib["playlists"].setdefault(library.DOWNLOADS_PLAYLIST, [])
            if track["uri"] not in pl:
                pl.append(track["uri"])
        self.commit()

    def _dl_finish(self, ok, fail, err):
        msg = f"{ok} descargada{'s' if ok != 1 else ''} en «{library.DOWNLOADS_PLAYLIST}»" if ok else "No se descargó nada"
        if fail:
            msg += f" · {fail} con error: {err[:140]}"
        self.set_dl_status(msg)
        GLib.timeout_add_seconds(12, self._dl_clear, msg)

    def _dl_clear(self, msg):
        if self.dl_status == msg and not self.dl_pending:
            self.set_dl_status("")
        return False
