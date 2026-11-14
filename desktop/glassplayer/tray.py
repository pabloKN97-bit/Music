"""Icono de GlassPlayer en la barra superior de Ubuntu (StatusNotifier / AppIndicator).

Muestra el nombre de la canción junto al icono y, en su menú, Anterior / Pausa / Siguiente.
Corre como proceso aparte (lo lanza la app) porque AppIndicator usa GTK3 y la app usa GTK4, que no
pueden convivir en un mismo proceso. Habla con la app por MPRIS (D-Bus) y se cierra solo cuando
la app termina. Requiere el paquete gir1.2-ayatanaappindicator3-0.1.
"""
import os
import sys

try:
    import gi
    gi.require_version("Gtk", "3.0")
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator
    except (ValueError, ImportError):
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as AppIndicator
    from gi.repository import Gio, GLib, Gtk
except (ImportError, ValueError) as e:
    print("GlassPlayer: icono de la barra superior no disponible "
          "(instala gir1.2-ayatanaappindicator3-0.1):", e, file=sys.stderr)
    sys.exit(0)

BUS = "org.mpris.MediaPlayer2.glassplayer"
PATH = "/org/mpris/MediaPlayer2"
ROOT = "org.mpris.MediaPlayer2"
PLAYER = ROOT + ".Player"
PROPS = "org.freedesktop.DBus.Properties"
MAX_LABEL = 38


def short(text, n=MAX_LABEL):
    return text if len(text) <= n else text[:n - 1] + "…"


class Tray:
    def __init__(self):
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.seen = False  # la app ya apareció en el bus (para no salir antes de que arranque)
        self.ind = AppIndicator.Indicator.new("glassplayer", "com.pablo.glassplayer",
                                              AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        icons = os.path.join(GLib.get_user_data_dir(), "icons", "hicolor", "scalable", "apps")
        if os.path.isdir(icons):
            self.ind.set_icon_theme_path(icons)
        self.ind.set_title("GlassPlayer")
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.build_menu()
        self.conn.signal_subscribe(BUS, PROPS, "PropertiesChanged", PATH, None,
                                   Gio.DBusSignalFlags.NONE, lambda *_a: self.refresh())
        Gio.bus_watch_name_on_connection(self.conn, BUS, Gio.BusNameWatcherFlags.NONE,
                                         self.on_appeared, self.on_vanished)

    # ---- menú ----
    def item(self, text, cb=None):
        it = Gtk.MenuItem(label=text)
        if cb:
            it.connect("activate", lambda _i: cb())
        self.menu.append(it)
        return it

    def build_menu(self):
        self.menu = Gtk.Menu()
        self.i_title = self.item("Nada en reproducción")
        self.i_title.set_sensitive(False)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.i_prev = self.item("⏮  Anterior", lambda: self.call(PLAYER, "Previous"))
        self.i_play = self.item("▶  Reproducir", lambda: self.call(PLAYER, "PlayPause"))
        self.i_next = self.item("⏭  Siguiente", lambda: self.call(PLAYER, "Next"))
        self.menu.append(Gtk.SeparatorMenuItem())
        self.item("Abrir GlassPlayer", lambda: self.call(ROOT, "Raise"))
        self.item("Salir", lambda: self.call(ROOT, "Quit"))
        self.menu.show_all()
        self.ind.set_menu(self.menu)
        self.ind.set_secondary_activate_target(self.i_play)  # clic central = reproducir/pausa

    # ---- D-Bus ----
    def call(self, iface, method):
        self.conn.call(BUS, PATH, iface, method, None, None, Gio.DBusCallFlags.NONE, -1, None,
                       lambda c, r: self._finish(c, r))

    @staticmethod
    def _finish(conn, res):
        try:
            conn.call_finish(res)
        except GLib.Error:
            pass

    def refresh(self):
        self.conn.call(BUS, PATH, PROPS, "GetAll", GLib.Variant("(s)", (PLAYER,)),
                       GLib.VariantType("(a{sv})"), Gio.DBusCallFlags.NONE, 2000, None, self._got)

    def _got(self, conn, res):
        try:
            props = conn.call_finish(res).unpack()[0]
        except GLib.Error:
            return
        md = props.get("Metadata") or {}
        title = md.get("xesam:title") or ""
        artist = ", ".join(md.get("xesam:artist") or [])
        playing = props.get("PlaybackStatus") == "Playing"
        full = f"{title} — {artist}" if title and artist else title
        self.i_title.set_label("♪  " + short(full, 60) if full else "Nada en reproducción")
        self.i_play.set_label("⏸  Pausa" if playing else "▶  Reproducir")
        self.i_prev.set_sensitive(bool(props.get("CanGoPrevious")))
        self.i_next.set_sensitive(bool(props.get("CanGoNext")))
        label = short(title) if title else ""
        self.ind.set_label(label, label)  # texto junto al icono, en la barra superior

    def on_appeared(self, _conn, _name, _owner):
        self.seen = True
        self.refresh()

    def on_vanished(self, _conn, _name):
        if self.seen:  # la app se cerró: fuera el icono
            Gtk.main_quit()


def main():
    Tray()
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, 15, lambda: (Gtk.main_quit(), False)[1])  # SIGTERM
    Gtk.main()


if __name__ == "__main__":
    main()
