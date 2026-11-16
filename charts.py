import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from brand import ORANGE, INK, GREY, LINE, font_paths  # noqa: E402


def _font():
    reg, _ = font_paths()
    font_manager.fontManager.addfont(reg)
    return font_manager.FontProperties(fname=reg).get_name()


def chart_data(a, n=10):
    """(title, labels, ly, cy, has_ly): top distributors if we have them, else top items."""
    k, d = a["kpis"], a["distributors"]
    if not d.empty:
        d = d[d["segment"] != "Untapped"].head(n)
        return ("Top distributors: last year vs this year" if k["has_ly"] else f"Top distributors · {k['cy_label']}",
                d["distributor"].tolist(), d["ly_amt"].tolist(), d["cy_amt"].tolist(), k["has_ly"])
    p = a["products"].head(n)
    return (f"Top items · {k['cy_label']}", p["product"].tolist(), p["amount_LY"].tolist(),
            p["amount_CY"].tolist(), k["has_ly"])


def bars(labels, ly, cy, has_ly, width=7.2, height=3.0) -> bytes:
    plt.rcParams["font.family"] = _font()
    labels, ly, cy = labels[::-1], ly[::-1], cy[::-1]
    fig, ax = plt.subplots(figsize=(width, height), dpi=200)
    y = list(range(len(labels)))
    if has_ly:
        ax.barh([i + 0.2 for i in y], [v / 1e5 for v in ly], height=0.38, color="#C9C5C0", label="Last year")
        ax.barh([i - 0.2 for i in y], [v / 1e5 for v in cy], height=0.38, color=ORANGE, label="This year")
        ax.legend(fontsize=7, frameon=False, loc="lower right")
    else:
        ax.barh(y, [v / 1e5 for v in cy], height=0.6, color=ORANGE)
        for i, v in zip(y, cy):
            ax.text(v / 1e5, i, f" {v / 1e5:.1f}", va="center", fontsize=6.5, color=GREY)
    ax.set_yticks(y)
    ax.set_yticklabels([s[:26] for s in labels], fontsize=7, color=INK)
    ax.tick_params(axis="x", labelsize=7, colors=GREY)
    ax.set_xlabel("₹ lakh", fontsize=7, color=GREY)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.grid(axis="x", color=LINE, linewidth=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return buf.getvalue()


def cockpit_chart(a, n=8, width=4.6, height=2.6):
    title, labels, ly, cy, has_ly = chart_data(a, n)
    return title, bars(labels, ly, cy, has_ly, width, height)
