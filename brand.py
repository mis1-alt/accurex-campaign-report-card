"""Accurex Brand Guide v1.1 values shared by every output."""
import os
import re

ORANGE = "#F28421"      # primary
BLUE = "#0376BD"        # Clinical Blue, max ~15% of a layout
INK = "#231F20"         # text
GREY = "#6B6B6B"
LINE = "#E6E2DD"
SOFT = "#FDF1E6"        # orange tint for panels
WHITE = "#FFFFFF"

SEG_COLOURS = {          # segment -> (text colour, background)
    "Star": ("#1E7B34", "#E5F4E8"),
    "Growing": ("#0376BD", "#E3F1FA"),
    "New": ("#0376BD", "#E3F1FA"),
    "Declining": ("#B4561A", "#FCEBDC"),
    "Lost": ("#B3261E", "#FBE4E2"),
    "Untapped": ("#6B4FA0", "#EFEAF7"),
    "Anchor": ("#1E7B34", "#E5F4E8"),
    "Core": ("#0376BD", "#E3F1FA"),
    "Tail": ("#B4561A", "#FCEBDC"),
}
TONES = {"ink": INK, "good": "#1E7B34", "bad": "#B3261E", "blue": BLUE, "orange": ORANGE}

_D = os.path.dirname(os.path.abspath(__file__))
# works in the folder layout (reports/brand.py) and the flat layout (brand.py next to app.py)
HERE = _D if os.path.exists(os.path.join(_D, "app.py")) else os.path.dirname(_D)
LOGO = next((p for p in (os.path.join(HERE, "assets", "accurex_logo.png"), os.path.join(HERE, "accurex_logo.png"),
                         os.path.join(HERE, "accurex_logo (1).png")) if os.path.exists(p)),
            os.path.join(HERE, "assets", "accurex_logo.png"))


def font_paths():
    """DejaVu ships inside matplotlib, so it works on Streamlit Cloud and Windows alike
    (and has the ₹ glyph). Montserrat is used when present in assets/fonts."""
    mont = os.path.join(HERE, "assets", "fonts")
    if os.path.exists(os.path.join(mont, "Montserrat-Regular.ttf")):
        return (os.path.join(mont, "Montserrat-Regular.ttf"), os.path.join(mont, "Montserrat-Bold.ttf"))
    import matplotlib
    base = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    return os.path.join(base, "DejaVuSans.ttf"), os.path.join(base, "DejaVuSans-Bold.ttf")


def esc(s) -> str:
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md(s) -> str:
    """**bold** -> <b>bold</b>, everything else escaped (for reportlab Paragraphs)."""
    parts = esc(s).split("**")
    html = "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))
    return html.strip().replace("\n", "<br/>")


def plain(s) -> str:
    return re.sub(r"\*\*", "", str(s if s is not None else ""))
