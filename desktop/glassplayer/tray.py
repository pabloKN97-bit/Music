"""Icono de GlassPlayer en la barra superior de Ubuntu (StatusNotifier / AppIndicator).

Muestra el nombre de la canción junto al icono y, a su lado, tres botones de un solo clic
(⏮ Anterior · ⏯ Pausa/Reproducir · ⏭ Siguiente), como la barra de Spotify de escritorio: no hace falta abrir
ningún menú para encontrarlos. El menú del icono sigue existiendo (clic en el nombre).
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

# ---- botones de un solo clic: StatusNotifierItem propios, sin menú (clic = acción) ----
WATCHER = "org.kde.StatusNotifierWatcher"
SNI_IFACE = "org.kde.StatusNotifierItem"
SNI_PATH = "/StatusNotifierItem"
SNI_XML = """
<node>
 <interface name="org.kde.StatusNotifierItem">
  <property name="Category" type="s" access="read"/>
  <property name="Id" type="s" access="read"/>
  <property name="Title" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="WindowId" type="u" access="read"/>
  <property name="IconThemePath" type="s" access="read"/>
  <property name="IconName" type="s" access="read"/>
  <property name="IconPixmap" type="a(iiay)" access="read"/>
  <property name="OverlayIconName" type="s" access="read"/>
  <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionIconName" type="s" access="read"/>
  <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionMovieName" type="s" access="read"/>
  <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <property name="Menu" type="o" access="read"/>
  <method name="ContextMenu"><arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/></method>
  <method name="Activate"><arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/></method>
  <method name="SecondaryActivate"><arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/></method>
  <method name="Scroll"><arg type="i" direction="in" name="delta"/><arg type="s" direction="in" name="orientation"/></method>
  <signal name="NewTitle"/><signal name="NewIcon"/><signal name="NewAttentionIcon"/>
  <signal name="NewOverlayIcon"/><signal name="NewToolTip"/>
  <signal name="NewStatus"><arg type="s" name="status"/></signal>
 </interface>
</node>"""
V = GLib.Variant


class Button:
    """Icono de la barra superior que ejecuta una acción con un solo clic (sin menú).

    Es un StatusNotifierItem con su propia conexión y nombre D-Bus (como hacen Electron o Steam):
    ItemIsMenu=false hace que el clic izquierdo llame a Activate() en vez de abrir un menú.
    """
    count = 0

    def __init__(self, ident, title, icon, action):
        Button.count += 1
        self.ident, self.title, self.icon, self.action = ident, title, icon, action
        self.tip = ("", "")
        self.owned = self.host = self.sent = False  # nombre obtenido / host de iconos presente / ya registrado
        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-{Button.count}"
        addr = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        self.conn = Gio.DBusConnection.new_for_address_sync(
            addr, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None)
        node = Gio.DBusNodeInfo.new_for_xml(SNI_XML)
        self.conn.register_object(SNI_PATH, node.interfaces[0], self._call, self._get, None)
        Gio.bus_own_name_on_connection(self.conn, self.name, Gio.BusNameOwnerFlags.NONE, self._acquired, None)
        # el host de iconos (GNOME/KDE) puede aparecer después que nosotros: nos registramos cuando esté
        Gio.bus_watch_name_on_connection(self.conn, WATCHER, Gio.BusNameWatcherFlags.NONE,
                                         self._host_up, self._host_down)

    def _acquired(self, _conn, _name):
        self.owned = True
        self.register()

    def _host_up(self, *_a):
        self.host = True
        self.register()

    def _host_down(self, *_a):
        self.host = self.sent = False  # si el host reaparece, hay que registrarse de nuevo

    def register(self):
        if self.sent or not (self.owned and self.host):
            return
        self.sent = True
        self.conn.call(WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
                       V("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, 2000, None, self._registered)

    def _registered(self, conn, res):
        try:
            conn.call_finish(res)
        except GLib.Error:
            pass  # no hay host de iconos (GNOME sin la extensión AppIndicator): los botones no se ven

    def _get(self, _conn, _sender, _path, _iface, name):
        empty = V("a(iiay)", [])
        return {"Category": V("s", "ApplicationStatus"), "Id": V("s", self.ident), "Title": V("s", self.title),
                "Status": V("s", "Active"), "WindowId": V("u", 0), "IconThemePath": V("s", ""),
                "IconName": V("s", self.icon), "IconPixmap": empty, "OverlayIconName": V("s", ""),
                "OverlayIconPixmap": empty, "AttentionIconName": V("s", ""), "AttentionIconPixmap": empty,
                "AttentionMovieName": V("s", ""), "ToolTip": V("(sa(iiay)ss)", ("", [], *self.tip)),
                "ItemIsMenu": V("b", False), "Menu": V("o", "/NO_DMENU")}.get(name)

    def _call(self, _conn, _sender, _path, _iface, method, _params, inv):
        if method in ("Activate", "SecondaryActivate"):
            self.action()
        inv.return_value(None)

    def update(self, icon=None, title=None, tip=None):
        """Cambia icono / texto / tooltip y avisa al host."""
        if icon is not None and icon != self.icon:
            self.icon = icon
            self._emit("NewIcon")
        if title is not None:
            self.title = title
        if tip is not None and tip != self.tip:
            self.tip = tip
            self._emit("NewToolTip")

    def _emit(self, signal):
        try:
            self.conn.emit_signal(None, SNI_PATH, SNI_IFACE, signal, None)
        except GLib.Error:
            pass


def short(text, n=MAX_LABEL):
    return text if len(text) <= n else text[:n - 1] + "…"


class Tray:
    def __init__(self):
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.seen = False  # la app ya apareció en el bus (para no salir antes de que arranque)
        self.buttons = self.make_buttons()
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

    # ---- botones de un clic ----
    def make_buttons(self):
        """Orden en la barra, de izquierda a derecha: nombre · ⏮ · ⏯ · ⏭ (GNOME coloca cada icono nuevo a la
        izquierda de los anteriores, así que se registran al revés: siguiente, pausa, anterior, y al final el nombre)."""
        if os.environ.get("GLASSPLAYER_NO_TRAY_BUTTONS"):
            return {}
        try:
            return {
                "next": Button("glassplayer-next", "Siguiente", "media-skip-forward-symbolic",
                               lambda: self.call(PLAYER, "Next")),
                "play": Button("glassplayer-play", "Reproducir", "media-playback-start-symbolic",
                               lambda: self.call(PLAYER, "PlayPause")),
                "prev": Button("glassplayer-prev", "Anterior", "media-skip-backward-symbolic",
                               lambda: self.call(PLAYER, "Previous")),
            }
        except GLib.Error as e:
            print("GlassPlayer: botones de la barra superior no disponibles:", e, file=sys.stderr)
            return {}

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
        self.ind.set_label("", "")  # texto junto al icono, en la barra superior
        self.ind.set_title(full or "GlassPlayer")
        self.update_buttons(full, playing, props)

    def update_buttons(self, full, playing, props):
        b = self.buttons
        if not b:
            return
        song = full or "Nada en reproducción"
        b["play"].update(icon="media-playback-pause-symbolic" if playing else "media-playback-start-symbolic",
                         tip=("Pausa" if playing else "Reproducir", song))
        b["prev"].update(tip=("Anterior", song))
        b["next"].update(tip=("Siguiente", song))

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
