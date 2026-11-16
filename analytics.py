"""All arithmetic lives here, in plain pandas. The AI only interprets these numbers.

Works with whatever the files contain:
  - last year + this year  -> growth, targets vs last year, Star/Growing/Declining/Lost/New
  - this period only       -> share-based Anchor/Core/Tail, targets as uplift on this period
  - instruments + reagents -> reagent pull-through per instrument placed
  - contact lists          -> reachable audience, data-quality flags, customer types
"""
from __future__ import annotations

import re

import pandas as pd

SEGMENTS = {
    "Star":      "Growing fast (+15% or more over last year). Protect and use as a reference.",
    "Growing":   "Growing, below +15%. Push for the next slab.",
    "Declining": "Selling less than last year. Recovery plan needed.",
    "Lost":      "Bought last year, nothing this year. Win back.",
    "New":       "No purchase last year, buying now. Nurture.",
    "Anchor":    "Top distributors making up the first 50% of value. Protect and grow.",
    "Core":      "Next tier, up to 80% of value. Main growth pool.",
    "Tail":      "Smallest 20% of value. Activate or consolidate.",
    "Untapped":  "Active with Accurex on other products, has never bought this one. Cross-sell.",
}
SEG_ORDER = list(SEGMENTS)


_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"


def short_period(text: str) -> str:
    """'April 2026 - October 2026' -> 'Apr–Oct 2026'; 'April 2025 to March 2026' -> 'Apr 2025–Mar 2026'."""
    t = str(text or "").strip()
    m = re.search(rf"{_MON}[\s,]*'?(\d{{2,4}})?\s*(?:-|–|—|to|till|until)\s*{_MON}[\s,]*'?(\d{{2,4}})", t, re.I)
    if not m:
        return t
    m1, y1, m2, y2 = m.group(1).title(), m.group(2), m.group(3).title(), m.group(4)
    y2 = y2 if len(y2) == 4 else "20" + y2
    if not y1 or (y1 if len(y1) == 4 else "20" + y1) == y2:
        return f"{m1}–{m2} {y2}"
    return f"{m1} {y1 if len(y1) == 4 else '20' + y1}–{m2} {y2}"


def _pct(cy, ly):
    if ly:
        return round((cy - ly) / ly * 100, 1)
    return 100.0 if cy else 0.0


def _growth_segment(ly, cy):
    if ly > 0 and cy == 0:
        return "Lost"
    if ly == 0 and cy > 0:
        return "New"
    g = _pct(cy, ly)
    return "Star" if g >= 15 else "Growing" if g >= 0 else "Declining"


def analyse(tidy: pd.DataFrame, products: list[str], target_growth_pct: float = 20.0,
            hq_map: dict | None = None, periods: dict | None = None, contacts: pd.DataFrame | None = None) -> dict:
    hq_map = {k.strip().lower(): v for k, v in (hq_map or {}).items()}
    periods = periods or {}
    camp = tidy[tidy["product"].isin(products)]
    if camp.empty:
        raise ValueError("No sales found for the selected items.")
    has_ly = bool((camp["period"] == "LY").any())
    g = target_growth_pct / 100

    # ── distributors ──
    named = tidy[tidy["distributor"] != ""]
    rows = []
    for d in sorted(named["distributor"].unique()):
        mine = camp[camp["distributor"] == d]
        s = lambda col, per: float(mine.loc[mine.period == per, col].sum())  # noqa: E731
        ly_a, cy_a, ly_q, cy_q = s("amount", "LY"), s("amount", "CY"), s("qty", "LY"), s("qty", "CY")
        inst_units = float(mine.loc[(mine.period == "CY") & (mine.category == "instrument"), "qty"].sum())
        other = float(named[(named.distributor == d) & (~named["product"].isin(products))]["amount"].sum())
        if ly_a == 0 and cy_a == 0:
            if other <= 0:
                continue
            seg = "Untapped"
        else:
            seg = _growth_segment(ly_a, cy_a) if has_ly else None
        hqs = named.loc[(named.distributor == d) & (named.hq != ""), "hq"]
        hq = hq_map.get(d.strip().lower()) or (hqs.iloc[0] if len(hqs) else "")
        base = max(ly_a, cy_a) if has_ly else cy_a
        target = round(base * (1 + g)) if has_ly else round(cy_a * (1 + g))
        rows.append({"distributor": d, "hq": hq, "segment": seg, "ly_qty": ly_q, "cy_qty": cy_q,
                     "ly_amt": ly_a, "cy_amt": cy_a, "growth_pct": _pct(cy_a, ly_a) if has_ly else None,
                     "instrument_units": inst_units, "target_amt": target,
                     "gap_amt": max(0, target - cy_a), "other_products_amt": other})
    dist = pd.DataFrame(rows, columns=["distributor", "hq", "segment", "ly_qty", "cy_qty", "ly_amt", "cy_amt",
                                       "growth_pct", "instrument_units", "target_amt", "gap_amt", "other_products_amt"])
    if not dist.empty:
        dist = dist.sort_values(["cy_amt", "ly_amt"], ascending=False).reset_index(drop=True)
        tot = dist["cy_amt"].sum()
        dist["share_pct"] = (dist["cy_amt"] / tot * 100).round(1) if tot else 0.0
        if not has_ly:
            cum = dist["cy_amt"].cumsum() / tot if tot else 0
            prev = cum.shift(fill_value=0)
            dist["segment"] = [s if s == "Untapped" else ("Anchor" if p < 0.5 else "Core" if p < 0.8 else "Tail")
                               for s, p in zip(dist["segment"], prev)]

    # ── totals and mix ──
    tot = lambda per, cat=None: float(camp.loc[(camp.period == per) & ((camp.category == cat) if cat else True), "amount"].sum())  # noqa: E731
    units = lambda per: float(camp.loc[(camp.period == per) & (camp.category == "instrument"), "qty"].sum())  # noqa: E731
    ly_amt, cy_amt = tot("LY"), tot("CY")
    inst_cy, cons_cy, units_cy = tot("CY", "instrument"), tot("CY", "consumable"), units("CY")
    inst_ly, cons_ly, units_ly = tot("LY", "instrument"), tot("LY", "consumable"), units("LY")

    prod = (camp.groupby(["product", "category", "period"])[["qty", "amount"]].sum().unstack("period", fill_value=0))
    prod.columns = [f"{a}_{b}" for a, b in prod.columns]
    for c in ("qty_LY", "qty_CY", "amount_LY", "amount_CY"):
        if c not in prod:
            prod[c] = 0.0
    prod = prod.reset_index()
    prod["growth_pct"] = [(_pct(c, l) if has_ly else None) for l, c in zip(prod["amount_LY"], prod["amount_CY"])]
    prod["share_pct"] = (prod["amount_CY"] / cy_amt * 100).round(1) if cy_amt else 0.0
    prod = prod.sort_values("amount_CY", ascending=False).reset_index(drop=True)

    seg = pd.DataFrame(columns=["segment", "count", "ly_amt", "cy_amt"])
    if not dist.empty:
        seg = (dist.groupby("segment").agg(count=("distributor", "count"), ly_amt=("ly_amt", "sum"),
                                           cy_amt=("cy_amt", "sum")).reindex(SEG_ORDER).dropna(how="all")
               .fillna(0).reset_index())
        seg["count"] = seg["count"].astype(int)

    hq_df = pd.DataFrame()
    if not dist.empty and (dist["hq"] != "").any():
        hq_df = dist.groupby("hq").agg(ly_amt=("ly_amt", "sum"), cy_amt=("cy_amt", "sum"),
                                       distributors=("distributor", "count")).reset_index()
        hq_df["growth_pct"] = [(_pct(c, l) if has_ly else None) for l, c in zip(hq_df.ly_amt, hq_df.cy_amt)]
        hq_df = hq_df.sort_values("cy_amt", ascending=False)

    target_amt = round((ly_amt if has_ly else cy_amt) * (1 + g))
    kpis = {
        "has_ly": has_ly, "ly_label": short_period(periods.get("LY", "Last year")),
        "cy_label": short_period(periods.get("CY", "This year")),
        "ly_amt": ly_amt, "cy_amt": cy_amt, "growth_pct": _pct(cy_amt, ly_amt) if has_ly else None,
        "ly_qty": float(camp.loc[camp.period == "LY", "qty"].sum()), "cy_qty": float(camp.loc[camp.period == "CY", "qty"].sum()),
        "target_growth_pct": target_growth_pct, "target_amt": target_amt,
        "target_basis": "last year" if has_ly else "this period",
        "gap_amt": max(0, target_amt - cy_amt) if has_ly else round(cy_amt * g),
        "instrument_units": units_cy, "instrument_amt": inst_cy, "consumable_amt": cons_cy,
        "pull_through_per_unit": round(cons_cy / units_cy) if units_cy else None,
        "consumable_share_pct": round(cons_cy / cy_amt * 100, 1) if cy_amt else 0,
        "ly_instrument_units": units_ly, "ly_consumable_amt": cons_ly, "ly_instrument_amt": inst_ly,
        "distributors_total": int((dist["segment"] != "Untapped").sum()) if not dist.empty else 0,
        "distributors_active": int((dist["cy_amt"] > 0).sum()) if not dist.empty else 0,
        "untapped_count": int((dist["segment"] == "Untapped").sum()) if not dist.empty else 0,
        "top3_share_pct": round(dist["cy_amt"].head(3).sum() / dist["cy_amt"].sum() * 100, 1)
        if not dist.empty and dist["cy_amt"].sum() else None,
        "top_distributor": dist.iloc[0]["distributor"] if not dist.empty else None,
        "line_items": len(products),
        "has_consumables_by_distributor": bool(((camp.category == "consumable") & (camp.distributor != "")).any()),
    }
    out = {"kpis": kpis, "distributors": dist, "segments": seg, "products": prod, "hq": hq_df}
    if contacts is not None and len(contacts):
        out["contacts"] = analyse_contacts(contacts)
        kpis["contacts_reachable"] = out["contacts"]["reachable"]
    return out


# ── Contacts ─────────────────────────────────────────────────────────────────
TYPE_RULES = [
    ("Pathology lab", r"\blab\b|labs\b|patho|laborator|janch|path ?lab|pathcare|biopsy"),
    ("Diagnostic / imaging centre", r"diagnost|digonast|digonest|x[ -]?ray|scan|imaging|radio"),
    ("Hospital / nursing home", r"hospital|nursing|hosp\b|medical college|institute|medical centre|medical center|sevashram|arogyamandir|gmch|aims\b|trihms"),
    ("Clinic / polyclinic", r"clinic|polyclinic|care|diabet|health|medicare|sadan"),
    ("Trade / distributor", r"enterprise|agenc|biomedical|\bltd\b|\bllp\b|chemical|surgical|closures|services|traders|nbd"),
]
ORG_WORDS = re.compile("|".join(r for _, r in TYPE_RULES) + r"|trust|samit|club|centre|center|\bdr\b|doctor|medi|"
                       r"pvt|dispensary|setup|\bhosp", re.I)


def _norm_phone(p: str) -> str:
    p = re.sub(r"\D", "", str(p or ""))
    if len(p) == 12 and p.startswith("91"):
        p = p[2:]
    if len(p) == 11 and p.startswith("0"):
        p = p[1:]
    return p


def analyse_contacts(c: pd.DataFrame) -> dict:
    df = c.copy()
    df["phone"] = df["phone"].map(_norm_phone)
    df["valid_mobile"] = df["phone"].str.fullmatch(r"[6-9]\d{9}")
    df["type"] = [next((t for t, rx in TYPE_RULES if re.search(rx, n, re.I)), "Individual / unclear") for n in df["name"]]
    df["individual"] = [not ORG_WORDS.search(n) and len(n.split()) <= 3 for n in df["name"]]
    df.loc[df["individual"], "type"] = "Individual / unclear"
    dup = df[df["phone"] != ""].groupby("phone")["name"].apply(list)
    dup = {p: n for p, n in dup.items() if len(n) > 1}
    df["duplicate_phone"] = df["phone"].isin(dup)
    # one message per number: first occurrence of each valid number
    # people's names stay in (often the team's own test numbers) but are flagged for a check
    df["send"] = df["valid_mobile"] & ~df.duplicated("phone")
    flags = []
    for r in df.itertuples():
        f = []
        if not r.valid_mobile:
            f.append("not a valid mobile")
        if r.duplicate_phone:
            f.append("shared number")
        if r.individual:
            f.append("looks like a person's name: check if internal/test number")
        flags.append("; ".join(f))
    df["flag"] = flags
    return {
        "total": len(df), "reachable": int(df["send"].sum()),
        "invalid": df.loc[~df.valid_mobile, ["name", "phone"]].to_dict("records"),
        "duplicates": [{"phone": p, "names": n} for p, n in dup.items()],
        "individuals": df.loc[df.individual, "name"].tolist(),
        "by_type": df[df.send].groupby("type").size().sort_values(ascending=False).to_dict(),
        "table": df[["name", "phone", "type", "valid_mobile", "duplicate_phone", "send", "flag", "list"]],
    }


# ── Facts for the AI ─────────────────────────────────────────────────────────
def facts_for_ai(a: dict, max_rows: int = 40) -> str:
    k = a["kpis"]
    L = ["UNITS: money is in Indian rupees, already converted: L = lakh (1,00,000), Cr = crore (1,00,00,000 = 100 L). "
         "Quote these figures as written."]
    if k["has_ly"]:
        L += [f"PERIODS: last year = {k['ly_label']}, this year = {k['cy_label']}",
              f"TOTAL campaign value: LY {inr(k['ly_amt'])} -> CY {inr(k['cy_amt'])} ({k['growth_pct']:+}%)",
              f"Target at +{k['target_growth_pct']}% over last year: {inr(k['target_amt'])}; gap to close: {inr(k['gap_amt'])}"]
    else:
        L += [f"PERIOD: only one period in the data ({k['cy_label']}). NO last-year data, so no growth figures exist; "
              f"do not invent any.",
              f"TOTAL campaign value in the period: {inr(k['cy_amt'])}",
              f"Uplift target +{k['target_growth_pct']}% for the campaign period: {inr(k['target_amt'])} "
              f"({inr(k['gap_amt'])} extra)"]
    if k["instrument_units"] or k["consumable_amt"]:
        L.append(f"MIX (this period): instruments {k['instrument_units']:,.0f} units = {inr(k['instrument_amt'])}; "
                 f"reagents/consumables {inr(k['consumable_amt'])} ({k['consumable_share_pct']}% of value)")
        if k["pull_through_per_unit"]:
            L.append(f"Reagent pull-through: {inr(k['pull_through_per_unit'])} of reagents per instrument placed in the period "
                     f"(only meaningful as an indicator: reagents also go to older installations)")
        if not k["has_consumables_by_distributor"]:
            L.append("Reagent sales are available only as product totals, not per distributor.")
    d = a["distributors"]
    if not d.empty:
        L.append(f"\nDISTRIBUTORS: {k['distributors_active']} active; top 3 hold {k['top3_share_pct']}% of value; "
                 f"untapped (buy other Accurex products, not this): {k['untapped_count']}")
        L.append("SEGMENTS: " + "; ".join(f"{r.segment}={int(r['count'])}" for _, r in a["segments"].iterrows()))
        if k["has_ly"]:
            L.append("name | HQ | segment | LY | CY | growth% | target | gap Rs")
            for r in d.head(max_rows).itertuples():
                L.append(f"{r.distributor} | {r.hq or '-'} | {r.segment} | {inr(r.ly_amt)} | {inr(r.cy_amt)} | "
                         f"{r.growth_pct:+} | {inr(r.target_amt)} | {inr(r.gap_amt)}")
        else:
            L.append("name | HQ | segment | units | value | share% | target")
            for r in d.head(max_rows).itertuples():
                L.append(f"{r.distributor} | {r.hq or '-'} | {r.segment} | {r.cy_qty:,.0f} | {inr(r.cy_amt)} | "
                         f"{r.share_pct} | {inr(r.target_amt)}")
        if len(d) > max_rows:
            L.append(f"... {len(d) - max_rows} more")
    L.append("\nITEMS (item | category | units | value | share%" + (" | growth%)" if k["has_ly"] else ")"))
    for r in a["products"].head(25).itertuples():
        L.append(f"{r.product} | {r.category} | {r.qty_CY:,.0f} | {inr(r.amount_CY)} | {r.share_pct}"
                 + (f" | {r.growth_pct:+}" if k["has_ly"] else ""))
    if not a["hq"].empty:
        L.append("\nHQ (HQ | CY" + (" | growth%)" if k["has_ly"] else ")"))
        for r in a["hq"].itertuples():
            L.append(f"{r.hq} | {inr(r.cy_amt)}" + (f" | {r.growth_pct:+}" if k["has_ly"] else ""))
    c = a.get("contacts")
    if c:
        L += [f"\nCONTACT LIST for drip marketing: {c['total']} rows, {c['reachable']} reachable unique valid mobiles "
              f"(after removing {len(c['invalid'])} invalid numbers and {len(c['duplicates'])} repeated numbers; "
              f"{len(c['individuals'])} entries look like people's names, possibly internal test numbers)",
              "Reachable by type: " + "; ".join(f"{t}={n}" for t, n in c["by_type"].items())]
        names = c["table"][c["table"].send]["name"].tolist()
        L.append("Sample of names (place names show geography): " + "; ".join(names[:120]))
    return "\n".join(L)


def inr(v) -> str:
    """Indian short rupees: Rs 1.23 L / Rs 1.23 Cr."""
    if v is None:
        return "–"
    v = float(v)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e7:
        return f"{sign}₹{v / 1e7:.2f} Cr"
    if v >= 1e5:
        return f"{sign}₹{v / 1e5:.2f} L"
    return f"{sign}₹{v:,.0f}"


def kpi_tiles(k: dict) -> list[tuple]:
    """(label, value, tone) for the cockpit, adapting to what the data has. tone: ink|good|bad|blue|orange."""
    if k["has_ly"]:
        g = k["growth_pct"]
        t = [(k["ly_label"], inr(k["ly_amt"]), "ink"), (k["cy_label"], inr(k["cy_amt"]), "ink"),
             ("Growth", f"{g:+.1f}%", "good" if g >= 0 else "bad"),
             (f"Target (+{k['target_growth_pct']:.0f}%)", inr(k["target_amt"]), "blue"),
             ("Gap to close", inr(k["gap_amt"]), "orange")]
    else:
        t = [(f"Value · {k['cy_label']}", inr(k["cy_amt"]), "ink")]
        if k["instrument_units"]:
            t += [("Instruments placed", f"{k['instrument_units']:,.0f}", "ink"),
                  ("Reagent value", inr(k["consumable_amt"]), "ink"),
                  ("Reagent per instrument", inr(k["pull_through_per_unit"]), "orange")]
        t += [(f"Target (+{k['target_growth_pct']:.0f}%)", inr(k["target_amt"]), "blue")]
    if k.get("contacts_reachable") is not None:
        t.append(("Labs reachable", f"{k['contacts_reachable']:,}", "blue"))
    elif k["distributors_total"]:
        t.append(("Active distributors", f"{k['distributors_active']}/{k['distributors_total']}", "ink"))
    return t[:6]
