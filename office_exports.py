"""Editable versions: Word playbook and Excel action tracker."""
import io
import os
from datetime import date

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from core.analytics import inr, kpi_tiles
from . import brand as B
from .charts import bars, chart_data


def _rgb(h):
    h = h.lstrip("#")
    return RGBColor(int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16))


def _shade(cell, hexcol):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexcol.lstrip("#"))
    tcPr.append(shd)


def _runs(par, text, size=9.5, color=B.INK, bold=False):
    for i, part in enumerate(str(text or "").split("**")):
        r = par.add_run(part)
        r.bold = bold or bool(i % 2)
        r.font.size = Pt(size)
        r.font.color.rgb = _rgb(color)
        r.font.name = "Montserrat"


def _table(doc, header, rows, seg_col=None):
    t = doc.add_table(rows=1, cols=len(header))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.style = "Table Grid"
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        _shade(c, B.INK)
        _runs(c.paragraphs[0], h, 8.5, B.WHITE, True)
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r):
            colr = B.INK
            if seg_col == i and v in B.SEG_COLOURS:
                colr, bg = B.SEG_COLOURS[v]
                _shade(cells[i], bg)
            _runs(cells[i].paragraphs[0], v, 8.5, colr, seg_col == i)
    doc.add_paragraph()


def _h(doc, text, level=1):
    p = doc.add_paragraph()
    _runs(p, text, 14 if level == 1 else 11, B.INK if level == 1 else B.ORANGE, True)


def _bullets(doc, items):
    for it in items or []:
        _runs(doc.add_paragraph(style="List Bullet"), it)


def build_docx(brief, a, ai) -> bytes:
    plan, an, rs, cr, rv = (ai.get(k, {}) for k in ("plan", "analysis", "research", "creative", "review"))
    k = a["kpis"]
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Mm(16)
        s.top_margin = s.bottom_margin = Mm(14)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Montserrat", Pt(9.5)

    if os.path.exists(B.LOGO):
        doc.add_picture(B.LOGO, width=Mm(45))
    p = doc.add_paragraph()
    _runs(p, plan.get("campaign_name") or f"{brief['product']} campaign", 22, B.INK, True)
    _runs(doc.add_paragraph(), plan.get("motto", ""), 12, B.ORANGE, True)
    _runs(doc.add_paragraph(), f"{brief['product']} · {brief['camp_type']} · {brief['duration']} · "
                               f"{brief['stage']} · {date.today():%d %b %Y}", 8.5, B.GREY)

    _h(doc, "Campaign cockpit")
    tiles = kpi_tiles(k)
    _table(doc, [t[0] for t in tiles] + ["AI review"],
           [[t[1] for t in tiles] + [f"{rv.get('score', '–')}/10 {rv.get('verdict', '')}"]])
    _h(doc, "Management summary", 2)
    _bullets(doc, plan.get("management_summary"))
    title, labels, ly, cy, has_ly = chart_data(a)
    _runs(doc.add_paragraph(), title, 10, B.ORANGE, True)
    doc.add_picture(io.BytesIO(bars(labels, ly, cy, has_ly)), width=Mm(170))

    _h(doc, "1. Strategy")
    obj = plan.get("objective", {})
    _runs(doc.add_paragraph(), f"**Objective:** {obj.get('statement', '')}  **Target:** {obj.get('target_value', '')}")
    if an.get("headline"):
        _runs(doc.add_paragraph(), f"**What the data says:** {an['headline']}")
        _table(doc, ["Insight", "Detail", "So what"], [[i.get("title"), i.get("detail"), i.get("so_what")]
                                                       for i in an.get("insights", [])])
    nm = ai.get("naming", {})
    if nm.get("options"):
        _h(doc, "Campaign name options", 2)
        _table(doc, ["Name", "Tagline", "Why it fits", "Name check"],
               [[("★ " if o.get("name") == nm.get("chosen") else "") + str(o.get("name", "")), o.get("tagline"),
                 o.get("idea"), o.get("conflict_check")] for o in nm["options"]])
    if plan.get("decisions_needed"):
        _h(doc, "Decisions needed from management", 2)
        _table(doc, ["Decision", "Why", "Cost"], [[d.get("decision"), d.get("why"), d.get("cost")]
                                                for d in plan["decisions_needed"]])
    if ai.get("unverified"):
        _h(doc, "Unverified technical claims: PMT to confirm before use", 2)
        _table(doc, ["Where", "Claim"], [[u["where"], u["claim"]] for u in ai["unverified"]])
    _h(doc, "Technical USPs", 2)
    _table(doc, ["USP", "Proof", "Versus competitor"],
           [[u.get("usp"), u.get("proof"), u.get("vs_competitor")] for u in plan.get("technical_usps", [])])
    _h(doc, "Mechanics", 2)
    _table(doc, ["Mechanic", "How it works", "Owner"],
           [[m.get("name"), m.get("how_it_works"), m.get("owner")] for m in plan.get("mechanics", [])])
    inc = plan.get("incentive_scheme", {})
    if inc:
        _h(doc, f"Incentive scheme: {inc.get('type', '')}", 2)
        _table(doc, ["Slab", "Reward"], [[s.get("slab"), s.get("reward")] for s in inc.get("slabs", [])])
    _h(doc, "Phases", 2)
    _table(doc, ["Phase", "Weeks", "Focus", "Milestone"],
           [[p.get("phase"), p.get("weeks"), p.get("focus"), p.get("milestone")] for p in plan.get("phases", [])])
    fc = plan.get("forecast", {})
    if fc:
        _h(doc, "Expected outcome", 2)
        _table(doc, ["Conservative", "Target", "Stretch"], [[fc.get("conservative"), fc.get("target"), fc.get("stretch")]])
        _bullets(doc, fc.get("assumptions"))

    _h(doc, "2. Distributors and item mix")
    d = a["distributors"]
    if not d.empty and k["has_ly"]:
        _table(doc, ["Distributor", "HQ", "Segment", "LY", "CY", "Growth", "Target", "Gap"],
               [[r.distributor, r.hq or "–", r.segment, inr(r.ly_amt), inr(r.cy_amt), f"{r.growth_pct:+.1f}%",
                 inr(r.target_amt), inr(r.gap_amt)] for r in d.itertuples()], seg_col=2)
    elif not d.empty:
        _runs(doc.add_paragraph(), "No last-year data uploaded: distributors grouped by share of value.", 8.5, B.GREY)
        _table(doc, ["Distributor", "HQ", "Segment", "Units", "Value", "Share", "Target"],
               [[r.distributor, r.hq or "–", r.segment, f"{r.cy_qty:,.0f}", inr(r.cy_amt), f"{r.share_pct}%",
                 inr(r.target_amt)] for r in d.itertuples()], seg_col=2)
    if k["pull_through_per_unit"]:
        _runs(doc.add_paragraph(), f"Instruments **{k['instrument_units']:,.0f} units** · reagents **{inr(k['consumable_amt'])}** · "
                                   f"**{inr(k['pull_through_per_unit'])}** reagent per instrument placed")
    _table(doc, ["Item", "Type", "Units", "Value", "Share"],
           [[r.product, r.category, f"{r.qty_CY:,.0f}", inr(r.amount_CY), f"{r.share_pct}%"]
            for r in a["products"].head(30).itertuples()])
    _table(doc, ["Distributor", "Segment", "Action", "Owner", "By"],
           [[x.get("distributor"), x.get("segment"), x.get("action"), x.get("owner"), x.get("by_when")]
            for x in an.get("distributor_actions", [])], seg_col=1)

    _h(doc, "3. Execution checklist")
    _table(doc, ["Section", "Activity", "Doer", "Frequency", "Tool", "By", "KPI"],
           [[c.get("section"), c.get("activity"), c.get("doer"), c.get("frequency"), c.get("tool"),
             c.get("deadline"), c.get("kpi")] for c in plan.get("checklist", [])])
    _table(doc, ["KPI", "Target", "Frequency", "Source"],
           [[x.get("kpi"), x.get("target"), x.get("frequency"), x.get("source")] for x in plan.get("kpis", [])])

    _h(doc, "4. Competitors and market gaps")
    if rs.get("market_notes"):
        _runs(doc.add_paragraph(), rs["market_notes"])
    _table(doc, ["Company", "Product", "Price", "Key specs", "Positioning"],
           [[c.get("company"), c.get("product"), c.get("price"), c.get("key_specs"), c.get("positioning")]
            for c in rs.get("competitors", [])])
    _table(doc, ["Company", "Tactic", "Channel", "Why it works"],
           [[x.get("company"), x.get("tactic"), x.get("channel"), x.get("why_it_works")] for x in rs.get("industry_playbook", [])])
    _table(doc, ["Priority", "What others do", "Accurex today", "Recommendation"],
           [[g.get("priority"), g.get("what_others_do"), g.get("accurex_today"), g.get("recommendation")] for g in rs.get("gaps", [])])

    _h(doc, "5. Creative brief")
    _runs(doc.add_paragraph(), f"**Big idea:** {cr.get('big_idea', '')}")
    _runs(doc.add_paragraph(), f"**Key message:** {cr.get('key_message', '')}  **Tone:** {cr.get('tone', '')}")
    _runs(doc.add_paragraph(), "**Colours:** Accurex Orange #F28421 (primary) · Clinical Blue #0376BD (max 15%) · "
                               "Ink #231F20 · white space · Montserrat")
    for v in cr.get("verticals", []):
        _h(doc, f"{v.get('vertical', '')} · {v.get('audience', '')}", 2)
        _table(doc, ["Asset", "Size", "Headline", "Copy", "Visual & colours", "CTA / frequency"],
               [[f"{x.get('asset', '')} ({x.get('channel', '')})", x.get("size"), x.get("headline"), x.get("body_copy"),
                 f"{x.get('visual_direction', '')} {x.get('colours', '')}", f"{x.get('cta', '')} · {x.get('frequency', '')}"]
                for x in v.get("assets", [])])
    if cr.get("content_calendar"):
        _table(doc, ["Week", "What goes out"], [[c.get("week"), c.get("posts")] for c in cr["content_calendar"]])
    cd = cr.get("cockpit_design", {})
    if cd.get("zones"):
        _h(doc, "Cockpit design", 2)
        _table(doc, ["Zone", "Shows", "Visual", "Colour rule"],
               [[z.get("zone"), z.get("shows"), z.get("visual"), z.get("colour_rule")] for z in cd["zones"]])

    dr, c = ai.get("drip"), a.get("contacts")
    if dr or c:
        _h(doc, "Drip campaign to labs and hospitals")
        if c:
            _runs(doc.add_paragraph(), f"**{c['reachable']}** reachable of {c['total']} contacts · {len(c['invalid'])} invalid · "
                                       f"{len(c['duplicates'])} repeated numbers · {len(c['individuals'])} people's names to check")
        if dr:
            _runs(doc.add_paragraph(), dr.get("audience_summary", ""))
            _table(doc, ["Segment", "Who", "Approx.", "Angle"],
                   [[s.get("segment"), s.get("who"), s.get("approx_count"), s.get("angle")] for s in dr.get("segments", [])])
            _table(doc, ["#", "When", "Channel", "Objective", "Message", "Media", "CTA", "Owner"],
                   [[str(s.get("touch", "")), s.get("day"), s.get("channel"), s.get("objective"), s.get("message"),
                     s.get("media"), s.get("cta"), s.get("owner")] for s in dr.get("sequence", [])])
            _bullets(doc, dr.get("follow_up_rules"))
            _bullets(doc, dr.get("compliance"))
            _bullets(doc, dr.get("list_hygiene"))

    _h(doc, f"6. Director review: {rv.get('score', '–')}/10 · {rv.get('verdict', '')}")
    _table(doc, ["Area", "Issue", "Fix"], [[i.get("area"), i.get("issue"), i.get("fix")] for i in rv.get("issues", [])])
    _bullets(doc, rv.get("director_questions"))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_tracker(brief, a, ai) -> bytes:
    """Excel the team works from during the campaign: targets, actions, checklist, creatives."""
    plan, an, cr = ai.get("plan", {}), ai.get("analysis", {}), ai.get("creative", {})
    d = a["distributors"].copy()
    if not d.empty:
        d = d[["distributor", "hq", "segment", "cy_qty", "ly_amt", "cy_amt", "growth_pct", "target_amt", "gap_amt"]]
        d.columns = ["Distributor", "HQ", "Segment", "Units", "LY value", "CY value", "Growth %", "Target", "Gap"]
        if not a["kpis"]["has_ly"]:
            d = d.drop(columns=["LY value", "Growth %"])
        for w in ("Week 1", "Week 2", "Week 3", "Week 4"):
            d[f"{w} orders"] = None
        d["Remarks"] = None
    dr, c = ai.get("drip") or {}, a.get("contacts")
    contacts = pd.DataFrame()
    if c:
        contacts = c["table"].rename(columns={"name": "Name", "phone": "Mobile", "type": "Type", "valid_mobile": "Valid",
                                              "duplicate_phone": "Repeated", "send": "Send", "flag": "Check", "list": "List"})
        for s in dr.get("sequence", []):
            contacts[f"Touch {s.get('touch')} ({s.get('day')})"] = None
        contacts["Replied"] = None
        contacts["Outcome"] = None
    sheets = {
        "Distributor targets": d,
        "Item mix": a["products"],
        "Drip contacts": contacts,
        "Drip messages": pd.DataFrame(dr.get("sequence", [])),
        "Priority actions": pd.DataFrame([{**x, "Status": "Open"} for x in an.get("distributor_actions", [])]),
        "Checklist": pd.DataFrame([{**c, "Status": "Not started"} for c in plan.get("checklist", [])]),
        "KPIs": pd.DataFrame(plan.get("kpis", [])),
        "Creatives": pd.DataFrame([{"vertical": v.get("vertical"), **x, "Status": "To brief"}
                                   for v in cr.get("verticals", []) for x in v.get("assets", [])]),
    }
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            (df if not df.empty else pd.DataFrame({"info": ["No data"]})).to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            from openpyxl.styles import Font, PatternFill
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor=B.ORANGE.lstrip("#"))
            for col in ws.columns:
                width = min(60, max(10, max(len(str(c.value or "")) for c in col[:50]) + 2))
                ws.column_dimensions[col[0].column_letter].width = width
            ws.freeze_panes = "B2"
    return buf.getvalue()
