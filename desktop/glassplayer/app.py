"""Interfaz GTK4 con estética Apple Music "glass" y reproducción con GStreamer."""
import os
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gst", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gst, Gtk, Pango

from . import deezer, library
from .mpris import Mpris

CSS = """
window { background: #121212; }
.scrim { background: rgba(0,0,0,.45); }
.glass { background-image: linear-gradient(to bottom, rgba(255,255,255,.28), rgba(255,255,255,.08));
         border: 1px solid rgba(255,255,255,.35); border-radius: 28px; padding: 18px; }
.glass label, .glass button { color: white; }
.glass label.sub { color: rgba(255,255,255,.7); }
.glass label.title { font-weight: 800; font-size: 20px; }
.glass-row { border-radius: 14px; padding: 6px 8px; }
.playing { background: rgba(255,255,255,.14); }
.thumb { border-radius: 10px; background: rgba(255,255,255,.12); }
.cover-big { border-radius: 20px; background: rgba(255,255,255,.12); }
.ctl image { -gtk-icon-size: 28px; }
list, row { background: transparent; }
scale trough { background: rgba(255,255,255,.3); }
scale highlight, scale slider { background: white; }
entry { background: rgba(255,255,255,.12); color: white; }
"""
V, H = Gtk.Orientation.VERTICAL, Gtk.Orientation.HORIZONTAL


def label(text="", css=None, **kw):
    l = Gtk.Label(label=text, xalign=0, ellipsize=Pango.EllipsizeMode.END, **kw)
    if css:
        l.add_css_class(css)
    return l


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.pablo.glassplayer")
        Gst.init(None)
        self.tracks = library.load()
        self.idx, self.playing, self.win, self.mpris, self._dlg = -1, False, None, None, None
        self.gst = Gst.ElementFactory.make("playbin", "player")
        bus = self.gst.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", lambda *_: self.go_next())
        bus.connect("message::error", lambda _b, m: print("GStreamer:", m.parse_error()[0]))

    # ------------------------------------------------------------ ciclo de vida
    def do_activate(self):
        if self.win:
            self.win.present()
            return
        css = Gtk.CssProvider()
        css.load_from_string(CSS) if hasattr(css, "load_from_string") else css.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, 800)
        self.win = Gtk.ApplicationWindow(application=self, title="GlassPlayer", default_width=1020, default_height=660)
        self.build()
        self.win.present()
        self.mpris = Mpris(self)
        GLib.timeout_add(500, self.tick)
        self.show_track()

    def do_shutdown(self):
        self.gst.set_state(Gst.State.NULL)
        Gtk.Application.do_shutdown(self)

    # ------------------------------------------------------------ interfaz
    def build(self):
        ov = Gtk.Overlay()
        self.bg = Gtk.Picture()
        self.bg.set_keep_aspect_ratio(False)
        ov.set_child(self.bg)
        scrim = Gtk.Box(hexpand=True, vexpand=True)
        scrim.add_css_class("scrim")
        scrim.set_can_target(False)
        ov.add_overlay(scrim)
        main = Gtk.Box(spacing=16, margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        ov.add_overlay(main)
        self.win.set_child(ov)

        # tarjeta del reproductor (cristal)
        card = Gtk.Box(orientation=V, spacing=10, width_request=340)
        card.add_css_class("glass")
        self.cover = Gtk.Picture()
        self.cover.set_can_shrink(True)
        self.cover.set_size_request(300, 300)
        self.cover.add_css_class("cover-big")
        self.l_title = label("GlassPlayer", "title", max_width_chars=28)
        self.l_artist = label("Añade tus MP3", "sub", max_width_chars=32)
        self.scale = Gtk.Scale.new_with_range(H, 0, 100, 1)
        self.scale.set_draw_value(False)
        self.scale.connect("change-value", self.on_seek)
        times = Gtk.Box()
        self.l_pos, self.l_dur = label("0:00", "sub", hexpand=True), label("0:00", "sub")
        times.append(self.l_pos)
        times.append(self.l_dur)
        ctr = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        for icon, cb in (("media-skip-backward-symbolic", self.go_prev),
                         ("media-playback-start-symbolic", self.toggle),
                         ("media-skip-forward-symbolic", self.go_next)):
            b = Gtk.Button(icon_name=icon)
            b.add_css_class("flat"), b.add_css_class("circular"), b.add_css_class("ctl")
            b.connect("clicked", lambda _b, cb=cb: cb())
            ctr.append(b)
            if cb == self.toggle:
                self.btn_play = b
        crow = Gtk.Box(spacing=8, homogeneous=True)
        b1, b2 = Gtk.Button(label="Portada: imagen"), Gtk.Button(label="Portada: Deezer")
        b1.connect("clicked", lambda _b: self.pick_image())
        b2.connect("clicked", lambda _b: self.cover_from_deezer())
        crow.append(b1)
        crow.append(b2)
        for w in (self.cover, self.l_title, self.l_artist, self.scale, times, ctr, crow):
            card.append(w)
        main.append(card)

        # panel derecho: biblioteca / Deezer
        right = Gtk.Box(orientation=V, spacing=8, hexpand=True)
        right.add_css_class("glass")
        self.stack = Gtk.Stack(vexpand=True)
        right.append(Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER))
        right.append(self.stack)
        main.append(right)

        lib = Gtk.Box(orientation=V, spacing=8)
        add = Gtk.Button(label="Añadir MP3…")
        add.connect("clicked", lambda _b: self.add_files())
        self.lst = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.lst.connect("row-activated", lambda _l, row: self.play_index(row.get_index()))
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.lst)
        lib.append(add)
        lib.append(sc)
        self.stack.add_titled(lib, "lib", "Biblioteca")

        dz = Gtk.Box(orientation=V, spacing=8)
        bar = Gtk.Box(spacing=8)
        self.mode = Gtk.DropDown.new_from_strings(["Canciones", "Álbumes"])
        self.entry = Gtk.SearchEntry(hexpand=True, placeholder_text="Buscar en Deezer…")
        self.entry.connect("activate", lambda _e: self.dz_search())
        bar.append(self.mode)
        bar.append(self.entry)
        self.dz_status = label("Solo previews de 30 s (límite de la API pública de Deezer)", "sub")
        self.dz_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        sc2 = Gtk.ScrolledWindow(vexpand=True)
        sc2.set_child(self.dz_list)
        for w in (bar, self.dz_status, sc2):
            dz.append(w)
        self.stack.add_titled(dz, "dz", "Deezer")

    def thumb(self, path, size):
        p = Gtk.Picture(halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        p.set_can_shrink(True)
        p.set_size_request(size, size)
        p.add_css_class("thumb")
        if path:
            try:
                p.set_paintable(Gdk.Texture.new_for_pixbuf(
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size * 2, size * 2, True)))
            except Exception:
                pass
        return p

    def _set_tex(self, pic, data):
        try:
            ld = GdkPixbuf.PixbufLoader()
            ld.write(data)
            ld.close()
            pic.set_paintable(Gdk.Texture.new_for_pixbuf(ld.get_pixbuf()))
        except Exception:
            pass

    def async_thumb(self, pic, url):
        def work():
            d = deezer.download(url)
            if d:
                GLib.idle_add(self._set_tex, pic, d)
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def clear(box):
        while (c := box.get_first_child()):
            box.remove(c)

    def refresh_list(self):
        self.clear(self.lst)
        for i, t in enumerate(self.tracks):
            row = Gtk.Box(spacing=10)
            row.add_css_class("glass-row")
            if i == self.idx:
                row.add_css_class("playing")
            col = Gtk.Box(orientation=V, hexpand=True, valign=Gtk.Align.CENTER)
            col.append(label(t["title"]))
            col.append(label(t["artist"], "sub"))
            rm = Gtk.Button(icon_name="window-close-symbolic")
            rm.add_css_class("flat")
            rm.connect("clicked", lambda _b, i=i: self.remove(i))
            for w in (label(str(i + 1), "sub", width_chars=3), self.thumb(t["cover"], 44), col,
                      label(library.fmt(t["duration"]), "sub"), rm):
                row.append(w)
            self.lst.append(row)

    # ------------------------------------------------------------ estado de la pista actual
    def current(self):
        return self.tracks[self.idx] if 0 <= self.idx < len(self.tracks) else None

    def position_us(self):
        ok, pos = self.gst.query_position(Gst.Format.TIME)
        return pos // 1000 if ok else 0

    def show_track(self):
        t = self.current()
        self.l_title.set_label(t["title"] if t else "GlassPlayer")
        self.l_artist.set_label(t["artist"] if t else "Añade tus MP3")
        self.scale.set_range(0, max(1, t["duration"]) if t else 1)
        self.l_dur.set_label(library.fmt(t["duration"]) if t else "0:00")
        tex = bg = None
        if t and t["cover"] and os.path.exists(t["cover"]):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(t["cover"], 600, 600, True)
                tex, bg = Gdk.Texture.new_for_pixbuf(pb), Gdk.Texture.new_for_pixbuf(library.blur(pb))
            except Exception:
                pass
        self.cover.set_paintable(tex)
        self.bg.set_paintable(bg)
        self.refresh_list()
        self.show_state()

    def show_state(self):
        self.btn_play.set_icon_name("media-playback-pause-symbolic" if self.playing else "media-playback-start-symbolic")
        if self.mpris:
            self.mpris.notify()

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

    # ------------------------------------------------------------ reproducción
    def play_index(self, i):
        if not (0 <= i < len(self.tracks)):
            return
        self.idx, self.playing = i, True
        self.gst.set_state(Gst.State.NULL)
        self.gst.set_property("uri", self.tracks[i]["uri"])
        self.gst.set_state(Gst.State.PLAYING)
        self.show_track()

    def toggle(self):
        if not self.current():
            if self.tracks:
                self.play_index(0)
            return
        self.playing = not self.playing
        self.gst.set_state(Gst.State.PLAYING if self.playing else Gst.State.PAUSED)
        self.show_state()

    def stop(self):
        self.gst.set_state(Gst.State.NULL)
        self.playing = False
        self.show_state()

    def go_next(self):
        if self.tracks:
            self.play_index((self.idx + 1) % len(self.tracks))

    def go_prev(self):
        if self.tracks:
            self.play_index((self.idx - 1) % len(self.tracks))

    def on_seek(self, _scale, _scroll, value):
        self.gst.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, int(value * Gst.SECOND))
        return False

    def seek_rel(self, offset_us):
        self.gst.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, max(0, self.position_us() + offset_us) * 1000)

    # ------------------------------------------------------------ biblioteca y portadas
    def add_tracks(self, new):
        have = {t["uri"] for t in self.tracks}
        self.tracks += [t for t in new if t["uri"] not in have]
        library.save(self.tracks)
        self.refresh_list()
        self.show_state()

    def remove(self, i):
        t = self.tracks.pop(i)
        if i == self.idx:
            self.stop()
            self.idx = -1
        elif i < self.idx:
            self.idx -= 1
        library.drop_cover(t["cover"], self.tracks)
        library.save(self.tracks)
        self.show_track()

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

    def apply_cover(self, i, data):
        path = library.save_cover(data) if data else None
        if path and 0 <= i < len(self.tracks):
            old = self.tracks[i]["cover"]
            self.tracks[i]["cover"] = path
            library.drop_cover(old, self.tracks)
            library.save(self.tracks)
            self.show_track()

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
                    self.apply_cover(self.idx, fh.read())
        d.connect("response", done)
        self._dlg = d
        d.show()

    def cover_from_deezer(self):
        t = self.current()
        if not t:
            return
        self.stack.set_visible_child_name("dz")
        self.mode.set_selected(0)
        self.entry.set_text(f"{t['title']} {'' if t['artist'].startswith('Artista') else t['artist']}".strip())
        self.dz_search()

    # ------------------------------------------------------------ Deezer
    def dz_search(self):
        q = self.entry.get_text().strip()
        if not q:
            return
        albums = self.mode.get_selected() == 1
        self.dz_status.set_label("Buscando…")

        def work():
            try:
                res = deezer.search_albums(q) if albums else deezer.search_tracks(q)
                GLib.idle_add(self.dz_show, res)
            except Exception:
                GLib.idle_add(self.dz_status.set_label, "Sin conexión o error de Deezer")
        threading.Thread(target=work, daemon=True).start()

    def dz_show(self, res):
        self.dz_status.set_label("" if res else "Sin resultados")
        self.clear(self.dz_list)
        for r in res:
            row = Gtk.Box(spacing=10)
            row.add_css_class("glass-row")
            th = self.thumb(None, 48)
            self.async_thumb(th, r["thumb"])
            col = Gtk.Box(orientation=V, hexpand=True, valign=Gtk.Align.CENTER)
            col.append(label(r["title"]))
            col.append(label(r["artist"] + ("" if r["kind"] == "album" else f" · {r['album']}"), "sub"))
            b_add = Gtk.Button(label="Añadir álbum" if r["kind"] == "album" else "Añadir preview")
            b_add.connect("clicked", lambda _b, r=r: self.dz_add(r))
            b_cov = Gtk.Button(label="Usar portada")
            b_cov.connect("clicked", lambda _b, r=r: self.dz_cover(r))
            for w in (th, col, b_add, b_cov):
                row.append(w)
            self.dz_list.append(row)

    def dz_add(self, r):
        """Añade a la cola la preview (o las previews del álbum completo) con su portada."""
        self.dz_status.set_label("Descargando…")

        def work():
            try:
                if r["kind"] == "album":
                    album, cover_url, items = deezer.album_tracks(r["id"])
                else:
                    album, cover_url = r["album"], r["cover"]
                    items = [{"title": r["title"], "artist": r["artist"], "preview": r["preview"]}]
                data = deezer.download(cover_url)
                cover = library.save_cover(data) if data else None
                new = [{"uri": i["preview"], "title": i["title"], "artist": i["artist"], "album": album,
                        "duration": 30, "cover": cover} for i in items if i["preview"]]
                GLib.idle_add(self.add_tracks, new)
                GLib.idle_add(self.dz_status.set_label, f"{len(new)} preview(s) añadida(s) a la biblioteca")
            except Exception:
                GLib.idle_add(self.dz_status.set_label, "Sin conexión o error de Deezer")
        threading.Thread(target=work, daemon=True).start()

    def dz_cover(self, r):
        if not self.current():
            self.dz_status.set_label("Selecciona primero una canción de tu biblioteca")
            return
        i = self.idx
        threading.Thread(target=lambda: GLib.idle_add(self.apply_cover, i, deezer.download(r["cover"])), daemon=True).start()
