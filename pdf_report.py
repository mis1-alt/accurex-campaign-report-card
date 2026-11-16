"""
Branded PDF:
  Page 1   Campaign Cockpit  (one page for management)
  Then     Strategy, Distributor action plan, Execution checklist, Competitor & gaps,
           Creative brief, Director review
"""
import io
import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from core.analytics import inr, kpi_tiles
from . import brand as B
from .charts import cockpit_chart

W = 182 * mm - 12      # frame width minus reportlab's default 6pt frame padding each side
C = colors.HexColor
_FONTS = False


def _fonts():
    global _FONTS
    if not _FONTS:
        reg, bold = B.font_paths()
        pdfmetrics.registerFont(TTFont("Brand", reg))
        pdfmetrics.registerFont(TTFont("Brand-Bold", bold))
        pdfmetrics.registerFontFamily("Brand", normal="Brand", bold="Brand-Bold",
                                      italic="Brand", boldItalic="Brand-Bold")
        _FONTS = True


def S(size=8.5, color=B.INK, bold=False, align=0, leading=None, space=0):
    _fonts()   # fonts must exist before any Paragraph is created
    return ParagraphStyle("x", fontName="Brand-Bold" if bold else "Brand", fontSize=size,
                          leading=leading or size * 1.35, textColor=C(color), alignment=align,
                          spaceAfter=space)


def P(text, **kw):
    return Paragraph(B.md(text), S(**kw))


def h1(text):
    t = Table([[P(text, size=12, bold=True, color=B.INK)]], colWidths=[W])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 2, C(B.ORANGE)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return [Spacer(1, 6), t, Spacer(1, 6)]


def h2(text):
    return P(text, size=9.5, bold=True, color=B.ORANGE, space=3)


def table(header, rows, widths, seg_col=None, bold_col=None, font=7.6, fit=True):
    data = [[P(h, size=7.2, bold=True, color=B.WHITE) for h in header]]
    styles = []
    for i, r in enumerate(rows, start=1):
        cells = []
        for j, v in enumerate(r):
            colr = B.INK
            if seg_col is not None and j == seg_col and v in B.SEG_COLOURS:
                colr, bg = B.SEG_COLOURS[v]
                styles.append(("BACKGROUND", (j, i), (j, i), C(bg)))
            cells.append(P(v, size=font, color=colr, bold=(j == bold_col or (seg_col == j))))
        data.append(cells)
    if fit:
        widths = [w * W / sum(widths) for w in widths]   # exactly the content width
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C(B.INK)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C(B.WHITE), C("#FAF8F6")]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, C(B.LINE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ] + styles))
    return t


HALF = W / 2 - 8      # usable width inside a half-page column


def bullets(items, color=B.ORANGE, width=None, size=8.4):
    """width = the space the list actually sits in (full page by default, HALF inside two columns)."""
    width = width or W
    out = []
    for it in items or []:
        t = Table([[P("■", size=6, color=color), P(it, size=size, leading=size * 1.4)]],
                  colWidths=[5 * mm, width - 5 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
        out.append(t)
    return out


def panel(flowables, bg=B.SOFT, width=W):
    t = Table([[flowables]], colWidths=[width])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(bg)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _header_footer(brief, label="Campaign plan"):
    def draw(canv, doc):
        canv.saveState()
        canv.setFillColor(C(B.ORANGE))
        canv.rect(0, A4[1] - 4 * mm, A4[0], 4 * mm, stroke=0, fill=1)
        canv.setFont("Brand", 7)
        canv.setFillColor(C(B.GREY))
        canv.drawString(14 * mm, 8 * mm, f"Accurex Biomedical  |  {brief['product']} · {label}  |  Confidential, internal use")
        canv.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {doc.page}")
        canv.restoreState()
    return draw


# ── Page 1: cockpit ──────────────────────────────────────────────────────────
def cockpit(brief, a, ai, mode="full", level=0):
    """mode: full (cockpit + priority actions) | mgmt (no actions table) | header (title + tiles only)."""
    k, plan, review = a["kpis"], ai.get("plan", {}), ai.get("review", {})
    out = []
    title = [P(plan.get("campaign_name") or f"{brief['product']} Campaign", size=17, bold=True, leading=21),
             P(plan.get("motto", ""), size=9.5, color=B.ORANGE, bold=True),
             P(f"{brief['product']}  ·  {brief['camp_type']}  ·  {brief['duration']}  ·  "
               f"{brief['stage']}  ·  {date.today():%d %b %Y}", size=7.5, color=B.GREY)]
    logo = ""
    if os.path.exists(B.LOGO):
        iw, ih = ImageReader(B.LOGO).getSize()
        sc = min(40 * mm / iw, 13 * mm / ih)
        logo = Image(B.LOGO, iw * sc, ih * sc)
    hdr = Table([[title, logo]], colWidths=[W - 44 * mm, 44 * mm])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    out += [hdr, Spacer(1, 6)]

    # KPI tiles
    tiles = [(l, v, B.TONES[t]) for l, v, t in kpi_tiles(k)]
    cw = W / len(tiles)
    row1 = [P(t[0], size=6.8, color=B.GREY, bold=True) for t in tiles]
    row2 = [P(t[1], size=13, color=t[2], bold=True, leading=16) for t in tiles]
    kt = Table([row1, row2], colWidths=[cw] * len(tiles))
    kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(B.SOFT)),
                            ("LINEABOVE", (0, 0), (-1, 0), 2.5, C(B.ORANGE)),
                            ("LINEAFTER", (0, 0), (-2, -1), 0.8, C(B.WHITE)),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
    out += [kt, Spacer(1, 7)]
    if mode == "header":
        return out

    # Summary + review badge
    score = review.get("score", "–")
    verdict = review.get("verdict", "")
    badge_col = "#1E7B34" if str(score).replace(".", "").isdigit() and float(score) >= 7 else B.ORANGE
    n_sum, sum_cut = [(5, 400), (5, 220), (4, 180), (4, 150), (3, 130)][min(level, 4)]
    summary = [h2("Management summary")] + bullets([_cut(x, sum_cut) for x in plan.get("management_summary", [])[:n_sum]],
                                                   width=W - 40 * mm)
    badge = Table([[P("AI director review", size=7, color=B.WHITE, bold=True, align=TA_CENTER)],
                   [P(f"{score}/10", size=20, color=B.WHITE, bold=True, align=TA_CENTER, leading=24)],
                   [P(verdict, size=7.5, color=B.WHITE, align=TA_CENTER)]], colWidths=[34 * mm])
    badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(badge_col)),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    st = Table([[summary, badge]], colWidths=[W - 38 * mm, 38 * mm])   # summary sits in W-38mm; bullets use W-40mm
    st.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    out += [st, Spacer(1, 6)]

    # Chart + segments side by side
    chart_title, png = cockpit_chart(a)
    chart = Image(io.BytesIO(png), 108 * mm, 61 * mm)
    seg_rows = [[P("Segment", size=7, bold=True, color=B.GREY), P("Dist.", size=7, bold=True, color=B.GREY, align=TA_RIGHT),
                 P("Value", size=7, bold=True, color=B.GREY, align=TA_RIGHT)]]
    seg_style = []
    for i, r in enumerate(a["segments"].itertuples(), start=1):
        fg, bg = B.SEG_COLOURS.get(r.segment, (B.INK, B.WHITE))
        seg_rows.append([P(r.segment, size=7.8, bold=True, color=fg), P(f"{int(r.count)}", size=7.8, align=TA_RIGHT),
                         P(inr(r.cy_amt), size=7.8, align=TA_RIGHT)])
        seg_style.append(("BACKGROUND", (0, i), (0, i), C(bg)))
    sg = Table(seg_rows, colWidths=[30 * mm, 14 * mm, 26 * mm])
    sg.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, C(B.LINE)),
                            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)] + seg_style))
    if a["segments"].empty:
        p = a["products"].head(6)
        sg = table(["Item", "Value"], [[r.product[:30], inr(r.amount_CY)] for r in p.itertuples()],
                   [48 * mm, 22 * mm], font=7, fit=False)
    seg_block = [h2("Distributor segments" if not a["segments"].empty else "Top items"), sg]
    ct = Table([[[h2(chart_title), chart], seg_block]],
               colWidths=[110 * mm, W - 110 * mm])
    ct.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    out += [ct, Spacer(1, 4)]

    # Top actions this week
    acts = ai.get("analysis", {}).get("distributor_actions", [])[:6]
    if acts and mode == "full":
        out.append(h2("Priority actions"))
        out.append(table(["Distributor", "Segment", "Action", "Owner", "By"],
                         [[x.get("distributor"), x.get("segment"), x.get("action"), x.get("owner"), x.get("by_when")]
                          for x in acts],
                         [36 * mm, 20 * mm, 80 * mm, 30 * mm, 16 * mm], seg_col=1, bold_col=0, font=7.3))
    return out


# ── Following pages ──────────────────────────────────────────────────────────
def strategy(brief, a, ai):
    plan, an = ai.get("plan", {}), ai.get("analysis", {})
    out = h1("1. Strategy")
    obj = plan.get("objective", {})
    out.append(panel([P("Objective", size=8, bold=True, color=B.ORANGE),
                      P(obj.get("statement", ""), size=9.5, bold=True),
                      P(f"Target: **{obj.get('target_value', '')}**  ·  Measured by: {obj.get('measure', '')}", size=8)]))
    out.append(Spacer(1, 6))
    if an.get("headline"):
        out += [h2("What the data says"), P(an["headline"], size=8.8, bold=True, space=3)]
        out.append(table(["Insight", "Detail", "So what"],
                         [[i.get("title"), i.get("detail"), i.get("so_what")] for i in an.get("insights", [])],
                         [38 * mm, 78 * mm, 66 * mm], bold_col=0))
        out.append(Spacer(1, 6))
    out += [h2("Technical USPs")]
    out.append(table(["USP", "Proof", "Versus competitor"],
                     [[u.get("usp"), u.get("proof"), u.get("vs_competitor")] for u in plan.get("technical_usps", [])],
                     [50 * mm, 60 * mm, 72 * mm], bold_col=0))
    out += [Spacer(1, 6), h2("Campaign mechanics")]
    out.append(table(["Mechanic", "How it works", "Owner"],
                     [[m.get("name"), m.get("how_it_works"), m.get("owner")] for m in plan.get("mechanics", [])],
                     [42 * mm, 108 * mm, 32 * mm], bold_col=0))
    inc = plan.get("incentive_scheme", {})
    if inc:
        out += [Spacer(1, 6), h2(f"Incentive scheme: {inc.get('type', '')}")]
        out.append(table(["Slab", "Reward"], [[s.get("slab"), s.get("reward")] for s in inc.get("slabs", [])],
                         [70 * mm, 112 * mm], bold_col=0))
        if inc.get("budget_note"):
            out.append(P(inc["budget_note"], size=7.5, color=B.GREY))
    out += [Spacer(1, 6), h2("Phases")]
    out.append(table(["Phase", "Weeks", "Focus", "Milestone"],
                     [[p.get("phase"), p.get("weeks"), p.get("focus"), p.get("milestone")] for p in plan.get("phases", [])],
                     [34 * mm, 22 * mm, 70 * mm, 56 * mm], bold_col=0))
    fc = plan.get("forecast", {})
    if fc:
        out += [Spacer(1, 6), h2("Expected outcome")]
        ft = Table([[P("Conservative", size=7, color=B.GREY, bold=True), P("Target", size=7, color=B.GREY, bold=True),
                     P("Stretch", size=7, color=B.GREY, bold=True)],
                    [P(fc.get("conservative", ""), size=12, bold=True), P(fc.get("target", ""), size=12, bold=True, color=B.ORANGE),
                     P(fc.get("stretch", ""), size=12, bold=True, color="#1E7B34")]], colWidths=[W / 3] * 3)
        ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(B.SOFT)), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
        out.append(ft)
        out += bullets(fc.get("assumptions", []), color=B.GREY)
    if plan.get("competitor_response"):
        out += [Spacer(1, 6), h2("Answer to the strongest competitor"), P(plan["competitor_response"], size=8.4)]
    return out


def distributors(brief, a, ai):
    plan = ai.get("plan", {})
    k = a["kpis"]
    d = a["distributors"]
    out = [PageBreak()] + h1("2. Distributors and product mix" + (" (last year vs this year)" if k["has_ly"] else f" · {k['cy_label']}"))
    if not d.empty and k["has_ly"]:
        out.append(table(["Distributor", "HQ", "Segment", "LY value", "CY value", "Growth", "Target", "Gap"],
                         [[r.distributor, r.hq or "–", r.segment, inr(r.ly_amt), inr(r.cy_amt), f"{r.growth_pct:+.1f}%",
                           inr(r.target_amt), inr(r.gap_amt)] for r in d.itertuples()],
                         [42, 20, 20, 20, 20, 18, 21, 21], seg_col=2, bold_col=0, font=7.2))
    elif not d.empty:
        out.append(P("No last-year data was uploaded, so distributors are grouped by their share of value. "
                     "Upload last year's report to see growth.", size=7.8, color=B.GREY, space=3))
        out.append(table(["Distributor", "HQ", "Segment", "Units", "Value", "Share", "Target (+%.0f%%)" % k["target_growth_pct"]],
                         [[r.distributor, r.hq or "–", r.segment, f"{r.cy_qty:,.0f}", inr(r.cy_amt), f"{r.share_pct}%",
                           inr(r.target_amt)] for r in d.itertuples()],
                         [50, 20, 20, 16, 24, 16, 26], seg_col=2, bold_col=0, font=7.2))
    p = a["products"]
    if len(p):
        out += [Spacer(1, 6), h2("Item mix")]
        if k["pull_through_per_unit"]:
            out.append(P(f"Instruments **{k['instrument_units']:,.0f} units** ({inr(k['instrument_amt'])}) · reagents "
                         f"**{inr(k['consumable_amt'])}** ({k['consumable_share_pct']}% of value) · "
                         f"**{inr(k['pull_through_per_unit'])} reagent per instrument placed**", size=8.2, space=3))
        hdr = ["Item", "Type", "Units", "Value", "Share"] + (["LY value", "Growth"] if k["has_ly"] else [])
        rows = [[r.product, r.category, f"{r.qty_CY:,.0f}", inr(r.amount_CY), f"{r.share_pct}%"]
                + ([inr(r.amount_LY), f"{r.growth_pct:+.1f}%"] if k["has_ly"] else []) for r in p.head(30).itertuples()]
        out.append(table(hdr, rows, [64, 22, 16, 24, 16] + ([22, 18] if k["has_ly"] else []), bold_col=0, font=7.1))
    if not a["hq"].empty:
        out += [Spacer(1, 6), h2("By HQ")]
        out.append(table(["HQ", "Distributors", "LY value", "CY value", "Growth"],
                         [[r.hq, str(r.distributors), inr(r.ly_amt), inr(r.cy_amt), f"{r.growth_pct:+.1f}%"]
                          for r in a["hq"].itertuples()], [50 * mm, 30 * mm, 34 * mm, 34 * mm, 34 * mm], bold_col=0))
    segs = plan.get("target_segments", [])
    if segs:
        out += [Spacer(1, 6), h2("Play per segment")]
        out.append(table(["Segment", "Distributors", "Play", "Expected"],
                         [[s.get("segment"), ", ".join(s.get("distributors", [])[:8]), s.get("play"), s.get("expected_value")]
                          for s in segs], [22 * mm, 52 * mm, 82 * mm, 26 * mm], seg_col=0))
    return out


def execution(brief, a, ai):
    plan = ai.get("plan", {})
    out = [PageBreak()] + h1("3. Execution checklist")
    out.append(table(["Section", "Activity", "Doer", "Frequency", "Tool", "By", "KPI"],
                     [[c.get("section"), c.get("activity"), c.get("doer"), c.get("frequency"), c.get("tool"),
                       c.get("deadline"), c.get("kpi")] for c in plan.get("checklist", [])],
                     [24 * mm, 44 * mm, 26 * mm, 19 * mm, 24 * mm, 14 * mm, 31 * mm], bold_col=2, font=7))
    out += [Spacer(1, 6), h2("KPIs we track")]
    out.append(table(["KPI", "Target", "Frequency", "Data source"],
                     [[x.get("kpi"), x.get("target"), x.get("frequency"), x.get("source")] for x in plan.get("kpis", [])],
                     [60 * mm, 46 * mm, 30 * mm, 46 * mm], bold_col=0))
    return out


def market(brief, a, ai):
    r = ai.get("research", {})
    out = [PageBreak()] + h1("4. Competitors and market gaps")
    if r.get("market_notes"):
        out += [P(r["market_notes"], size=8.4, space=4)]
    out.append(table(["Company", "Product", "Price", "Key specs", "Positioning"],
                     [[c.get("company"), c.get("product"), c.get("price"), c.get("key_specs"), c.get("positioning")]
                      for c in r.get("competitors", [])],
                     [26 * mm, 30 * mm, 26 * mm, 56 * mm, 44 * mm], bold_col=0, font=7.2))
    out += [Spacer(1, 6), h2("How competitors run campaigns")]
    out.append(table(["Company", "Tactic", "Channel", "Why it works"],
                     [[x.get("company"), x.get("tactic"), x.get("channel"), x.get("why_it_works")]
                      for x in r.get("industry_playbook", [])], [28 * mm, 60 * mm, 30 * mm, 64 * mm], bold_col=0, font=7.2))
    out += [Spacer(1, 6), h2("What we are missing")]
    out.append(table(["Priority", "What others do", "Accurex today", "Recommendation"],
                     [[g.get("priority"), g.get("what_others_do"), g.get("accurex_today"), g.get("recommendation")]
                      for g in r.get("gaps", [])], [18 * mm, 54 * mm, 44 * mm, 66 * mm], bold_col=0, font=7.2))
    return out


def creative(brief, a, ai):
    cr = ai.get("creative", {})
    out = [PageBreak()] + h1("5. Creative brief for the Digital Marketing team")
    out.append(panel([P("Big idea", size=8, bold=True, color=B.ORANGE), P(cr.get("big_idea", ""), size=11, bold=True),
                      P(f"Key message: {cr.get('key_message', '')}", size=8.4),
                      P(f"Tone: {cr.get('tone', '')}", size=8, color=B.GREY)]))
    sw = Table([[P("", size=6), P("Accurex Orange #F28421 · primary", size=7.5),
                 P("", size=6), P("Clinical Blue #0376BD · max 15%", size=7.5),
                 P("", size=6), P("Ink #231F20 · text, Montserrat", size=7.5)]],
               colWidths=[6 * mm, 54 * mm, 6 * mm, 54 * mm, 6 * mm, W - 126 * mm])
    sw.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), C(B.ORANGE)), ("BACKGROUND", (2, 0), (2, 0), C(B.BLUE)),
                            ("BACKGROUND", (4, 0), (4, 0), C(B.INK)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    out += [Spacer(1, 4), sw, Spacer(1, 6)]
    for v in cr.get("verticals", []):
        block = [h2(f"{v.get('vertical', '')}  ·  {v.get('audience', '')}"),
                 P(f"Angle: {v.get('message_angle', '')}", size=8, color=B.GREY, space=2),
                 table(["Asset / size", "Headline & copy", "Visual & colours", "CTA / frequency"],
                       [[f"**{x.get('asset', '')}**\n{x.get('channel', '')}\n{x.get('size', '')}",
                         f"**{x.get('headline', '')}**\n{x.get('body_copy', '')}",
                         f"{x.get('visual_direction', '')}\n{x.get('colours', '')}",
                         f"{x.get('cta', '')}\n{x.get('frequency', '')} {('· ' + x['phase']) if x.get('phase') else ''}"]
                        for x in v.get("assets", [])], [34 * mm, 60 * mm, 56 * mm, 32 * mm], font=7)]
        out += [KeepTogether(block), Spacer(1, 5)]
    if cr.get("content_calendar"):
        out += [h2("Content calendar")]
        out.append(table(["Week", "What goes out"], [[c.get("week"), c.get("posts")] for c in cr["content_calendar"]],
                         [24 * mm, 158 * mm], bold_col=0))
    cd = cr.get("cockpit_design", {})
    if cd.get("zones"):
        out += [Spacer(1, 6), h2(f"Cockpit design (updated {cd.get('update_frequency', '')}, owner {cd.get('owner', '')})")]
        out.append(table(["Zone", "Shows", "Visual", "Colour rule"],
                         [[z.get("zone"), z.get("shows"), z.get("visual"), z.get("colour_rule")] for z in cd["zones"]],
                         [32 * mm, 66 * mm, 40 * mm, 44 * mm], bold_col=0))
    if cr.get("dos") or cr.get("donts"):
        dd = Table([[[h2("Do")] + bullets(cr.get("dos", []), "#1E7B34", width=HALF),
                     [h2("Don't")] + bullets(cr.get("donts", []), "#B3261E", width=HALF)]], colWidths=[W / 2, W / 2])
        dd.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        out += [Spacer(1, 6), dd]
    return out


def review_page(brief, a, ai):
    rv = ai.get("review", {})
    out = [PageBreak()] + h1(f"6. Director review: {rv.get('score', '–')}/10 · {rv.get('verdict', '')}")
    if rv.get("strengths"):
        out += [h2("Strengths")] + bullets(rv["strengths"], "#1E7B34")
    if rv.get("issues"):
        out += [Spacer(1, 4), h2("Issues and fixes")]
        out.append(table(["Area", "Issue", "Fix"], [[i.get("area"), i.get("issue"), i.get("fix")] for i in rv["issues"]],
                         [30 * mm, 74 * mm, 78 * mm], bold_col=0))
    if rv.get("director_questions"):
        out += [Spacer(1, 4), h2("Questions to prepare for")] + bullets(rv["director_questions"], B.BLUE)
    risks = ai.get("analysis", {}).get("risks", [])
    if risks:
        out += [Spacer(1, 4), h2("Risks")] + bullets(risks, B.ORANGE)
    return out


def drip_page(brief, a, ai):
    dr, c = ai.get("drip"), a.get("contacts")
    if not dr and not c:
        return []
    out = [PageBreak()] + h1("Drip campaign to labs and hospitals")
    if c:
        tiles = [("Contacts uploaded", f"{c['total']}"), ("Reachable (unique valid mobiles)", f"{c['reachable']}"),
                 ("Invalid numbers", f"{len(c['invalid'])}"), ("Repeated numbers", f"{len(c['duplicates'])}"),
                 ("Check: people's names", f"{len(c['individuals'])}")]
        t = Table([[P(l, size=6.8, bold=True, color=B.GREY) for l, _ in tiles],
                   [P(v, size=13, bold=True, color=B.INK) for _, v in tiles]], colWidths=[W / 5] * 5)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(B.SOFT)), ("LINEABOVE", (0, 0), (-1, 0), 2, C(B.BLUE)),
                               ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
        out += [t, Spacer(1, 4)]
        out.append(P("Reachable by type: " + " · ".join(f"**{k}** {v}" for k, v in c["by_type"].items()), size=8, space=4))
    if dr:
        if dr.get("audience_summary"):
            out.append(P(dr["audience_summary"], size=8.4, space=4))
        if dr.get("segments"):
            out.append(table(["Segment", "Who", "Approx.", "Angle"],
                             [[s.get("segment"), s.get("who"), s.get("approx_count"), s.get("angle")] for s in dr["segments"]],
                             [34, 62, 18, 68], bold_col=0, font=7.2))
        out += [Spacer(1, 6), h2("Message sequence")]
        out.append(table(["#", "When", "Channel", "Message", "Media", "CTA / owner"],
                         [[str(s.get("touch", "")), s.get("day"), s.get("channel"),
                           f"**{s.get('objective', '')}**\n{s.get('message', '')}", s.get("media"),
                           f"{s.get('cta', '')}\n{s.get('owner', '')}"] for s in dr.get("sequence", [])],
                         [7, 16, 20, 82, 27, 30], font=7))
        if dr.get("follow_up_rules"):
            out += [Spacer(1, 4), h2("When a lab replies")] + bullets(dr["follow_up_rules"], B.BLUE)
        if dr.get("kpis"):
            out += [Spacer(1, 4), h2("Drip KPIs")]
            out.append(table(["KPI", "Target"], [[x.get("kpi"), x.get("target")] for x in dr["kpis"]], [110, 72], bold_col=0))
        if dr.get("compliance") or dr.get("list_hygiene"):
            cc = Table([[[h2("Compliance")] + bullets(dr.get("compliance", []), B.GREY, width=HALF),
                         [h2("Fix the list before sending")] + bullets(dr.get("list_hygiene", []), B.ORANGE, width=HALF)]],
                       colWidths=[W / 2, W / 2])
            cc.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            out += [Spacer(1, 4), cc]
    if c and (c["invalid"] or c["duplicates"]):
        out += [Spacer(1, 4), h2("Contact list issues")]
        rows = [[x["name"], x["phone"], "Not a valid mobile"] for x in c["invalid"]] + \
               [[" / ".join(x["names"]), x["phone"], "Same number on several entries"] for x in c["duplicates"]]
        out.append(table(["Name", "Number", "Issue"], rows[:25], [100, 30, 52], font=7.2))
    return out


def _cut(s, n=150):
    s = str(s or "")
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


def naming_block(ai, compact=False):
    nm = ai.get("naming", {})
    opts = nm.get("options", [])
    if not opts:
        return []
    out = [h2("Campaign name options")]
    rows = [[("★ " if o.get("name") == nm.get("chosen") else "") + str(o.get("name", "")), o.get("tagline"),
             _cut(o.get("idea"), 90 if compact else 200)] + ([] if compact else [_cut(o.get("conflict_check"), 120)])
            for o in opts]
    out.append(table(["Name", "Tagline", "Why it fits"] + ([] if compact else ["Name check"]), rows,
                     [34, 54, 94] if compact else [30, 44, 66, 42], bold_col=0, font=7.1))
    if nm.get("why_chosen") and not compact:
        out.append(P(f"Chosen: **{nm.get('chosen')}**. {nm['why_chosen']}", size=7.8, color=B.GREY))
    return out


def management_page2(brief, a, ai, level=0):
    """level 0 = everything; each level up trims rows and text so the brief stays on 2 pages."""
    plan, rv, an = ai.get("plan", {}), ai.get("review", {}), ai.get("analysis", {})
    n_dec, n_ph, n_act, n_kpi, n_risk = [(3, 4, 5, 4, 3), (2, 3, 4, 4, 3), (2, 3, 4, 3, 2), (2, 0, 3, 3, 2)][min(level, 3)]
    cut = [110, 90, 80, 70][min(level, 3)]
    out = [PageBreak()] + h1("What management needs to know and decide")
    dec = plan.get("decisions_needed", [])
    if dec:
        out.append(table(["Decision needed", "Why", "Cost"], [[d.get("decision"), _cut(d.get("why"), cut), d.get("cost")]
                                                              for d in dec[:n_dec]], [70, 80, 32], bold_col=0, font=7.6))
        out.append(Spacer(1, 6))
    fc = plan.get("forecast", {})
    inc = plan.get("incentive_scheme", {})
    if fc:
        ft = Table([[P("Conservative", size=7, color=B.GREY, bold=True), P("Target", size=7, color=B.GREY, bold=True),
                     P("Stretch", size=7, color=B.GREY, bold=True), P("Budget", size=7, color=B.GREY, bold=True)],
                    [P(fc.get("conservative", ""), size=12, bold=True), P(fc.get("target", ""), size=12, bold=True, color=B.ORANGE),
                     P(fc.get("stretch", ""), size=12, bold=True, color="#1E7B34"),
                     P(_cut(inc.get("budget_note") or brief.get("budget") or "–", 70), size=7.6)]],
                   colWidths=[W * 0.22, W * 0.22, W * 0.22, W * 0.34])
        ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(B.SOFT)), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                ("LINEABOVE", (0, 0), (-1, 0), 2, C(B.ORANGE)), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        out += [h2("Expected outcome"), ft, Spacer(1, 6)]
    if plan.get("phases") and n_ph:
        out += [h2("Plan on a page")]
        out.append(table(["Phase", "Weeks", "Milestone"], [[p.get("phase"), p.get("weeks"), _cut(p.get("milestone"), cut)]
                                                          for p in plan["phases"][:n_ph]], [44, 24, 114], bold_col=0, font=7.4))
        out.append(Spacer(1, 6))
    acts = an.get("distributor_actions", [])[:n_act]
    if acts:
        out += [h2(f"Top {len(acts)} actions")]
        out.append(table(["Distributor", "Action", "Owner", "By"],
                         [[x.get("distributor"), _cut(x.get("action"), cut), x.get("owner"), x.get("by_when")] for x in acts],
                         [44, 96, 30, 12], bold_col=0, font=7.2))
        out.append(Spacer(1, 6))
    kp = plan.get("kpis", [])[:n_kpi]
    side = []
    if kp:
        side = [h2("KPIs to watch")] + bullets([f"**{x.get('kpi')}**: {_cut(x.get('target'), 40)} ({x.get('frequency', '')})"
                                                for x in kp], B.BLUE, width=HALF, size=8)
    risk = [h2(f"Risks · AI review {rv.get('score', '–')}/10")] + bullets(
        [_cut(x, cut) for x in (an.get("risks", []) + [i.get("issue") for i in rv.get("issues", [])])[:n_risk]],
        B.ORANGE, width=HALF, size=8)
    two = Table([[side, risk]], colWidths=[W / 2, W / 2])
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    out += [two, Spacer(1, 4)]
    nm = ai.get("naming", {})
    if level <= 1:
        out += naming_block(ai, compact=True)
    elif nm.get("options"):
        others = ", ".join(o.get("name", "") for o in nm["options"] if o.get("name") != nm.get("chosen"))
        out.append(P(f"**Campaign name:** {nm.get('chosen')}. Other options: {others}. Details in the Team Playbook.",
                     size=7.8, space=3))
    unv = ai.get("unverified") or []
    if unv:
        out.append(P(f"**{len(unv)} technical claim(s) are unverified** and must be confirmed by PMT before any "
                     f"creative goes out. See the Team Playbook.", size=7.6, color="#B3261E"))
    return out


def unverified_block(ai):
    unv = ai.get("unverified") or []
    if not unv:
        return []
    out = [Spacer(1, 6), h2(f"⚠ {len(unv)} unverified technical claims: PMT to confirm before use")]
    out.append(table(["Where", "Claim"], [[u["where"], u["claim"]] for u in unv[:25]], [120, 62], font=7))
    return out


def _doc(brief, label, story):
    _fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=10 * mm,
                            bottomMargin=14 * mm, title=f"{brief['product']} · {label}",
                            author="Accurex AI Marketing Manager")
    hf = _header_footer(brief, label)
    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()


def page_count(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")


def build_management(brief, a, ai) -> bytes:
    """Bird's-eye view for directors: always 2 pages. Trims itself until it fits."""
    for level in range(5):
        pdf = _doc(brief, "Management brief", cockpit(brief, a, ai, mode="mgmt", level=level)
                   + management_page2(brief, a, ai, level))
        if page_count(pdf) <= 2:
            return pdf
    return pdf


def build_playbook(brief, a, ai) -> bytes:
    """Working document for the marketing team: everything needed to execute."""
    story = cockpit(brief, a, ai, mode="header") + strategy(brief, a, ai) + naming_block(ai) + unverified_block(ai) \
        + distributors(brief, a, ai) + execution(brief, a, ai) + market(brief, a, ai) + creative(brief, a, ai) \
        + drip_page(brief, a, ai) + review_page(brief, a, ai)
    return _doc(brief, "Team playbook", story)


def build_pdf(brief, a, ai, cockpit_only=False) -> bytes:
    _fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=10 * mm, bottomMargin=14 * mm,
                            title=f"{brief['product']} campaign", author="Accurex AI Marketing Manager")
    story = cockpit(brief, a, ai)
    if not cockpit_only:
        story += [PageBreak()] + strategy(brief, a, ai) + distributors(brief, a, ai) + execution(brief, a, ai) \
            + market(brief, a, ai) + creative(brief, a, ai) + drip_page(brief, a, ai) + review_page(brief, a, ai)
    hf = _header_footer(brief)
    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()
