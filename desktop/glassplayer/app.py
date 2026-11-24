"""Interfaz GTK4 estilo Apple Music "glass": barra de título, barra lateral, lista y barra de reproducción.
Incluye modo móvil, estilo personalizable, descarga de canciones y control desde la barra superior."""
import os
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gst", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gst, Gtk, Pango

from . import audiocache, downloader, library, news, settings, youtube
from .mpris import Mpris
from .style import build_css

V, H = Gtk.Orientation.VERTICAL, Gtk.Orientation.HORIZONTAL
START, CENTER = Gtk.Align.START, Gtk.Align.CENTER
TITLES = {"recent": "Recientes", "songs": "Canciones", "favs": "Favoritos", "news": "Novedades", "yt": "YouTube",
          "queue": "Cola"}
QUEUE_REST_MAX = 200  # canciones «a continuación» que se listan en la vista Cola
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
        # Lista que se está reproduciendo (queue + idx) y «cola» del usuario (up_next): la cola tiene prioridad
        # y al acabarse la lista sigue por donde iba, como en Spotify. _cur es la pista que suena ahora.
        self.queue, self.idx, self.playing = [], -1, False
        self.up_next, self._cur, self._qrows = [], None, []
        self.view, self.yt_results, self.yt_status, self.yt_query = "recent", [], "", ""
        # «Recientes» (pantalla de inicio): el orden se fija al entrar en la vista, para que la lista no se
        # recoloque bajo el cursor mientras se pincha una canción.
        self.recent_view = [t["uri"] for t in self.lib["recent"]]
        self.sc, self._rows, self._rendered_view, self._scroll_target = None, [], None, None
        self.win = self.mpris = self._dlg = None
        # Novedades: géneros y tendencias en memoria (copia temporal en news.json) y su estado de carga
        self.news_genres, self.news_tracks, self.news_status = [], {}, {}
        self._news_busy, self._genres_busy, self.genres_status = set(), False, ""
        self._held = self._bg_hint = False  # segundo plano: la app se mantiene viva con la ventana oculta
        self._token = 0
        self._buffering = False  # GStreamer está rellenando el búfer: las tareas en segundo plano esperan
        self.shuffle_on = False  # interruptor «Aleatorio» (listas creadas por el usuario)
        self._shuffled = False   # la cola actual está barajada
        self._orig_queue = []    # la cola en su orden original, para volver a él al desactivar
        self._preload_token, self._prefetch_uri = None, None  # canción que se está precargando / siguiente ya en marcha
        self._img_cache, self._img_pool = {}, ThreadPoolExecutor(max_workers=3)  # miniaturas: caché y hilos acotados
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
        bus.connect("message::buffering", self.on_buffering)
        self.gst.set_property("buffer-duration", 20 * Gst.SECOND)  # hasta 20 s de audio por adelantado

    # ------------------------------------------------------------ ciclo de vida
    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gtk.Window.set_default_icon_name("com.pablo.glassplayer")
        self.css = Gtk.CssProvider()
        self.apply_css()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css, 800)
        # Acciones para el menú contextual del icono en la barra de tareas (gapplication action ...)
        for name, cb in (("play-pause", self.toggle), ("next", self.go_next), ("prev", self.go_prev), ("quit", self.quit),
                         ("search", self.focus_search)):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda _a, _p, cb=cb: cb())
            self.add_action(act)
        self.set_accels_for_action("app.quit", ["<Primary>q"])  # Ctrl+Q = salir del todo
        self.set_accels_for_action("app.search", ["<Primary>f"])  # Ctrl+F = ir al buscador

    def do_activate(self):
        if self.win:
            self.show_window()
            return
        self.win = Gtk.ApplicationWindow(application=self, title="MusicPlayer", default_width=1180, default_height=720)
        self.win.connect("close-request", self.on_close)
        self.build()
        self.win.present()
        self.mpris = Mpris(self)
        GLib.timeout_add(500, self.tick)
        self.render_sidebar()
        self.render_main()
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
        """Cerrar la ventana (la X) con música sonando NO sale de la app: la oculta y la música sigue
        (controles en la barra superior, en el panel del sistema y en la pantalla de bloqueo). Sin música,
        se cierra la aplicación. Para salir del todo estando sonando: botón «Salir», Ctrl+Q o «Salir» del icono."""
        if self.playing:
            self.keep_alive(True)  # sin esto algunas versiones de GTK terminan el proceso al quedar sin ventanas visibles
            win.set_visible(False)
            self.background_hint()
            return True
        self.quit()  # hay dos ventanas posibles (escritorio y móvil): cerrar una cierra la app
        return False

    def keep_alive(self, on):
        """Mantiene (o suelta) la aplicación viva aunque no haya ninguna ventana visible."""
        if on and not self._held:
            self.hold()
            self._held = True
        elif not on and self._held:
            self.release()
            self._held = False

    def background_hint(self):
        """Aviso (una vez por sesión) de que la música sigue sonando y cómo volver o salir."""
        if self._bg_hint:
            return
        self._bg_hint = True
        n = Gio.Notification.new("GlassPlayer sigue sonando")
        n.set_body("Cerraste la ventana pero la música continúa. Contrólala desde el icono de la barra superior "
                   "y ábrela desde ahí; «Salir» detiene la música.")
        n.set_priority(Gio.NotificationPriority.LOW)
        self.send_notification("background", n)

    def cur_win(self):
        return self.phone if self.mode == "mobile" and self.phone else self.win

    def show_window(self):
        w = self.cur_win()
        w.set_visible(True)
        w.present()
        self.keep_alive(False)  # con la ventana visible ya no hace falta el «hold» explícito

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

    def on_buffering(self, _bus, msg):
        """Si llega menos audio del que se consume, pausa hasta rellenar el búfer (en vez de entrecortarse)."""
        pct = msg.parse_buffering()
        self._buffering = pct < 100
        if self.playing:
            self.gst.set_state(Gst.State.PAUSED if pct < 100 else Gst.State.PLAYING)

    def wait_playback_idle(self):
        """Hilo en segundo plano: espera (máx. 90 s) a que la canción que se pulsó esté cargada y sonando:
        primero la canción, después el resto."""
        end = time.monotonic() + 90
        while (self._buffering or self._preload_token is not None) and time.monotonic() < end:
            time.sleep(0.5)

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
        hb.pack_start(label("MusicPlayer", "brand"))
        self.search = Gtk.SearchEntry(placeholder_text="Buscar canciones en YouTube…")
        self.search.add_css_class("global-search")
        self.search.connect("activate", lambda e: self.yt_search(e.get_text()))
        # Buscar siempre es buscar en YouTube: al pinchar el buscador (o empezar a escribir) desde cualquier
        # lista, se pasa a la lista YouTube, que muestra los resultados.
        click = Gtk.GestureClick()
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)  # sin quitarle el clic al cuadro de texto
        click.connect("pressed", lambda *_: self.goto_search())
        self.search.add_controller(click)
        self.search.connect("changed", lambda e: e.get_text().strip() and self.goto_search())
        hb.set_title_widget(self.search)
        hb.pack_end(button("ibtn", self.add_files, icon="list-add-symbolic", tip="Añadir MP3"))
        hb.pack_end(button("ibtn", self.open_style, icon="applications-graphics-symbolic", tip="Personalizar estilo"))
        hb.pack_end(button("ibtn", lambda: self.set_mode("mobile"), icon="phone-symbolic", tip="Modo móvil"))
        hb.pack_end(button("ibtn", self.quit, icon="application-exit-symbolic",
                           tip="Salir (la X solo oculta la ventana mientras suena música)"))
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
        self.btn_shuffle = button("btn-ghost", self.toggle_shuffle, text="🔀  Aleatorio",
                                  tip="Reproducir la lista en orden aleatorio (pulsa de nuevo para desactivarlo)")
        self.btn_shuffle.set_valign(CENTER)
        self.btn_dl = button("btn-ghost", self.download_view, text="⬇  Descargar")
        self.btn_dl.set_valign(CENTER)
        self.btn_add = button("btn-ghost", self.open_add_dialog, text="＋  Añadir canciones")
        self.btn_add.set_valign(CENTER)
        self.btn_clear = button("btn-ghost", self.clear_queue, text="Vaciar cola")
        self.btn_clear.set_valign(CENTER)
        self.btn_back = button("btn-ghost", lambda: self.set_view("news"), text="←  Novedades")
        self.btn_gfav = button("btn-ghost", lambda: self.toggle_genre(self.view[5:]), text="☆  Favorito")
        for b in (self.btn_back, self.btn_gfav):
            b.set_valign(CENTER)
        head.append(self.btn_back)
        head.append(titles)
        head.append(self.btn_gfav)
        head.append(self.btn_add)
        head.append(self.btn_clear)
        head.append(self.btn_dl)
        head.append(self.btn_shuffle)
        head.append(self.btn_all)
        self.l_status = label("", "sub")
        self.lst = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.lst.connect("row-activated", self.on_row_activated)
        self.sc = sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.lst)
        sc.get_vadjustment().connect("changed", self.on_scroll_range)
        self.grid_box = Gtk.Box(orientation=V, spacing=8)
        gsc = Gtk.ScrolledWindow(vexpand=True)
        gsc.set_child(self.grid_box)
        self.stack = Gtk.Stack(vexpand=True)
        self.stack.add_named(sc, "list")
        self.stack.add_named(gsc, "grid")
        for x in (head, self.l_status, self.stack):
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
        self.l_title, self.l_artist = label("MusicPlayer", "nm", max_width_chars=24), label("", "sub", max_width_chars=26)
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
        self.l_qcount = label("", "sub")
        right.append(self.l_qcount)
        right.append(button("cbtn", lambda: self.set_view("queue"), icon="view-list-ordered-symbolic", tip="Cola de reproducción"))
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
            d = self._img_cache.get(url)
            if d is None:
                d = youtube.download(url)
                if d:
                    self._img_cache[url] = d
            if d:
                GLib.idle_add(self._set_tex, pic, d)
        self._img_pool.submit(work)

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
        if key == self.view or (key == "news" and self.view.startswith("news:")):
            b.add_css_class("on")
        b.connect("clicked", lambda _b: self.set_view(key))
        return b

    def render_sidebar(self):
        self.clear(self.side_box)
        sb = self.side_box
        sb.append(label("BIBLIOTECA", "side-title"))
        for key, icon in (("recent", "document-open-recent-symbolic"), ("songs", "audio-x-generic-symbolic"), ("favs", "emblem-favorite-symbolic"), ("news", "view-grid-symbolic"), ("yt", "web-browser-symbolic"), ("queue", "view-list-ordered-symbolic")):
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
        if key == "recent":  # al entrar se toma el orden actual de «Recientes»
            self.recent_view = [t["uri"] for t in self.lib["recent"]]
        self.render_sidebar()
        self.render_main()
        if key == "news":
            self.load_genres()
        elif key.startswith("news:"):
            self.load_chart(key[5:])

    def view_tracks(self):
        if self.view == "recent":
            by = {t["uri"]: t for t in self.lib["recent"]}
            by.update({t["uri"]: t for t in self.lib["tracks"]})  # la biblioteca tiene los datos más recientes
            return [by[u] for u in self.recent_view if u in by]
        if self.view == "songs":
            return self.lib["tracks"]
        if self.view == "favs":
            return [t for t in self.lib["tracks"] if t["uri"] in self.lib["favorites"]]
        if self.view == "yt":
            return self.yt_results
        if self.view.startswith("news:"):  # solo las ya encontradas en YouTube
            return [t for t in self.news_tracks.get(self.view[5:], []) if t.get("uri")]
        if self.view == "queue":
            return [it[1] for it in self.queue_items() if it[0] == "track"]
        by = {t["uri"]: t for t in self.lib["tracks"]}
        return [by[u] for u in self.lib["playlists"].get(self.view[3:], []) if u in by]

    def render_main(self):
        in_genre = self.view.startswith("news:")
        self.btn_back.set_visible(in_genre)
        self.btn_gfav.set_visible(in_genre)
        self.stack.set_visible_child_name("grid" if self.view == "news" else "list")
        if self.view == "news":
            self.l_page.set_label(TITLES["news"])
            self.l_crumb.set_label("BIBLIOTECA")
            self.refresh_status()
            for b in (self.btn_all, self.btn_shuffle, self.btn_dl, self.btn_add, self.btn_clear):
                b.set_visible(False)
            self.render_news_grid()
            return
        tr = self.view_tracks()
        if in_genre:
            g = self.genre(self.view[5:])
            self.l_page.set_label(g["name"] if g else "Género")
            self.l_crumb.set_label("NOVEDADES · TENDENCIAS")
            fav = self.view[5:] in self.lib["news_genres"]
            self.btn_gfav.set_label("★  Favorito" if fav else "☆  Favorito")
        elif self.view.startswith("pl:"):
            self.l_page.set_label(self.view[3:])
            self.l_crumb.set_label("LISTA")
        elif self.view == "queue":
            self.l_page.set_label(TITLES["queue"])
            self.l_crumb.set_label("REPRODUCCIÓN")
        else:
            self.l_page.set_label(TITLES[self.view])
            self.l_crumb.set_label(f"RESULTADOS DE «{self.yt_query.upper()}»" if self.view == "yt" and self.yt_query else "BIBLIOTECA")
        self.refresh_status()
        self.btn_all.set_visible(bool(tr) and self.view != "queue")
        self.btn_clear.set_visible(self.view == "queue" and bool(self.up_next))
        self.btn_add.set_visible(self.view.startswith("pl:"))  # solo dentro de una lista creada
        self.btn_shuffle.set_visible(self.view.startswith("pl:") and len(tr) > 1)  # aleatorio: solo en listas creadas
        (self.btn_shuffle.add_css_class if self.shuffle_on else self.btn_shuffle.remove_css_class)("on")
        self.l_qcount.set_label(str(len(self.up_next)) if self.up_next else "")
        todo = [t for t in tr if self.dl_state(t) == "todo"]
        self.btn_dl.set_visible(bool(todo))
        self.btn_dl.set_label(f"⬇  Descargar ({len(todo)})" if len(todo) > 1 else "⬇  Descargar")
        # Si seguimos en la misma vista (marcar favorito, quitar de lista…), la lista no salta al principio.
        keep = self.sc.get_vadjustment().get_value() if self._rendered_view == self.view else 0
        self._rendered_view = self.view
        self.clear(self.lst)
        self._rows, self._qrows = [], []
        cur = self.current()
        if self.view == "queue":
            self.build_queue_rows()
        else:
            for i, t in enumerate(tr):
                self.lst.append(self.make_row(t, i, bool(cur) and cur["uri"] == t["uri"]))
        self._scroll_target = (keep, GLib.get_monotonic_time() + 400_000)
        self.on_scroll_range(self.sc.get_vadjustment())

    def on_scroll_range(self, adj):
        """Tras reconstruir la lista GTK recalcula su tamaño; entonces se restaura la posición."""
        tgt = self._scroll_target
        if tgt and GLib.get_monotonic_time() < tgt[1]:
            adj.set_value(min(tgt[0], max(0, adj.get_upper() - adj.get_page_size())))

    def refresh_playing(self):
        """Marca la fila que suena sin reconstruir la lista (así no se pierde la posición del scroll)."""
        cur = self.current()
        for r in self._rows:
            on = bool(cur) and cur["uri"] == r["uri"]
            if on:
                r["row"].add_css_class("playing")
            else:
                r["row"].remove_css_class("playing")
            r["num"].set_label("▶" if on else str(r["i"] + 1))

    def status_text(self):
        if self.dl_status:
            return self.dl_status
        tr = self.view_tracks()
        if self.view == "yt":
            return self.yt_status or ("" if tr else "Escribe en la barra superior y pulsa Intro para buscar en YouTube")
        if self.view == "news":
            return self.genres_status or ("" if self.news_genres else "Sin géneros")
        if self.view.startswith("news:"):
            return self.news_status.get(self.view[5:], "") or ("" if tr else "Sin canciones por ahora")
        if self.view == "recent":
            return "" if tr else "Aún no has escuchado nada: elige una canción y aparecerá aquí"
        if self.view == "queue":
            return "" if tr else "La cola está vacía: en ⋯ de cualquier canción elige «Añadir a la cola»"
        return "" if tr else "Aún no hay canciones aquí"

    def refresh_status(self):
        self.l_status.set_label(self.status_text())

    def make_row(self, t, i, playing, qctx=None):
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
        num = label("▶" if playing else str(i + 1), "num", width_chars=3)
        self._rows.append({"uri": t["uri"], "row": row, "num": num, "th": th, "i": i})
        cells = [num, th, col, heart]
        if youtube.is_yt(t["uri"]):
            cells.append(self.dl_button(t))
        if qctx and qctx[0] == "q":  # canción de la cola del usuario: se puede quitar con un clic
            cells.append(button("ibtn", lambda k=qctx[1]: self.queue_remove(k), icon="window-close-symbolic", tip="Quitar de la cola"))
        cells += [self.row_menu(t, qctx), label(library.fmt(t["duration"]), "sub", width_chars=5)]
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

    def row_menu(self, t, qctx=None):
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
        item("Reproducir a continuación", lambda: self.queue_add(t, front=True))
        item("Añadir a la cola", lambda: self.queue_add(t))
        if qctx and qctx[0] == "q":
            item("Quitar de la cola", lambda: self.queue_remove(qctx[1]))
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

    # ------------------------------------------------------------ cola de reproducción
    def queue_items(self):
        """Contenido de la vista Cola: [('head', texto) | ('track', pista, contexto)], contexto = 'now' | ('q', k) | ('c', i)."""
        items, cur = [], self.current()
        if cur:
            items += [("head", "SONANDO AHORA"), ("track", cur, "now")]
        if self.up_next:
            items.append(("head", f"EN COLA · {len(self.up_next)}"))
            items += [("track", t, ("q", k)) for k, t in enumerate(self.up_next)]
        rest = list(enumerate(self.queue))[self.idx + 1:self.idx + 1 + QUEUE_REST_MAX] if self.queue else []
        if rest:
            items.append(("head", "A CONTINUACIÓN"))
            items += [("track", t, ("c", i)) for i, t in rest]
        return items

    def build_queue_rows(self):
        n = 0
        for it in self.queue_items():
            if it[0] == "head":
                self.lst.append(label(it[1], "side-title"))
                row = self.lst.get_row_at_index(len(self._qrows))
                row.set_activatable(False)
                row.set_selectable(False)
                self._qrows.append(it)
                continue
            _k, t, ctx = it
            n = 1 if ctx == "now" else (ctx[1] + 1 if ctx[0] == "q" else ctx[1] + 1)
            self.lst.append(self.make_row(t, n - 1, ctx == "now", ctx))
            self._qrows.append(it)

    def on_row_activated(self, _lst, row):
        i = row.get_index()
        if self.view != "queue":
            self.play_list(self.view_tracks(), i)
            return
        if not (0 <= i < len(self._qrows)) or self._qrows[i][0] != "track":
            return
        _k, t, ctx = self._qrows[i]
        if ctx == "now":
            self.toggle()
        elif ctx[0] == "q":
            self.queue_remove(ctx[1], refresh=False)
            self._play(t)
        else:
            self.play_index(ctx[1])

    def queue_add(self, t, front=False):
        """«Añadir a la cola» (al final) o «Reproducir a continuación» (el primero)."""
        if not self.current():  # nada sonando: se empieza por esta canción
            self.play_list([t], 0)
            return
        self.up_next.insert(0 if front else len(self.up_next), dict(t))
        self.flash(f"«{t['title']}» " + ("sonará a continuación" if front else "añadida a la cola"))
        self.queue_changed()

    def queue_remove(self, k, refresh=True):
        if 0 <= k < len(self.up_next):
            del self.up_next[k]
        if refresh:
            self.queue_changed()

    def clear_queue(self):
        self.up_next.clear()
        self.queue_changed()

    def queue_changed(self):
        self.l_qcount.set_label(str(len(self.up_next)) if self.up_next else "")
        if self.view == "queue":
            self._rendered_view = None
            self.render_main()
        else:
            self.render_main()  # misma vista: conserva la posición del scroll

    def flash(self, text, secs=3):
        """Mensaje breve en la línea de estado."""
        self.set_dl_status(text)
        GLib.timeout_add_seconds(secs, self._dl_clear, text)

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
        self.lib["recent"] = [x for x in self.lib["recent"] if x["uri"] != uri]
        self.up_next = [x for x in self.up_next if x["uri"] != uri]
        if cur and cur["uri"] == uri:
            self.stop()
            self.queue, self.idx, self._cur = [], -1, None
            self.show_track()
        library.drop_cover(t.get("cover"), self.lib["tracks"] + self.queue + self.up_next)
        self.commit()

    def add_files(self, playlist=None):
        """Añade MP3 del equipo a la biblioteca y, si se indica, también a esa lista."""
        d = Gtk.FileChooserNative.new("Añadir MP3", self.cur_win(), Gtk.FileChooserAction.OPEN, "Añadir", "Cancelar")
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
                    self._files_read, [library.read_track(p) for p in paths], playlist), daemon=True).start()
        d.connect("response", done)
        self._dlg = d
        d.show()

    def _files_read(self, tracks, playlist):
        for t in tracks:
            self.add_to_library(t)
            if playlist in self.lib["playlists"] and t["uri"] not in self.lib["playlists"][playlist]:
                self.lib["playlists"][playlist].append(t["uri"])
        self.commit()
        if getattr(self, "_add_dlg", None) and self._add_dlg.get_visible():
            self._add_dlg.set_visible(False)

    # ------------------------------------------------------------ añadir canciones a una lista
    def open_add_dialog(self):
        """Selector para meter canciones de la biblioteca directamente en la lista que estás viendo."""
        if not self.view.startswith("pl:"):
            return
        name = self.view[3:]
        have = set(self.lib["playlists"].get(name, []))
        avail = [t for t in self.lib["tracks"] if t["uri"] not in have]
        dlg = Gtk.Window(title=f"Añadir a «{name}»", modal=True, transient_for=self.cur_win(),
                         default_width=470, default_height=560)
        dlg.add_css_class("style-panel")
        self._add_dlg = dlg
        box = Gtk.Box(orientation=V, spacing=10, margin_top=16, margin_bottom=16, margin_start=18, margin_end=18)
        dlg.set_child(box)
        box.append(label(f"Añadir a «{name}»", "panel-h"))
        flt = Gtk.SearchEntry(placeholder_text="Filtrar canciones…")
        box.append(flt)
        lst = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        checks = []
        for t in avail:
            row = Gtk.Box(spacing=10)
            cb = Gtk.CheckButton()
            col = Gtk.Box(orientation=V, hexpand=True, valign=CENTER)
            col.append(label(t["title"], "nm"))
            col.append(label(t["artist"], "sub"))
            for x in (cb, col):
                row.append(x)
            lst.append(row)
            checks.append((cb, t, f"{t['title']} {t['artist']}".lower()))
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(lst)
        empty = label("Toda tu biblioteca ya está en esta lista" if self.lib["tracks"] else
                      "Tu biblioteca está vacía: añade MP3 desde el equipo", "sub")
        box.append(sc if avail else empty)

        btn_ok = button("btn-primary", lambda: None, text="Añadir")
        btn_ok.set_sensitive(False)

        def update(*_):
            n = sum(1 for cb, _t, _k in checks if cb.get_active())
            btn_ok.set_label(f"Añadir ({n})" if n else "Añadir")
            btn_ok.set_sensitive(n > 0)

        def do_filter(row):
            q = flt.get_text().strip().lower()
            return not q or q in checks[row.get_index()][2]

        for cb, _t, _k in checks:
            cb.connect("toggled", update)
        lst.set_filter_func(do_filter)
        flt.connect("search-changed", lambda _e: lst.invalidate_filter())

        def confirm():
            picked = [t for cb, t, _k in checks if cb.get_active()]
            dlg.set_visible(False)
            for t in picked:
                self.add_to_playlist(name, t)
            if picked:
                n = len(picked)
                self.flash(f"1 canción añadida a «{name}»" if n == 1 else f"{n} canciones añadidas a «{name}»")

        foot = Gtk.Box(spacing=8)
        foot.append(button("panel-btn", lambda: self.add_files(name), text="Desde archivos MP3…"))
        foot.append(Gtk.Box(hexpand=True))
        foot.append(button("panel-btn", lambda: dlg.set_visible(False), text="Cancelar"))
        btn_ok.connect("clicked", lambda _b: confirm())
        foot.append(btn_ok)
        box.append(foot)
        dlg.present()

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
            for x in self.lib["tracks"] + self.lib["recent"]:  # la copia de la biblioteca y «Recientes» también
                if x["uri"] == t["uri"]:
                    x["cover"] = path
            library.drop_cover(old, self.lib["tracks"] + self.queue + self.up_next)
            self.show_track()
            self.render_main()  # la miniatura de la fila cambia; la posición del scroll se conserva
            library.save(self.lib)

    # ------------------------------------------------------------ Novedades (tendencias de Deezer + YouTube)
    def genre(self, gid):
        return next((g for g in self.news_genres if g["id"] == gid), None)

    def load_genres(self):
        if self.news_genres or self._genres_busy:
            return
        self._genres_busy = True
        self.genres_status = "Cargando géneros…"
        self.refresh_status()

        def work():
            try:
                res = news.genres()
            except Exception:
                res = None
            GLib.idle_add(self._genres_done, res)
        threading.Thread(target=work, daemon=True).start()

    def _genres_done(self, res):
        self._genres_busy = False
        self.genres_status = "" if res else "No se pudo conectar con Deezer. Comprueba tu conexión."
        self.news_genres = res or []
        if self.view == "news":
            self.render_main()
        elif self.view.startswith("news:"):
            self.render_main()  # ya se puede mostrar el nombre del género

    def render_news_grid(self):
        self.clear(self.grid_box)
        favs = [g for g in self.news_genres if g["id"] in self.lib["news_genres"]]
        rest = [g for g in self.news_genres if g["id"] not in self.lib["news_genres"]]
        for title, items in (("TUS GÉNEROS", favs), ("TODOS LOS GÉNEROS" if favs else "GÉNEROS", rest)):
            if not items:
                continue
            self.grid_box.append(label(title, "side-title"))
            fb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, valign=START,
                             min_children_per_line=2, max_children_per_line=6, column_spacing=14, row_spacing=14)
            fb.add_css_class("genre-flow")
            for g in items:
                fb.append(self.genre_tile(g))
            self.grid_box.append(fb)

    def genre_tile(self, g):
        ov = Gtk.Overlay()
        ov.set_size_request(180, 112)
        ov.set_overflow(Gtk.Overflow.HIDDEN)
        ov.add_css_class("genre-box")
        ov.add_css_class(f"g{int(g['id']) % 8}")
        ov.set_child(Gtk.Box())
        pic = Gtk.Picture(halign=Gtk.Align.END, valign=Gtk.Align.END, margin_end=8, margin_bottom=8)
        pic.set_can_shrink(True)
        pic.set_size_request(86, 86)
        pic.add_css_class("genre-pic")
        if g.get("picture"):
            self.async_thumb(pic, g["picture"])
        ov.add_overlay(pic)
        ov.add_overlay(label(g["name"], "genre-name", halign=START, valign=START, margin_start=14, margin_top=12,
                             max_width_chars=14))
        fav = g["id"] in self.lib["news_genres"]
        star = Gtk.Button(icon_name="starred-symbolic" if fav else "non-starred-symbolic",
                          halign=Gtk.Align.END, valign=START, margin_end=6, margin_top=6)
        star.add_css_class("gstar")
        if fav:
            star.add_css_class("on")
        star.set_tooltip_text("Quitar de favoritos" if fav else "Marcar como favorito")
        star.connect("clicked", lambda _b: self.toggle_genre(g["id"]))
        ov.add_overlay(star)
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self.set_view("news:" + g["id"]))
        ov.add_controller(click)
        ov.set_cursor_from_name("pointer")
        return ov

    def toggle_genre(self, gid):
        favs = self.lib["news_genres"]
        favs.remove(gid) if gid in favs else favs.append(gid)
        library.save(self.lib)
        self.render_main()

    def load_chart(self, gid):
        """Hilo 1: tendencias de Deezer. Hilo 2: busca en YouTube las canciones que aún no tienen enlace."""
        if gid in self._news_busy:
            return
        self._news_busy.add(gid)
        if gid not in self.news_tracks:
            self.news_status[gid] = "Cargando tendencias…"
            self.refresh_status()

        def work():
            try:
                tracks = news.chart(gid)
            except Exception:
                tracks = None
            GLib.idle_add(self._chart_done, gid, tracks)
        threading.Thread(target=work, daemon=True).start()

    def _chart_done(self, gid, tracks):
        if tracks is None:
            self._news_busy.discard(gid)
            if gid not in self.news_tracks:
                self.news_status[gid] = "No se pudo conectar con Deezer. Comprueba tu conexión."
            self.render_main()
            return
        self.news_tracks[gid] = tracks
        pending = [t for t in tracks if not t.get("uri")]
        if pending and not youtube.available():
            self._news_busy.discard(gid)
            self.news_status[gid] = "Falta yt-dlp: ejecuta ./install.sh"
        elif pending:
            self.news_status[gid] = f"Buscando en YouTube… 0/{len(pending)}"

            def work():
                # una búsqueda cada vez, con prioridad mínima y esperando si la música está cargando
                for i, t in enumerate(pending, 1):
                    news.resolve(t, self.wait_playback_idle)
                    GLib.idle_add(self._chart_progress, gid, i, len(pending))
            threading.Thread(target=work, daemon=True).start()
        else:
            self._news_busy.discard(gid)
            self.news_status[gid] = ""
        if self.view == "news:" + gid:
            self.render_main()

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
        # redibujar solo de vez en cuando para que la lista no parpadee
        if finished or done == 1 or done % 4 == 0:
            self.render_main()
        else:
            self.refresh_status()

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

    def goto_search(self):
        """Pasa a la lista YouTube (si no estás ya en ella) para ver ahí los resultados."""
        if self.view != "yt":
            self.set_view("yt")

    def focus_search(self):
        if self.mode == "desktop" and self.win and self.win.get_visible():
            self.search.grab_focus()
            self.goto_search()

    def _yt_done(self, q, res):
        if q != self.yt_query:
            return
        if res is None:
            self.yt_status = "No se pudo buscar (sin conexión o yt-dlp desactualizado: ejecuta 'yt-dlp -U')"
        else:
            self.yt_results, self.yt_status = res, "" if res else "Sin resultados"
        self._rendered_view = None  # resultados nuevos: la lista empieza desde arriba
        self.render_main()

    # ------------------------------------------------------------ reproducción
    def current(self):
        return self._cur

    def position_us(self):
        ok, pos = self.gst.query_position(Gst.Format.TIME)
        return pos // 1000 if ok else 0

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

    def toggle_shuffle(self):
        """Interruptor «Aleatorio»: al activarlo baraja la lista y la reproduce; al desactivarlo vuelve al orden
        original sin cortar la canción que está sonando."""
        self.shuffle_on = not self.shuffle_on
        tr = list(self.view_tracks())
        cur = self._cur
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
        self.render_main()

    def play_all(self):
        tr = self.view_tracks()
        if tr:
            shuffle = self.shuffle_on and self.view.startswith("pl:")
            self.play_list(tr, random.randrange(len(tr)) if shuffle else 0)

    def play_index(self, i):
        if not (0 <= i < len(self.queue)):
            return
        self.idx = i
        self._play(self.queue[i])

    def _play(self, t):
        """Reproduce la pista t (de la lista o de la cola del usuario)."""
        self._cur, self.playing = t, True
        self._token += 1
        library.push_recent(self.lib, t)  # «Recientes»: la lista visible no se recoloca hasta volver a entrar
        library.save(self.lib)
        self.gst.set_state(Gst.State.NULL)
        self._buffering = False
        self._preload_token = self._token if youtube.is_yt(t["uri"]) else None  # las búsquedas de fondo esperan
        self.show_track()
        if youtube.is_yt(t["uri"]):
            self.set_subtitle("Cargando canción… 0 %")
            threading.Thread(target=self._resolve, args=(t, self._token), daemon=True).start()
        else:
            self._start(t["uri"])

    def _start(self, uri):
        self.gst.set_property("uri", uri)
        self.gst.set_state(Gst.State.PLAYING)

    def _resolve(self, t, token):
        """Hilo: descarga la canción ENTERA (con progreso) y solo entonces empieza a sonar, desde disco: sin cortes
        aunque la conexión falle después. Si la descarga falla, plan B: streaming directo como antes."""
        self._preload_token = token
        play = None
        try:
            play = GLib.filename_to_uri(audiocache.fetch(
                t["uri"], on_progress=lambda p: GLib.idle_add(self._load_progress, token, p),
                cancel=lambda: token != self._token))
        except audiocache.Cancelled:
            return  # el usuario cambió de canción: la nueva se encarga
        except Exception:
            if token == self._token:
                try:
                    play = youtube.stream_url(t["uri"])
                except Exception:
                    play = None
        finally:
            if self._preload_token == token:
                self._preload_token = None
        GLib.idle_add(self._resolved, t, token, play)
        if play and not t.get("cover"):  # la portada llega después: no retrasa el inicio de la canción
            data = youtube.download(t["cover_url"]) if t.get("cover_url") else None  # portada HD de Deezer
            data = data or youtube.thumbnail(t["uri"])
            path = library.save_cover(data) if data else None
            if path:
                GLib.idle_add(self._cover_ready, t, path)

    def _load_progress(self, token, pct):
        if token == self._token:
            self.set_subtitle(f"Cargando canción… {pct:.0f} %")

    def prefetch_next(self):
        """Mientras suena la actual, descarga ya la siguiente (cola o lista) para que el cambio sea instantáneo."""
        if self.up_next:
            nxt = self.up_next[0]
        elif self.queue:
            nxt = self.queue[(self.idx + 1) % len(self.queue)]
        else:
            return
        uri = nxt["uri"]
        if not youtube.is_yt(uri) or self._prefetch_uri == uri or audiocache.cached(uri):
            return
        self._prefetch_uri, token = uri, self._token

        def work():
            try:
                audiocache.fetch(uri, low_priority=True, cancel=lambda: token != self._token)
            except Exception:
                pass
            finally:
                if self._prefetch_uri == uri:
                    self._prefetch_uri = None
        threading.Thread(target=work, daemon=True).start()

    def _cover_ready(self, t, path):
        if path and not t.get("cover"):
            t["cover"] = path
            for x in self.lib["tracks"]:
                if x["uri"] == t["uri"]:
                    x["cover"] = path
            for x in self.lib["recent"]:
                if x["uri"] == t["uri"]:
                    x["cover"] = path
            for r in self._rows:  # miniatura de la fila, sin reconstruir la lista
                if r["uri"] == t["uri"]:
                    self.set_pic(r["th"], path, 40)
            library.save(self.lib)
            if self.current() is t:
                self.set_pic(self.t_cover, path, 54)
                self.update_bg()
                self.update_phone()

    def _resolved(self, t, token, url):
        if token != self._token:
            return
        if url:
            self._start(url)
            self.prefetch_next()
        else:
            self.playing = False
        self.show_track()
        if not url:
            self.set_subtitle("No se pudo cargar (actualiza yt-dlp: 'yt-dlp -U')")

    def toggle(self):
        if not self.current():
            if self.up_next:
                self._play(self.up_next.pop(0))
            elif self.lib["tracks"]:
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
        if self.up_next:  # la cola del usuario tiene prioridad; después sigue la lista por donde iba
            self._play(self.up_next.pop(0))
        elif self.queue:
            nxt = self.idx + 1
            if nxt >= len(self.queue) and self._shuffled and len(self.queue) > 1:
                last = self.queue[-1]
                random.shuffle(self.queue)
                if self.queue[0] is last:  # que la última no se repita justo al empezar la nueva vuelta
                    self.queue[0], self.queue[-1] = self.queue[-1], self.queue[0]
            self.play_index(nxt % len(self.queue))
        elif self._cur:
            self._play(self._cur)

    def go_prev(self):
        in_list = bool(self.queue) and 0 <= self.idx < len(self.queue)
        if self._cur and in_list and self._cur is not self.queue[self.idx]:
            self.play_index(self.idx)  # estamos en una canción de la cola: «anterior» vuelve a la de la lista
        elif in_list:
            self.play_index((self.idx - 1) % len(self.queue))
        elif self._cur:
            self._play(self._cur)

    def on_seek(self, _scale, _scroll, value):
        self.gst.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, int(value * Gst.SECOND))
        return False

    def seek_to_us(self, pos_us):
        self.gst.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, max(0, pos_us) * 1000)

    def can_next(self):
        return bool(self.current())

    def can_prev(self):
        return bool(self.current())

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
        self.l_title.set_label(t["title"] if t else "MusicPlayer")
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
        if self.view == "queue" and self.sc:
            self._rendered_view = None
            self.render_main()
        else:
            self.refresh_playing()
        self.update_window_title()
        self.show_state()

    def update_window_title(self):
        """Como Spotify de escritorio: el título de la ventana es «Canción — Artista» y se ve en el dock,
        en la vista de actividades y en Alt+Tab sin abrir la app."""
        t = self.current()
        text = (f"{t['title']} — {t['artist']}" if t.get("artist") else t["title"]) if t else "MusicPlayer"
        for w in (self.win, self.phone):
            if w:
                w.set_title(text)

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
        op = max(0.15, 1 - self.theme["transparency"] / 100)
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
        self.tr_scale = Gtk.Scale.new_with_range(H, 0, 85, 1)
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
        w = Gtk.Window(application=self, title="MusicPlayer", decorated=False, resizable=False,
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
        self.p_title = Gtk.Label(label="MusicPlayer", ellipsize=Pango.EllipsizeMode.END, max_width_chars=24, margin_top=10)
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
        self.p_title.set_label(t["title"] if t else "MusicPlayer")
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
# LAS CANCIONES SE DESCARGAN EN LA CARPETA MUSIC ORIGINAL DE LINUX, AHI CREA UNA SUBCARPETA CON TODO

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
