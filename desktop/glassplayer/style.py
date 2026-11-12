"""Estilo Apple Music "glass": tokens de Reparaciones.txt adaptados a CSS de GTK4.
GTK no soporta backdrop-filter, así que el desenfoque lo da la portada borrosa del fondo
y las capas translúcidas con brillo superior (inset) recrean el cristal."""

CSS = """
window.glass {
  background-image: linear-gradient(180deg, #4d4d4f 0%, #0e0e10 100%);
  color: #f6f8fb;
  font-family: 'Inter', 'Ubuntu', sans-serif;
}
.shell { background: rgba(255,255,255,0.10); }
.sub, .crumb, .num { color: rgba(246,248,251,0.50); }
.nm { font-weight: 600; font-size: 13.5px; }

/* barra de título */
headerbar.glass-bar {
  background: rgba(255,255,255,0.06); border: none; border-bottom: 1px solid rgba(255,255,255,0.08);
  box-shadow: none; color: #f6f8fb; min-height: 56px;
}
.brand { font-family: 'Instrument Serif', 'Playfair Display', serif; font-size: 22px; padding: 0 8px; }
.global-search {
  background: rgba(0,0,0,0.22); color: #f6f8fb; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.08); min-width: 340px;
}

/* barra lateral */
.side { border-right: 1px solid rgba(255,255,255,0.08); padding: 14px 8px 14px 14px; }
.side-title { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; color: rgba(246,248,251,0.50); margin: 10px 8px 4px; }
button.side-item {
  background: transparent; background-image: none; border: none; box-shadow: none;
  border-radius: 8px; padding: 7px 10px; color: rgba(246,248,251,0.74); font-weight: 500; font-size: 13.5px;
}
button.side-item image { color: #ff5d8f; }
button.side-item:hover { background: rgba(255,255,255,0.06); color: #f6f8fb; }
button.side-item.on {
  background-image: linear-gradient(180deg, rgba(255,255,255,0.18), rgba(255,255,255,0.06));
  color: #f6f8fb; box-shadow: inset 0 1px 0 rgba(255,255,255,0.35);
}
entry.new-list { background: rgba(0,0,0,0.22); color: #f6f8fb; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; margin-top: 8px; }

/* contenido */
.main { padding: 18px 22px 8px; }
.page-title { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; }
.crumb { font-size: 12px; letter-spacing: 0.04em; }
list, row { background: transparent; }
.row-item { border-radius: 10px; padding: 7px 8px; }
.row-item:hover { background: rgba(255,255,255,0.06); }
.row-item.playing {
  background-image: linear-gradient(180deg, rgba(255,93,143,0.16), rgba(255,93,143,0.04));
  box-shadow: inset 0 0 0 1px rgba(255,93,143,0.25);
}
.row-item.playing .num { color: #ff5d8f; }
.cv { border-radius: 8px; background: rgba(255,255,255,0.12); box-shadow: inset 0 1px 0 rgba(255,255,255,0.4); }

/* botones */
button.btn-primary {
  background-image: linear-gradient(180deg, #ffffff 0%, #d8e0e8 100%); color: #0a1018; border: none;
  border-radius: 999px; padding: 9px 18px; font-weight: 600;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), inset 0 -1px 0 rgba(0,0,0,0.18), 0 8px 20px -6px rgba(0,0,0,0.4);
}
button.btn-ghost { background: rgba(0,0,0,0.28); background-image: none; color: #fff; border: 1px solid rgba(255,255,255,0.32); border-radius: 999px; padding: 9px 18px; font-weight: 600; }
button.ibtn, button.heart, button.cbtn {
  background: transparent; background-image: none; border: none; box-shadow: none;
  color: rgba(246,248,251,0.55); border-radius: 8px;
}
button.ibtn:hover, button.cbtn:hover { color: #f6f8fb; background: rgba(255,255,255,0.08); }
button.heart:hover, button.heart.on { color: #ff5d8f; }
button.cbtn { color: rgba(246,248,251,0.74); border-radius: 999px; min-width: 34px; min-height: 34px; }
button.play {
  background-image: linear-gradient(180deg, #ffffff, #cdd5dd); color: #0a1018; border-radius: 999px; border: none;
  min-width: 44px; min-height: 44px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), inset 0 -2px 4px rgba(0,0,0,0.18), 0 0 0 4px rgba(255,255,255,0.08), 0 8px 22px -6px rgba(0,0,0,0.55);
}
button.play:hover { background-image: linear-gradient(180deg, #ffffff, #e2e8ee); }

/* barra de reproducción */
.transport { border-top: 1px solid rgba(255,255,255,0.08); background: rgba(0,0,0,0.15); padding: 10px 22px; min-height: 88px; }
scale trough { background: rgba(255,255,255,0.12); min-height: 5px; border-radius: 999px; }
scale highlight { background-image: linear-gradient(90deg, #e8ecf0, #ffffff); border-radius: 999px; }
scale slider { background: #fff; min-width: 13px; min-height: 13px; border-radius: 999px; box-shadow: 0 4px 10px rgba(0,0,0,0.4); }

/* menús emergentes */
popover > contents {
  background: rgba(28,29,32,0.92); border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; padding: 6px;
  box-shadow: 0 8px 28px -6px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.08);
}
button.menu-item { background: transparent; background-image: none; border: none; box-shadow: none; color: #f6f8fb; border-radius: 8px; padding: 8px 10px; font-weight: 500; }
button.menu-item:hover { background: rgba(255,255,255,0.08); }
"""
