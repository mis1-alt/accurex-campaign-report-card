"""
Reads any number of uploaded files (Excel / CSV, any layout) into two things:

  SALES    one tidy table: source | distributor | hq | product | category | period | qty | amount
           (distributor is "" when a table is per product only; period is LY or CY)
  CONTACTS customer / lead lists (name + phone), used for drip campaigns

A workbook is described as a list of TABLE BLOCKS. Each block says where a table sits, what it
is, and which period it covers:

  kind = by_distributor          one row per distributor (product implied by the title)
         by_product              one row per item (distributor = sheet name, or all distributors)
         by_distributor_product  one row per distributor x item

Side-by-side tables are NOT assumed to be last year vs this year. Their titles decide: e.g.
"Instrument Sales Apr-Oct 2026" next to "Reagent Sales Apr-Oct 2026" are two different tables
for the same period. The AI proposes the blocks; Python applies them, and all arithmetic stays in
code. Without AI, a rule-based detector produces the same block description.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

TOTAL_WORDS = {"total", "totals", "grand total", "sub total", "subtotal", "total sales",
               "total amount", "total qty", "total quantity", "net total"}
TIDY_COLS = ["source", "distributor", "hq", "product", "category", "period", "qty", "amount"]

COMPANY_WORDS = re.compile(r"enterprise|distribut|agenc|pharma|medicare|surgical|scientific|trader|"
                           r"corporation|international|house|mart|pvt|ltd|limited|llp|sales|marketing|"
                           r"healthcare|health care|associates|& co|\bco\b|infotech|biomedical|"
                           r"diagnostics &|stockist", re.I)
PRODUCT_HINTS = re.compile(r"\d+\s*(ml|l|t|test|tests|x)\b|\b\d{2,4}\b|reagent|kit|control|calibrat|"
                           r"diluent|lyse|cleaner|analy[sz]er|autopure", re.I)
INSTRUMENT_WORDS = re.compile(r"instrument|analy[sz]er|machine|equipment|\bunit\b", re.I)
MONTHS = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"


# ── Loading ──────────────────────────────────────────────────────────────────
def load_any(file_bytes: bytes, filename: str) -> dict[str, pd.DataFrame]:
    """{sheet_name: raw DataFrame, no header}. CSV becomes one sheet."""
    bio = io.BytesIO(file_bytes)
    if filename.lower().endswith((".csv", ".txt")):
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                bio.seek(0)
                df = pd.read_csv(bio, header=None, dtype=object, encoding=enc)
                return {"Sheet1": _clean(df)}
            except UnicodeDecodeError:
                continue
    xl = pd.ExcelFile(bio)
    out = {}
    for s in xl.sheet_names:
        df = _clean(pd.read_excel(xl, sheet_name=s, header=None, dtype=object))
        if not df.empty:
            out[str(s)] = df
    return out


def _clean(df):
    # Empty rows go; empty COLUMNS stay - a blank spacer column is what separates side-by-side tables.
    df = df.dropna(how="all").reset_index(drop=True)
    while df.shape[1] and df.iloc[:, -1].isna().all():
        df = df.iloc[:, :-1]
    df.columns = range(df.shape[1])
    return df


def _cell(v, n=38) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip().replace("\n", " ")[:n]


def _row(df, i, n=80):
    return [_cell(v, n).lower() for v in df.iloc[i].tolist()]


def profile(sheets: dict[str, pd.DataFrame], rows: int = 14, max_sheets: int = 8) -> str:
    names = list(sheets)
    lines = [f"Workbook has {len(names)} sheet(s): {', '.join(n.strip() for n in names[:60])}"
             + (" ..." if len(names) > 60 else "")]
    for s in names[:max_sheets]:
        df = sheets[s]
        lines.append(f"\n=== Sheet '{s}' ({df.shape[0]} rows x {df.shape[1]} cols, rows r0..r{len(df) - 1}) ===")
        show = len(df) if len(df) <= 45 else rows
        for i in range(min(show, len(df))):
            cells = [f"c{j}={_cell(v)}" for j, v in enumerate(df.iloc[i].tolist()) if _cell(v)]
            lines.append(f"r{i}: " + " | ".join(cells))
        if show < len(df):
            lines.append(f"... rows r{show} to r{len(df) - 5} NOT SHOWN (data continues) ...")
            for i in range(len(df) - 4, len(df)):
                cells = [f"c{j}={_cell(v)}" for j, v in enumerate(df.iloc[i].tolist()) if _cell(v)]
                lines.append(f"r{i}: " + " | ".join(cells))
    if len(names) > max_sheets:
        lines.append(f"\n({len(names) - max_sheets} more sheets not shown; they likely share a structure "
                     f"with a shown sheet.)")
    return "\n".join(lines)


# ── Contacts ─────────────────────────────────────────────────────────────────
PHONE_LABEL = re.compile(r"phone|mobile|number|contact|whatsapp|\bno\b|cell", re.I)
NAME_LABEL = re.compile(r"name|customer|lab|hospital|account|party|client", re.I)
AMOUNT_LABEL = re.compile(r"amount|value|sales|revenue|qty|quantity", re.I)


def find_contacts(sheets) -> pd.DataFrame | None:
    """A sheet with a name column and a phone column and no sales numbers is a contact list."""
    frames = []
    for s, df in sheets.items():
        for i in range(min(5, len(df))):
            labels = _row(df, i)
            if any(AMOUNT_LABEL.search(l) for l in labels):
                break
            pc = next((j for j, l in enumerate(labels) if PHONE_LABEL.search(l)), None)
            nc = next((j for j, l in enumerate(labels) if NAME_LABEL.search(l) and j != pc), None)
            if pc is not None and nc is not None:
                cc = next((j for j, l in enumerate(labels) if re.search(r"city|town|district|state|region", l)), None)
                body = df.iloc[i + 1:]
                frames.append(pd.DataFrame({
                    "name": body[nc].map(lambda v: _cell(v, 120)),
                    "phone": body[pc].map(lambda v: re.sub(r"\D", "", _cell(v, 40))),
                    "city": body[cc].map(_cell) if cc is not None else "",
                    "list": s}))
                break
    if not frames:
        return None
    c = pd.concat(frames, ignore_index=True)
    return c[c["name"] != ""].reset_index(drop=True)


# ── Mapping (list of table blocks) ───────────────────────────────────────────
@dataclass
class Mapping:
    blocks: list = field(default_factory=list)
    skip_sheets: list = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Mapping":
        return cls(blocks=list(d.get("blocks") or []), skip_sheets=[str(s) for s in d.get("skip_sheets", [])],
                   notes=str(d.get("notes", "")))

    def to_dict(self):
        return {"blocks": self.blocks, "skip_sheets": self.skip_sheets, "notes": self.notes}

    def periods(self) -> dict:
        out = {}
        for b in self.blocks:
            for p, lab in (("LY", b.get("ly_label")), ("CY", b.get("cy_label"))):
                if lab:
                    out.setdefault(p, lab)
            if b.get("period") in ("LY", "CY"):
                lab = b.get("period_label") or ""
                from_title = _period_label(b.get("title") or "")
                if re.search(r"\s(-|–|—|to)\s|\d(-|–|—)", from_title) and not re.search(r"\s(-|–|—|to)\s", lab):
                    lab = from_title            # the title has the full range, e.g. 'April 2026 - October 2026'
                if lab:
                    out.setdefault(b["period"], lab)
        return out


MAPPING_SCHEMA_TEXT = """
Describe every data table in the workbook as a block. Return JSON:
{
 "blocks": [{
   "sheets": ["sheet names this block applies to (several if many sheets share the structure)"],
   "title": "the table's title as written, e.g. 'Acculab 200 Instrument Sales April 2026 - October 2026'",
   "kind": "by_distributor" | "by_product" | "by_distributor_product",
   "header_row": <0-based row of the column labels>,
   "last_row": null,   // ALWAYS null (Python reads until the data ends and skips Total rows),
                       // except when a second table is stacked BELOW this one on the same columns
   "columns": {"name": n|null, "distributor": n|null, "product": n|null, "hq": n|null,
               "qty": n|null, "amount": n|null, "period": n|null},
   "distributor_from_sheet": true|false,   // true when each sheet is one distributor
   "product_label": "for by_distributor tables: the product the numbers are for, e.g. 'Acculab 200 Instrument'",
   "category": "instrument" | "consumable" | "mixed",
   "period": "LY" | "CY" | null,           // null only if a period column or sheet_periods decides it
   "period_label": "e.g. 'Apr-Oct 2026'",
   "sheet_periods": {"<sheet>": "LY"|"CY"},          // when whole sheets are one period
   "period_values": {"LY": ["values"], "CY": ["values"]}  // when columns.period is used
 }],
 "skip_sheets": ["summary / pivot / notes sheets"],
 "notes": "one or two sentences on what the file contains"
}
Rules:
- Two tables side by side are only Last Year vs This Year if their titles/labels show two
  different periods for the SAME kind of table. Different subjects (instruments vs reagents,
  distributors vs products) for the same period are separate blocks with the same period.
- If the file has only one period, mark it CY (this year). LY = the older period.
- A wide table with LY and CY columns side by side = two blocks on the same rows, each with its own qty/amount columns.
- 'name' is the row label column; say via kind whether it holds distributors or products.
- Column numbers are the c<N> indexes shown. Ignore 'Total' rows.
"""


def ai_detect_mapping(ai, sheets) -> Mapping:
    prompt = ("You are reading a sales report from an Indian IVD company (instruments and reagents "
              "sold to distributors). Work out its structure.\n\n" + profile(sheets) + "\n\n" + MAPPING_SCHEMA_TEXT)
    return Mapping.from_dict(ai.json(prompt, system="You are a meticulous data engineer. Output only JSON.",
                                     max_tokens=2500))


# ── Rule-based detection ─────────────────────────────────────────────────────
def _is_qty(l):
    return bool(re.search(r"\bqty\b|quantity|units?\b|\bnos\b", l))


def _is_amt(l):
    return bool(re.search(r"amount|value|sales|revenue|\brs\b|inr|₹|\bnet\b", l)) and not _is_qty(l)


_LY = re.compile(r"\bly\b|last|prev|previous|\bpy\b|prior")
_CY = re.compile(r"\bcy\b|this year|current|\bcurr\b|\bty\b")


def _hint(text):
    if _LY.search(text):
        return "LY"
    if _CY.search(text):
        return "CY"
    yrs = re.findall(r"20\d{2}", text)
    if yrs:
        return int(yrs[-1])
    m = re.findall(r"\bfy\s*(\d{2})", text)
    return 2000 + int(m[-1]) if m else None


def _period_label(text):
    m = re.search(rf"{MONTHS}\W*\d{{0,4}}\s*(to|-|–|—|till|until)\s*{MONTHS}\W*\d{{2,4}}", text, re.I)
    if m:
        return m.group(0)
    m = re.search(r"(fy\s*)?20\d{2}(\s*[-/]\s*\d{2,4})?", text, re.I)
    return m.group(0) if m else ""


def _groups(labels):
    """Split a header row into contiguous non-blank column groups."""
    out, cur = [], []
    for j, l in enumerate(labels):
        if l:
            cur.append(j)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _title_for(df, header_row, group):
    for r in range(header_row - 1, -1, -1):
        for j in group:
            t = _cell(df.iloc[r, j], 200)
            if t:
                return t
    return ""


def _looks_like(df, col, start, n=25):
    vals = [_cell(v, 120) for v in df.iloc[start:start + n, col].tolist()]
    vals = [v for v in vals if v and v.lower() not in TOTAL_WORDS]
    if not vals:
        return "product"
    comp = sum(bool(COMPANY_WORDS.search(v)) for v in vals) / len(vals)
    prod = sum(bool(PRODUCT_HINTS.search(v)) for v in vals) / len(vals)
    return "distributor" if comp > prod and comp >= 0.25 else "product"


def _product_label(title):
    t = re.sub(rf"{MONTHS}\W*\d{{0,4}}", "", title, flags=re.I)
    t = re.sub(r"\b(sales|report|from|to|for|fy|20\d{2})\b|[-–:]", " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip() or title


def _detect_blocks(df):
    """Blocks found on one sheet (without period resolution)."""
    for i in range(min(10, len(df))):
        labels = _row(df, i)
        if not any(_is_amt(l) for l in labels):
            continue
        blocks = []
        for g in _groups(labels):
            qty = [j for j in g if _is_qty(labels[j])]
            amt = [j for j in g if _is_amt(labels[j])]
            if not amt:
                continue
            lab = lambda rx: next((j for j in g if re.search(rx, labels[j]) and j not in qty + amt), None)  # noqa: E731
            dist = lab(r"distributor|party|dealer|customer|ledger|stockist")
            prod = lab(r"product|item|description|material|sku|particular")
            hq = lab(r"\bhq\b|region|zone|territory|state")
            per = lab(r"\byear\b|\bfy\b|period|month|date")
            text_cols = [j for j in g if j not in qty + amt + [dist, prod, hq, per]]
            name = text_cols[0] if text_cols else None
            if not qty and len(g) == len(amt):
                continue                              # a title row mentioning "sales", not a header
            if name is None and g[0] >= 1 and not labels[g[0] - 1]:
                name = g[0] - 1                       # unlabelled name column just left of the group
            title = _title_for(df, i, sorted(set(g + ([name] if name is not None else []))))
            if dist is not None and prod is not None:
                kind = "by_distributor_product"
            elif dist is not None:
                kind = "by_distributor"
            elif prod is not None:
                kind = "by_product"
            elif name is not None:
                kind = "by_" + _looks_like(df, name, i + 1)
            else:
                continue
            base = {"title": title, "kind": kind, "header_row": i, "last_row": None,
                    "columns": {"name": name, "distributor": dist, "product": prod, "hq": hq, "period": per},
                    "product_label": _product_label(title) if kind == "by_distributor" else "",
                    "category": "instrument" if INSTRUMENT_WORDS.search(title) else
                                ("consumable" if re.search(r"reagent|consumable|kit", title, re.I) else "mixed")}
            if len(qty) == len(amt):
                pairs = list(zip(qty, amt))                 # one pair, or LY/CY pairs side by side
            elif len(amt) >= 2:
                pairs = [(None, a) for a in amt]
            else:
                pairs = [(qty[0] if qty else None, amt[0])]
            for q, a in pairs:
                b = {**base, "columns": {**base["columns"], "qty": q, "amount": a}}
                b["_hint"] = _hint(labels[a]) or _hint(labels[q] if q is not None else "") or _hint(title)
                b["period_label"] = _period_label(title) or (labels[a] if _hint(labels[a]) else "")
                blocks.append(b)
        if blocks:
            # stacked tables: a block ends where the next header row of the same columns starts (not handled) -> fine
            return blocks
    return []


def _resolve_periods(blocks, sheet_names):
    """Turn hints into LY/CY. Only blocks of the same kind+columns-shape compete as LY vs CY."""
    by_key = {}
    for b in blocks:
        by_key.setdefault(b["kind"], []).append(b)
    for kind, bs in by_key.items():
        hints = [b.get("_hint") for b in bs]
        if any(h in ("LY", "CY") for h in hints):
            for b, h in zip(bs, hints):
                b["period"] = h if h in ("LY", "CY") else "CY"
            continue
        yrs = sorted({h for h in hints if isinstance(h, int)})
        if len(bs) >= 2 and len(yrs) >= 2:
            for b, h in zip(bs, hints):
                b["period"] = "CY" if h == yrs[-1] else "LY" if h == yrs[-2] else None
        else:
            for b in bs:
                b["period"] = "CY" if b["columns"].get("period") is None else None
    # whole sheets as periods (one tab per year)
    for b in blocks:
        if b.get("period") is None or (len(b["sheets"]) >= 2 and b["columns"].get("period") is None
                                       and len({_hint(s) for s in b["sheets"]} - {None}) >= 2):
            yrs = {s: _hint(s) for s in b["sheets"]}
            ys = sorted({y for y in yrs.values() if isinstance(y, int)})
            if len(ys) >= 2:
                b["sheet_periods"] = {s: ("CY" if y == ys[-1] else "LY" if y == ys[-2] else None)
                                      for s, y in yrs.items() if isinstance(y, int)}
                b["period"] = None
                b["distributor_from_sheet"] = False
        b.pop("_hint", None)
    return blocks


def heuristic_mapping(sheets) -> Mapping:
    sig_groups = {}
    for s, df in sheets.items():
        blocks = _detect_blocks(df)
        if not blocks:
            continue
        sig = tuple(_row(df, blocks[0]["header_row"]))
        sig_groups.setdefault(sig, []).append((s, blocks))
    if not sig_groups:
        raise ValueError("Could not recognise any sales table without AI. Add an API key so the AI can read it.")
    all_blocks, used = [], set()
    for sig, members in sig_groups.items():
        names = [s for s, _ in members]
        used.update(names)
        for b in members[0][1]:
            b["sheets"] = names
            b["distributor_from_sheet"] = (len(names) > 1 and b["kind"] == "by_product"
                                           and len({_hint(n) for n in names} - {None}) < 2)
            all_blocks.append(b)
    all_blocks = _resolve_periods(all_blocks, list(sheets))
    kinds = sorted({b["kind"] for b in all_blocks})
    pers = sorted({b.get("period") or "per-sheet" for b in all_blocks})
    return Mapping(blocks=all_blocks, skip_sheets=[s for s in sheets if s not in used],
                   notes=f"Rule-based: {len(all_blocks)} table(s) ({', '.join(kinds)}); periods: {', '.join(pers)}.")


# ── Applying ─────────────────────────────────────────────────────────────────
_TOTAL_RX = re.compile(r"^(grand\s+|sub\s*-?\s*|net\s+)?totals?\b[\s:.-]*(sales|amount|qty|quantity|value|rs\.?|\(.*\))?\s*$")


def _is_total(label: str) -> bool:
    """'Total', 'Grand Total', 'Total Amount' yes; 'Total Protein 60 - Autopure' no."""
    return label.strip() in TOTAL_WORDS or bool(_TOTAL_RX.match(label.strip()))


def _num(v) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    s = re.sub(r"[₹,\s]|rs\.?|inr", "", str(v), flags=re.I)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0


def _ix(v):
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _get(row, idx):
    return row[idx] if idx is not None and idx < len(row) else None


def _auto_periods(values):
    yrs = {v: _hint(v) for v in set(values) if v}
    ys = sorted({y for y in yrs.values() if isinstance(y, int)})
    if len(ys) < 2:
        return {}
    return {v: ("CY" if y == ys[-1] else "LY" if y == ys[-2] else None) for v, y in yrs.items()}


def _category(product, block_cat, title):
    if INSTRUMENT_WORDS.search(product):
        return "instrument"
    if block_cat in ("instrument", "consumable"):
        return block_cat
    return "consumable"


def apply_mapping(sheets, m: Mapping, file_label: str = "") -> pd.DataFrame:
    recs = []
    skip = {s.strip().lower() for s in m.skip_sheets}
    for b in m.blocks:
        c = {k: _ix(v) for k, v in (b.get("columns") or {}).items()}
        targets = b.get("sheets") or ([b["sheet"]] if b.get("sheet") else list(sheets))
        kind = b.get("kind", "by_product")
        for s in targets:
            df = sheets.get(s)
            if df is None:
                df = next((d for k, d in sheets.items() if k.strip() == str(s).strip()), None)
            if df is None or str(s).strip().lower() in skip:
                continue
            hdr = _ix(b.get("header_row")) or 0
            last = _ix(b.get("last_row"))
            rows = df.iloc[hdr + 1:(last + 1 if last is not None else None)].values.tolist()
            sp = (b.get("sheet_periods") or {})
            fixed = b.get("period") if b.get("period") in ("LY", "CY") else (sp.get(s) or sp.get(str(s).strip()))
            auto = {}
            pv = b.get("period_values") or {}
            if not fixed and c.get("period") is not None and not pv:
                auto = _auto_periods([_cell(_get(r, c["period"]), 200) for r in rows])
            title = b.get("title") or s
            for r in rows:
                name = _cell(_get(r, c.get("name")), 200)
                if kind == "by_distributor":
                    dist = _cell(_get(r, c.get("distributor")), 200) or name
                    prod = b.get("product_label") or _product_label(title)
                elif kind == "by_product":
                    prod = _cell(_get(r, c.get("product")), 200) or name
                    dist = str(s).strip() if b.get("distributor_from_sheet") else ""
                else:
                    dist = _cell(_get(r, c.get("distributor")), 200) or (str(s).strip() if b.get("distributor_from_sheet") else name)
                    prod = _cell(_get(r, c.get("product")), 200)
                label = (dist if kind == "by_distributor" else prod).lower()
                if not label or _is_total(label) or (dist and _is_total(dist.lower())):
                    continue
                if fixed:
                    period = fixed
                else:
                    raw = _cell(_get(r, c.get("period")), 200)
                    period = next((p for p in ("LY", "CY") for t in pv.get(p, []) if t and str(t).lower() in raw.lower()), None) \
                        or auto.get(raw)
                if period not in ("LY", "CY"):
                    continue
                q, a = _num(_get(r, c.get("qty"))), _num(_get(r, c.get("amount")))
                if q == 0 and a == 0:
                    continue
                recs.append((f"{file_label}{title}", dist, _cell(_get(r, c.get("hq")), 80), prod,
                             _category(prod, b.get("category"), title), period, q, a))
    tidy = pd.DataFrame(recs, columns=TIDY_COLS)
    if not tidy.empty:
        tidy = tidy.groupby([c for c in TIDY_COLS if c not in ("qty", "amount")], as_index=False)[["qty", "amount"]].sum()
    return tidy


def total_checks(sheets, m: Mapping) -> list[dict]:
    """Compare what we read for each table with the file's own 'Total' row (when it has one)."""
    out = []
    for b in m.blocks:
        c = {k: _ix(v) for k, v in (b.get("columns") or {}).items()}
        label_cols = [x for x in (c.get("name"), c.get("distributor"), c.get("product")) if x is not None]
        amt = c.get("amount")
        if amt is None or not label_cols:
            continue
        file_total, found_all = 0.0, True
        targets = b.get("sheets") or list(sheets)
        for s in targets:
            df = sheets.get(s)
            if df is None:
                continue
            hdr = _ix(b.get("header_row")) or 0
            vals = [_num(df.iloc[i, amt]) for i in range(hdr + 1, len(df)) if amt < df.shape[1]
                    and any(_is_total(_cell(df.iloc[i, lc], 80).lower()) for lc in label_cols if lc < df.shape[1])]
            if vals:
                file_total += vals[0]
            else:
                found_all = False
        if not found_all or not file_total:
            continue
        read = apply_mapping(sheets, Mapping(blocks=[{**b, "period": b.get("period") or "CY"}]))["amount"].sum()
        out.append({"table": b.get("title") or ", ".join(map(str, targets[:2])), "file_total": file_total,
                    "read_total": float(read), "ok": abs(read - file_total) <= max(1.0, file_total * 0.001)})
    return out


def _score(checks):
    return (sum(c["ok"] for c in checks), -sum(not c["ok"] for c in checks))


def read_file(file_bytes, filename, ai=None, mapping: Mapping | None = None):
    """One uploaded file -> dict(tidy, mapping, sheets, contacts, kind, checks).
    Candidate readings (AI, AI without row limits, rule-based) are checked against the file's own
    Total rows and the best-matching one wins."""
    sheets = load_any(file_bytes, filename)
    if not sheets:
        raise ValueError(f"{filename}: no data.")
    contacts = find_contacts(sheets)
    if contacts is not None and mapping is None:
        return {"kind": "contacts", "contacts": contacts, "sheets": sheets, "tidy": pd.DataFrame(columns=TIDY_COLS),
                "mapping": Mapping(notes=f"Contact list: {len(contacts)} rows."), "checks": []}
    candidates, ai_err = [], ""
    if mapping is not None:
        candidates.append(mapping)
    else:
        if ai is not None:
            try:
                am = ai_detect_mapping(ai, sheets)
                candidates.append(am)
                if any(b.get("last_row") is not None for b in am.blocks):
                    candidates.append(Mapping(blocks=[{**b, "last_row": None} for b in am.blocks],
                                              skip_sheets=am.skip_sheets, notes=am.notes))
            except Exception as e:
                ai_err = str(e)
        try:
            hm = heuristic_mapping(sheets)
            if ai is not None and not candidates:
                hm.notes += f" (AI reading failed: {ai_err})"
            candidates.append(hm)
        except ValueError:
            if not candidates:
                raise
    best = None
    for m in candidates:
        t = apply_mapping(sheets, m)
        ch = total_checks(sheets, m)
        key = (not t.empty, *_score(ch))
        if best is None or key > best[0]:
            best = (key, m, t, ch)
    _, mapping, tidy, checks = best
    if checks and all(c["ok"] for c in checks):
        mapping.notes += " Totals match the file's own Total rows."
    return {"kind": "sales", "tidy": tidy, "mapping": mapping, "sheets": sheets, "contacts": None, "checks": checks}


def combine(results: dict) -> tuple[pd.DataFrame, pd.DataFrame | None, dict]:
    """results = {filename: read_file(...) output}. Returns (sales, contacts, period labels).
    Two single-period sales files for different years (e.g. 'Sales FY25' and 'Sales FY26') become LY and CY."""
    sales = {f: r for f, r in results.items() if r["kind"] == "sales" and not r["tidy"].empty}
    labels, as_ly = {}, set()
    single = {f: r for f, r in sales.items() if set(r["tidy"]["period"]) == {"CY"}}
    if len(single) >= 2 and len(single) == len(sales):
        yrs = {f: _hint(r["mapping"].periods().get("CY", "") + " " + f) for f, r in single.items()}
        ys = sorted({y for y in yrs.values() if isinstance(y, int)})
        if len(ys) >= 2:
            for f, y in yrs.items():
                if y == ys[-2]:
                    as_ly.add(f)
                elif y != ys[-1]:
                    sales[f] = {**sales[f], "tidy": sales[f]["tidy"].iloc[0:0]}
    frames = []
    for f, r in sales.items():
        t = r["tidy"].copy()
        pl = r["mapping"].periods()
        if f in as_ly:
            t["period"] = "LY"
            labels["LY"] = pl.get("CY") or f
        else:
            for p, lab in pl.items():
                labels.setdefault(p, lab)
        if len(sales) > 1:
            t["source"] = f + " · " + t["source"]
        frames.append(t)
    tidy = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=TIDY_COLS)
    cs = [r["contacts"].assign(list=f) for f, r in results.items() if r["kind"] == "contacts"]
    contacts = pd.concat(cs, ignore_index=True) if cs else None
    return tidy, contacts, labels


def read_sales(file_bytes, filename, ai=None, mapping=None):
    """Back-compatible helper: (tidy, mapping, sheets)."""
    r = read_file(file_bytes, filename, ai=ai, mapping=mapping)
    return r["tidy"], r["mapping"], r["sheets"]


# ── Product selection ────────────────────────────────────────────────────────
def _tokens(s):
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) >= 3}


def fuzzy_products(tidy: pd.DataFrame, campaign_product: str, min_overlap=0.5) -> list[str]:
    """Items whose own name, or whose table title, matches the campaign product."""
    pf, toks = campaign_product.lower().strip(), _tokens(campaign_product)
    pairs = tidy[["product", "source"]].drop_duplicates()
    out = []
    for p, src in pairs.itertuples(index=False):
        for text in (p, src):
            tl = text.lower()
            if (pf and pf in tl) or (toks and len(toks & _tokens(text)) / len(toks) >= min_overlap
                                     and len(toks & _tokens(text)) >= min(2, len(toks))):
                out.append(p)
                break
    return sorted(set(out))


def ai_select_products(ai, tidy, campaign_product, product_brief=""):
    t = tidy.groupby(["product", "source"])["amount"].sum().sort_values(ascending=False).reset_index().head(400)
    listing = "\n".join(f"- {r.product}   [table: {r.source}]" for r in t.itertuples())
    prompt = f"""Campaign product: "{campaign_product}"
What we know about it: {product_brief or 'n/a'}

Below are all item names in the sales data, with the table each came from. Select every item that
belongs to this campaign product: the instrument itself and its dedicated reagents, controls,
calibrators and consumables (the table title often says which instrument a reagent list is for).
Exclude items for other instruments.

{listing}

Return JSON: {{"selected": ["exact item names"], "reason": "one sentence"}}"""
    d = ai.json(prompt, max_tokens=3000)
    valid = set(t["product"])
    return [p for p in d.get("selected", []) if p in valid], d.get("reason", "")
