"""Estilo Apple Music "glass": tokens de Reparaciones.txt adaptados a CSS de GTK4.
GTK no soporta backdrop-filter, así que el desenfoque lo da la portada borrosa del fondo
y las capas translúcidas con brillo superior (inset) recrean el cristal.

El CSS es una plantilla: build_css(tema) la rellena con la paleta y la transparencia elegidas.
Con el tema por defecto el resultado es el mismo estilo de siempre."""
from string import Template

from .settings import PRESETS, rgb_of

TEMPLATE = Template("""
window.glass {
  background-image: linear-gradient(180deg, rgba($top_rgb,$op) 0%, rgba($bot_rgb,$op) 100%);
  color: $text;
  font-family: 'Inter', 'Ubuntu', sans-serif;
}
.shell { background: rgba(255,255,255,$a_shell); }
.sub, .crumb, .num { color: rgba($text_rgb,0.50); }
.nm { font-weight: 600; font-size: 13.5px; }

/* barra de título */
headerbar.glass-bar {
  background: rgba(255,255,255,$a_bar); border: none; border-bottom: 1px solid rgba(255,255,255,0.08);
  box-shadow: none; color: $text; min-height: 56px;
}
.brand { font-family: 'Instrument Serif', 'Playfair Display', serif; font-size: 22px; padding: 0 8px; }
.global-search {
  background: rgba(0,0,0,0.22); color: $text; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.08); min-width: 340px;
}

/* barra lateral */
.side { border-right: 1px solid rgba(255,255,255,0.08); padding: 14px 8px 14px 14px; }
.side-title { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; color: rgba($text_rgb,0.50); margin: 10px 8px 4px; }
button.side-item {
  background: transparent; background-image: none; border: none; box-shadow: none;
  border-radius: 8px; padding: 7px 10px; color: rgba($text_rgb,0.74); font-weight: 500; font-size: 13.5px;
}
button.side-item image { color: $accent; }
button.side-item:hover { background: rgba(255,255,255,0.06); color: $text; }
button.side-item.on {
  background-image: linear-gradient(180deg, rgba(255,255,255,0.18), rgba(255,255,255,0.06));
  color: $text; box-shadow: inset 0 1px 0 rgba(255,255,255,0.35);
}
entry.new-list { background: rgba(0,0,0,0.22); color: $text; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; margin-top: 8px; }

/* contenido */
.main { padding: 18px 22px 8px; }
.page-title { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; }
.crumb { font-size: 12px; letter-spacing: 0.04em; }
list, row { background: transparent; color: $text; }
.row-item { border-radius: 10px; padding: 7px 8px; }
.row-item:hover { background: rgba(255,255,255,0.06); }
.row-item.playing {
  background-image: linear-gradient(180deg, rgba($accent_rgb,0.16), rgba($accent_rgb,0.04));
  box-shadow: inset 0 0 0 1px rgba($accent_rgb,0.25);
}
.row-item.playing .num { color: $accent; }
.cv { border-radius: 8px; background: rgba(255,255,255,0.12); box-shadow: inset 0 1px 0 rgba(255,255,255,0.4); }

/* botones */
button.btn-primary {
  background-image: linear-gradient(180deg, #ffffff 0%, #d8e0e8 100%); color: #0a1018; border: none;
  border-radius: 999px; padding: 9px 18px; font-weight: 600;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), inset 0 -1px 0 rgba(0,0,0,0.18), 0 8px 20px -6px rgba(0,0,0,0.4);
}
button.btn-ghost { background: rgba(0,0,0,0.28); background-image: none; color: #fff; border: 1px solid rgba(255,255,255,0.32); border-radius: 999px; padding: 9px 18px; font-weight: 600; }
button.btn-ghost:hover { background: rgba(0,0,0,0.42); }
button.ibtn, button.heart, button.cbtn {
  background: transparent; background-image: none; border: none; box-shadow: none;
  color: rgba($text_rgb,0.55); border-radius: 8px;
}
button.ibtn:hover, button.cbtn:hover { color: $text; background: rgba(255,255,255,0.08); }
button.heart:hover, button.heart.on { color: $accent; }
button.cbtn { color: rgba($text_rgb,0.74); border-radius: 999px; min-width: 34px; min-height: 34px; }
button.play {
  background-image: linear-gradient(180deg, #ffffff, #cdd5dd); color: #0a1018; border-radius: 999px; border: none;
  min-width: 44px; min-height: 44px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), inset 0 -2px 4px rgba(0,0,0,0.18), 0 0 0 4px rgba(255,255,255,0.08), 0 8px 22px -6px rgba(0,0,0,0.55);
}
button.play:hover { background-image: linear-gradient(180deg, #ffffff, #e2e8ee); }

/* barra de reproducción */
.transport { border-top: 1px solid rgba(255,255,255,0.08); background: rgba(0,0,0,$a_transport); padding: 10px 22px; min-height: 88px; }
scale trough { background: rgba(255,255,255,0.12); min-height: 5px; border-radius: 999px; }
scale highlight { background-image: linear-gradient(90deg, #e8ecf0, #ffffff); border-radius: 999px; }
scale slider { background: #fff; min-width: 13px; min-height: 13px; border-radius: 999px; box-shadow: 0 4px 10px rgba(0,0,0,0.4); }

/* menús emergentes */
popover > contents {
  background: rgba(28,29,32,0.92); border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; padding: 6px;
  box-shadow: 0 8px 28px -6px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.08);
}
button.menu-item { background: transparent; background-image: none; border: none; box-shadow: none; color: $text; border-radius: 8px; padding: 8px 10px; font-weight: 500; }
button.menu-item:hover { background: rgba(255,255,255,0.08); }

/* ---------- modo móvil: ventana con forma de teléfono ---------- */
window.phone-win { background: transparent; background-image: none; box-shadow: none; }
.phone {
  background-image: linear-gradient(180deg, rgba($top_rgb,$op) 0%, rgba($bot_rgb,$op) 100%);
  border: 7px solid #050506; border-radius: 44px; color: $text;
  font-family: 'Inter', 'Ubuntu', sans-serif;
}
.phone .notch { background: #050506; border-radius: 999px; min-width: 88px; min-height: 22px; }
.phone .p-cover { border-radius: 22px; background: rgba(255,255,255,0.12);
  box-shadow: 0 18px 40px -12px rgba(0,0,0,0.65), inset 0 1px 0 rgba(255,255,255,0.4); }
.phone .p-title { font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }
.phone .p-artist { font-size: 14px; color: rgba($text_rgb,0.60); }
.phone .home-bar { background: rgba($text_rgb,0.55); border-radius: 999px; min-width: 120px; min-height: 5px; }
.phone button.p-ctl { min-width: 52px; min-height: 52px; }
.phone button.p-play { min-width: 68px; min-height: 68px; }
button.back-desktop {
  background: rgba(0,0,0,0.30); background-image: none; color: $text; border: 1px solid rgba(255,255,255,0.20);
  border-radius: 999px; padding: 3px 11px; font-size: 12px; font-weight: 600; box-shadow: none;
}
button.back-desktop:hover { background: rgba(0,0,0,0.45); }

/* ---------- panel «Personalizar estilo» ---------- */
window.style-panel { background: #1c1d20; color: #f6f8fb; font-family: 'Inter', 'Ubuntu', sans-serif; }
.panel-h { font-size: 20px; font-weight: 700; }
.panel-sec { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; color: rgba(246,248,251,0.50); }
.panel-hint { font-size: 12px; color: rgba(246,248,251,0.50); }
button.panel-btn {
  background: rgba(255,255,255,0.08); background-image: none; color: #f6f8fb; border: 1px solid rgba(255,255,255,0.14);
  border-radius: 999px; padding: 6px 14px; font-weight: 500; box-shadow: none;
}
button.panel-btn:hover { background: rgba(255,255,255,0.16); }
button.swatch { min-width: 30px; min-height: 30px; padding: 0; border-radius: 999px; border: 2px solid rgba(255,255,255,0.35); box-shadow: none; }
button.swatch:hover { border-color: #ffffff; }
""")


def swatch_css():
    """Un círculo por paleta: mitad color de fondo, mitad color de acento."""
    return "".join(
        f"button.swatch.sw{i} {{ background-image: linear-gradient(135deg, {p['bg_top']} 0%, {p['bg_top']} 50%, "
        f"{p['accent']} 50%, {p['accent']} 100%); }}\n" for i, p in enumerate(PRESETS))


def build_css(theme):
    op = 1 - theme["transparency"] / 100
    return TEMPLATE.substitute(
        accent=theme["accent"], accent_rgb=rgb_of(theme["accent"]),
        text=theme["text"], text_rgb=rgb_of(theme["text"]),
        top_rgb=rgb_of(theme["bg_top"]), bot_rgb=rgb_of(theme["bg_bottom"]),
        op=f"{op:.2f}",
        a_shell=f"{0.10 * op:.3f}", a_bar=f"{0.06 * op:.3f}", a_transport=f"{0.15 * op:.3f}",
    ) + swatch_css()
