"""MPRIS2 por D-Bus: GNOME muestra título, artista, portada y controles en la pantalla de
bloqueo, en el menú del sistema y responde a las teclas multimedia."""
import hashlib
import os

from gi.repository import Gio, GLib

PATH = "/org/mpris/MediaPlayer2"
XML = """
<node>
 <interface name="org.mpris.MediaPlayer2">
  <method name="Raise"/><method name="Quit"/>
  <property name="CanQuit" type="b" access="read"/>
  <property name="CanRaise" type="b" access="read"/>
  <property name="HasTrackList" type="b" access="read"/>
  <property name="Identity" type="s" access="read"/>
  <property name="DesktopEntry" type="s" access="read"/>
  <property name="SupportedUriSchemes" type="as" access="read"/>
  <property name="SupportedMimeTypes" type="as" access="read"/>
 </interface>
 <interface name="org.mpris.MediaPlayer2.Player">
  <method name="Next"/><method name="Previous"/><method name="Pause"/>
  <method name="PlayPause"/><method name="Stop"/><method name="Play"/>
  <method name="Seek"><arg direction="in" name="Offset" type="x"/></method>
  <method name="SetPosition"><arg direction="in" name="TrackId" type="o"/>
                              <arg direction="in" name="Position" type="x"/></method>
  <property name="PlaybackStatus" type="s" access="read"/>
  <property name="Metadata" type="a{sv}" access="read"/>
  <property name="LoopStatus" type="s" access="read"/>
  <property name="Shuffle" type="b" access="read"/>
  <property name="Position" type="x" access="read"/>
  <property name="Rate" type="d" access="read"/>
  <property name="MinimumRate" type="d" access="read"/>
  <property name="MaximumRate" type="d" access="read"/>
  <property name="Volume" type="d" access="read"/>
  <property name="CanGoNext" type="b" access="read"/>
  <property name="CanGoPrevious" type="b" access="read"/>
  <property name="CanPlay" type="b" access="read"/>
  <property name="CanPause" type="b" access="read"/>
  <property name="CanSeek" type="b" access="read"/>
  <property name="CanControl" type="b" access="read"/>
 </interface>
</node>"""

V = GLib.Variant


class Mpris:
    def __init__(self, app):
        self.app = app
        self.conn = None
        self._last = None
        self.node = Gio.DBusNodeInfo.new_for_xml(XML)
        Gio.bus_own_name(Gio.BusType.SESSION, "org.mpris.MediaPlayer2.glassplayer",
                         Gio.BusNameOwnerFlags.NONE, self._acquired, None, None)

    def _acquired(self, conn, name):
        self.conn = conn
        for ifc in self.node.interfaces:
            conn.register_object(PATH, ifc, self._call, self._get, None)

    # ---- estado ----
    @staticmethod
    def track_id(t):
        """Identificador estable de la pista (no cambia aunque cambie la lista o su posición)."""
        return "/com/pablo/glassplayer/track/" + hashlib.md5(t["uri"].encode()).hexdigest()[:16]

    @staticmethod
    def art_url(t):
        """Portada para el panel del sistema: la local; si aún no hay, la miniatura de YouTube; y si no, el icono de la app."""
        if t.get("cover") and os.path.exists(t["cover"]):
            return Gio.File.new_for_path(t["cover"]).get_uri()
        if t.get("thumb"):
            return t["thumb"]
        icon = os.path.join(GLib.get_user_data_dir(), "icons", "hicolor", "scalable", "apps", "com.pablo.glassplayer.svg")
        return Gio.File.new_for_path(icon).get_uri() if os.path.exists(icon) else None

    def _metadata(self):
        """Una sola pista: la que suena ahora (nunca la lista entera)."""
        t = self.app.current()
        if not t:
            return {}
        m = {"mpris:trackid": V("o", self.track_id(t)),
             "xesam:title": V("s", t["title"]),
             "xesam:artist": V("as", [t["artist"]]),
             "xesam:album": V("s", t.get("album") or "")}
        if t.get("duration", 0) > 0:
            m["mpris:length"] = V("x", int(t["duration"] * 1_000_000))
        art = self.art_url(t)
        if art:
            m["mpris:artUrl"] = V("s", art)
        return m

    def _player_props(self):
        a = self.app
        cur = a.current()
        status = "Playing" if a.playing else ("Paused" if cur else "Stopped")
        # Anterior/Siguiente siempre disponibles mientras haya una pista (con una sola canción, la reinician);
        # si no, GNOME oculta los botones del panel.
        return {"PlaybackStatus": V("s", status), "Metadata": V("a{sv}", self._metadata()),
                "LoopStatus": V("s", "None"), "Shuffle": V("b", False),
                "Position": V("x", a.position_us()), "Rate": V("d", 1.0), "MinimumRate": V("d", 1.0),
                "MaximumRate": V("d", 1.0), "Volume": V("d", 1.0),
                "CanGoNext": V("b", a.can_next()), "CanGoPrevious": V("b", a.can_prev()),
                "CanPlay": V("b", bool(a.queue or a.lib["tracks"])),
                "CanPause": V("b", True), "CanSeek": V("b", True), "CanControl": V("b", True)}

    def _root_props(self):
        return {"CanQuit": V("b", True), "CanRaise": V("b", True), "HasTrackList": V("b", False),
                "Identity": V("s", "GlassPlayer"), "DesktopEntry": V("s", "com.pablo.glassplayer"),
                "SupportedUriSchemes": V("as", ["file", "https"]),
                "SupportedMimeTypes": V("as", ["audio/mpeg"])}

    def _get(self, conn, sender, path, iface, name):
        props = self._player_props() if iface.endswith(".Player") else self._root_props()
        return props.get(name)

    def _call(self, conn, sender, path, iface, method, params, inv):
        a = self.app
        if iface.endswith(".Player"):
            if method == "PlayPause": a.toggle()
            elif method == "Play" and not a.playing: a.toggle()
            elif method == "Pause" and a.playing: a.toggle()
            elif method == "Next": a.go_next()
            elif method == "Previous": a.go_prev()
            elif method == "Stop": a.stop()
            elif method == "Seek": a.seek_rel(params.unpack()[0])
            elif method == "SetPosition":
                tid, pos = params.unpack()
                cur = a.current()
                if cur and tid == self.track_id(cur):
                    a.seek_to_us(pos)
        elif method == "Raise":
            a.show_window()
        elif method == "Quit":
            a.quit()
        inv.return_value(None)

    def notify(self):
        """Avisa a GNOME de que cambió la pista o el estado."""
        if not self.conn:
            return
        p = self._player_props()
        changed = {k: p[k] for k in ("PlaybackStatus", "Metadata", "CanGoNext", "CanGoPrevious", "CanPlay")}
        if self._last == (changed["PlaybackStatus"].unpack(), changed["Metadata"].unpack(), changed["CanGoNext"].unpack()):
            return  # nada nuevo: no se molesta a GNOME
        self._last = (changed["PlaybackStatus"].unpack(), changed["Metadata"].unpack(), changed["CanGoNext"].unpack())
        self.conn.emit_signal(None, PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                              V("(sa{sv}as)", ("org.mpris.MediaPlayer2.Player", changed, [])))
