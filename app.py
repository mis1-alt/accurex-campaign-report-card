import streamlit as st
import pandas as pd
import io
import os
import json
import zipfile
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from reportlab.lib.utils import ImageReader

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Accurex Campaign Report Card",
    page_icon="📣",
    layout="wide"
)

DEFAULT_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accurex_logo.png")


# ── Font registration (same DejaVu setup as the distributor report app) ─────
@st.cache_resource
def register_fonts():
    font_paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    ]
    for path in font_paths:
        if not os.path.exists(path):
            st.error(f"Font not found: {path}. Please ensure DejaVu fonts are installed.")
            return False
    pdfmetrics.registerFont(TTFont('DVSans', font_paths[0]))
    pdfmetrics.registerFont(TTFont('DVSans-Bold', font_paths[1]))
    pdfmetrics.registerFontFamily('DVSans', normal='DVSans', bold='DVSans-Bold')
    return True

register_fonts()

# ── Colours (same palette as the Distributor Order Report Card) ─────────────
BLUE   = colors.HexColor('#1A56A0')
RED    = colors.HexColor('#A32D2D')
GREEN  = colors.HexColor('#3B6D11')
AMBER  = colors.HexColor('#854F0B')
DGRAY  = colors.HexColor('#5F5E5A')
LGRAY  = colors.HexColor('#F5F5F3')
MGRAY  = colors.HexColor('#E0DED8')
WHITE  = colors.white
RED_BG = colors.HexColor('#FCEBEB')
GRN_BG = colors.HexColor('#EAF3DE')
AMB_BG = colors.HexColor('#FAEEDA')
BLU_BG = colors.HexColor('#E6F1FB')

def PS(name, **kw):
    base = dict(fontName='DVSans', fontSize=8.5, leading=12, textColor=colors.HexColor('#2C2C2A'))
    base.update(kw)
    return ParagraphStyle(name, **base)

def inr(v):
    return f'₹{int(round(v)):,}'

def ph(txt, align=TA_LEFT):
    return Paragraph(txt, PS(f'th_{txt[:8]}', fontName='DVSans-Bold', fontSize=7.5,
                              textColor=DGRAY, alignment=align, leading=10))

def pc(txt, color=None, align=TA_LEFT, bold=False):
    c = color or '#2C2C2A'
    font = 'DVSans-Bold' if bold else 'DVSans'
    return Paragraph(f'<font color="{c}"><font name="{font}">{txt}</font></font>',
                     PS(f'tc_{txt[:8]}', fontSize=7.5, leading=10, alignment=align))

def bold_markup(text):
    """Turn **word** markers from the AI's JSON into real <b> runs for reportlab Paragraphs."""
    out, bold = [], False
    for part in str(text).split('**'):
        part = part.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        out.append(f'<b>{part}</b>' if bold else part)
        bold = not bold
    return ''.join(out)

# ── Parse Excel: per-distributor sheet, two date-range blocks ───────────────
TOTALS_ROW_LABELS = {'total', 'totals', 'grand total', 'sub total', 'subtotal',
                      'total sales', 'total amount', 'total qty', 'total quantity'}

def is_totals_row(name):
    return str(name).strip().lower() in TOTALS_ROW_LABELS

def _safe_lower_strs(series):
    """Stringify every cell (NaN-safe) and lowercase — avoids pandas leaving NaN as float
    under .astype(str) in some mixed-dtype columns."""
    return [str(v).lower() if pd.notna(v) else '' for v in series.tolist()]

def find_header_row(df, max_scan=6):
    """Locate the header row. Real Accurex sales files don't label a 'Product' column at all —
    the only reliable markers are two 'Qty' columns and two 'Amount' columns (one pair per
    date-range block), so detection keys off those instead."""
    for i in range(min(max_scan, len(df))):
        labels = _safe_lower_strs(df.iloc[i])
        qty_count = sum(1 for l in labels if 'qty' in l or 'quantity' in l)
        amt_count = sum(1 for l in labels if 'amount' in l or 'value' in l)
        if qty_count >= 2 and amt_count >= 2:
            return i
    return None

def find_columns(header_row):
    """Split the header row into contiguous non-blank column blocks (blocks are separated by
    a blank/NaN header cell, e.g. the spacer column between the LY and CY blocks). Within each
    block, locate the Qty and Amount columns by label; the product column is whatever column in
    that block is neither Qty nor Amount (it's usually unlabeled or carries the block's date-range
    title, not the word 'Product')."""
    labels = _safe_lower_strs(header_row)
    blocks, cur = [], []
    for idx, label in enumerate(labels):
        if label == '':
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(idx)
    if cur:
        blocks.append(cur)

    result = []
    for block in blocks:
        qty_idx = next((idx for idx in block if 'qty' in labels[idx] or 'quantity' in labels[idx]), None)
        amt_idx = next((idx for idx in block if 'amount' in labels[idx] or 'value' in labels[idx]), None)
        prod_idx = next((idx for idx in block if idx not in (qty_idx, amt_idx)), None)
        if qty_idx is not None and amt_idx is not None and prod_idx is not None:
            result.append({'product': prod_idx, 'qty': qty_idx, 'amount': amt_idx})
    return result

def parse_sheet(df):
    """Returns (ly_dict, cy_dict) of {product: (qty, amount)}."""
    hdr_idx = find_header_row(df)
    if hdr_idx is None:
        return {}, {}
    header_row = df.iloc[hdr_idx]
    blocks = find_columns(header_row)
    if len(blocks) < 2:
        return {}, {}
    ly_cols, cy_cols = blocks[0], blocks[-1]

    ly, cy = {}, {}
    for i in range(hdr_idx + 1, len(df)):
        row = df.iloc[i]
        try:
            if 'product' in ly_cols:
                p = str(row.iloc[ly_cols['product']]).strip() if pd.notna(row.iloc[ly_cols['product']]) else ''
                q = float(row.iloc[ly_cols['qty']]) if 'qty' in ly_cols and pd.notna(row.iloc[ly_cols['qty']]) else 0
                a_raw = row.iloc[ly_cols['amount']] if 'amount' in ly_cols else None
                a = float(str(a_raw).replace(',', '').replace('₹', '').strip()) if pd.notna(a_raw) and str(a_raw).strip() not in ('', 'nan') else 0
                if p and p.lower() != 'nan' and not is_totals_row(p) and (q > 0 or a > 0):
                    ly[p] = (int(q), a)
        except Exception:
            pass
        try:
            if 'product' in cy_cols:
                p = str(row.iloc[cy_cols['product']]).strip() if pd.notna(row.iloc[cy_cols['product']]) else ''
                q = float(row.iloc[cy_cols['qty']]) if 'qty' in cy_cols and pd.notna(row.iloc[cy_cols['qty']]) else 0
                a_raw = row.iloc[cy_cols['amount']] if 'amount' in cy_cols else None
                a = float(str(a_raw).replace(',', '').replace('₹', '').strip()) if pd.notna(a_raw) and str(a_raw).strip() not in ('', 'nan') else 0
                if p and p.lower() != 'nan' and not is_totals_row(p) and (q > 0 or a > 0):
                    cy[p] = (int(q), a)
        except Exception:
            pass
    return ly, cy

import re

def _tokenize(s):
    return set(w for w in re.findall(r'[a-z0-9]+', s.lower()) if len(w) >= 3)

def filter_by_product(data, product_filter, min_overlap=0.5):
    """Restrict parsed rows to the campaign's product. Real sales sheets list reagents/
    consumables by their own names (e.g. 'Diluent 20L for CBC 360 NEO (RFID)') rather than
    repeating a brand prefix like 'Acculab', so a plain substring match misses almost
    everything. Instead: exact substring still matches (cheap, catches literal hits), and
    otherwise a row matches if at least half of the product filter's significant words
    (length >= 3) appear in the row name - catches instrument-family consumables without
    being so loose it pulls in unrelated products."""
    if not product_filter:
        return data
    pf = product_filter.strip().lower()
    filt_tokens = _tokenize(product_filter)
    out = {}
    for p, v in data.items():
        pl = p.lower()
        if pf in pl:
            out[p] = v
            continue
        if filt_tokens:
            row_tokens = _tokenize(p)
            overlap = len(filt_tokens & row_tokens) / len(filt_tokens)
            if overlap >= min_overlap:
                out[p] = v
    return out


# ── AI calls (Anthropic Platform API) ────────────────────────────────────────
def get_client():
    key = st.session_state.get('api_key') or st.secrets.get('ANTHROPIC_API_KEY', None) if hasattr(st, 'secrets') else st.session_state.get('api_key')
    if not key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=key)
    except Exception as e:
        st.error(f"Could not initialise Anthropic client: {e}")
        return None

AI_SYSTEM = (
    "You are an AI assistant generating content for an internal Accurex Biomedical "
    "(in-vitro diagnostics, India) campaign report for management. Accurex sells IVD "
    "instruments and reagents to distributors, who sell to diagnostic labs/hospitals. "
    "Write in a factual, precise, no-nonsense tone with no exclamation marks and no humour. "
    "Keep everything short and management-scannable: management will not read long paragraphs. "
    "Use **double asterisks** sparingly (2-4 times per section) to bold only the most important "
    "figures, targets or phrases. Return ONLY valid JSON matching the requested schema, nothing else."
)

def call_ai(client, prompt, max_tokens=1600):
    resp = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=max_tokens,
        system=AI_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:]
    return json.loads(text)

def generate_ai_sections(client, campaign, kpis, hq_summary):
    prompt = f"""
Campaign details (provided by the marketing executive):
- Product (per Tally): {campaign['product']}
- Campaign type: {campaign['camp_type']}
- Duration: {campaign['duration']}
- Stage: {campaign['stage']}
- Goal / expected output: {campaign['goal']}
- Rough campaign idea: {campaign['idea']}
- Technical USP: {campaign['usp']}
- Tasks and doers supplied by executive (name: frequency): {json.dumps(campaign['tasks'])}
- PMT team members available as doers: {campaign['pmt_names'] or "not specified - use 'PMT' as the doer"}

Sales data summary (actual numbers, already computed - use these, do not invent other totals):
{json.dumps(kpis, indent=2)}

HQ-level summary (may be empty if no distributor-to-HQ mapping was supplied):
{json.dumps(hq_summary, indent=2)}

Produce a JSON object with exactly these keys:

1. "smart_result": object with:
   - "timeline": short string, the key milestone dates/phases for this campaign (bold the 2-3 most important dates/numbers).
   - "action": array of 3-5 short bullet strings, each a concrete next action tied to a date or distributor/HQ, under 15 words each.

2. "checklist": array of 6-10 objects, modelled on the MCC Marketing Plan structure (sections: BACK END ACTIVITIES, SOP FOR CAMPAIGN, EXECUTION, FRONT END ACTIVITIES). Each object has:
   - "section": one of "Back End Activities", "SOP for Campaign", "Execution", "Front End Activities"
   - "activity": short activity name
   - "doer": EXACTLY ONE name/role (pick from the PMT names given, else "PMT")
   - "action_tools": short string naming the concrete action and any tool/reference, e.g. "Brief distributors using Technical Handbook" or "Log orders per Order Collection Handbook"
   - "end_date": a short relative deadline string (e.g. "Week 1", "Day 3 of launch"), not a literal calendar date

3. "competitor_analysis": array of 2-4 objects with "competitor", "product", "price" (mark "approx." if estimated), "feature" (one short line). Prioritise any named competitors if mentioned in the campaign idea/goal text above; otherwise use real, known Indian IVD/diagnostics market competitors for this product category, marking estimated figures clearly.

Return ONLY the JSON object, no commentary.
"""
    return call_ai(client, prompt)

def generate_creative_feedback(client, creative_text, campaign):
    prompt = f"""
The PMT team has drafted the following creative copy/brief for this campaign (product: {campaign['product']}, USP: {campaign['usp']}, goal: {campaign['goal']}):

---
{creative_text}
---

Give short, factual feedback (3-5 sentences, management-readable, bold the 1-2 most important points with **asterisks**) on whether this creative aligns with the technical USP and campaign goal, and one concrete improvement if needed.
Return ONLY a JSON object: {{"feedback": "..."}}
"""
    return call_ai(client, prompt, max_tokens=500)['feedback']


# ── Report data assembly ─────────────────────────────────────────────────────
def compute_kpis(dist_data):
    """dist_data: {distributor: (ly_dict, cy_dict)}"""
    total_ly_qty = total_ly_amt = total_cy_qty = total_cy_amt = 0
    rows = []
    for dist, (ly, cy) in dist_data.items():
        ly_qty = sum(q for q, a in ly.values())
        ly_amt = sum(a for q, a in ly.values())
        cy_qty = sum(q for q, a in cy.values())
        cy_amt = sum(a for q, a in cy.values())
        total_ly_qty += ly_qty; total_ly_amt += ly_amt
        total_cy_qty += cy_qty; total_cy_amt += cy_amt
        change_pct = ((cy_amt - ly_amt) / ly_amt * 100) if ly_amt else (100 if cy_amt else 0)
        rows.append({
            'distributor': dist, 'ly_qty': ly_qty, 'ly_amt': ly_amt,
            'cy_qty': cy_qty, 'cy_amt': cy_amt, 'change_pct': change_pct,
        })
    rows.sort(key=lambda r: -r['cy_amt'])
    kpis = {
        'total_ly_qty': total_ly_qty, 'total_ly_amt': total_ly_amt,
        'total_cy_qty': total_cy_qty, 'total_cy_amt': total_cy_amt,
        'overall_change_pct': round(((total_cy_amt - total_ly_amt) / total_ly_amt * 100), 1) if total_ly_amt else 0,
        'top_distributor': rows[0]['distributor'] if rows else None,
        'low_distributor': min(rows, key=lambda r: r['change_pct'])['distributor'] if rows else None,
    }
    return kpis, rows

def compute_hq_summary(dist_rows, hq_map):
    if not hq_map:
        return {}
    agg = {}
    for r in dist_rows:
        hq = hq_map.get(r['distributor'], 'Unmapped')
        a = agg.setdefault(hq, {'ly_amt': 0, 'cy_amt': 0})
        a['ly_amt'] += r['ly_amt']; a['cy_amt'] += r['cy_amt']
    for hq, v in agg.items():
        v['change_pct'] = round(((v['cy_amt'] - v['ly_amt']) / v['ly_amt'] * 100), 1) if v['ly_amt'] else 0
    ranked = sorted(agg.items(), key=lambda kv: -kv[1]['cy_amt'])
    return {
        'by_hq': agg,
        'top_hq': ranked[0][0] if ranked else None,
        'low_hq': min(agg.items(), key=lambda kv: kv[1]['change_pct'])[0] if agg else None,
    }


# ── PDF generation ────────────────────────────────────────────────────────────
def generate_pdf(campaign, kpis, dist_rows, hq_summary, ai, creative_feedback, logo_bytes=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=14*mm, rightMargin=14*mm,
                             topMargin=13*mm, bottomMargin=13*mm)
    story = []
    today_str = date.today().strftime("%d %B %Y")

    # ── Header ──
    title = f"{campaign['product']} — Campaign Report Card"
    header_text = Paragraph(f'<b>{title}</b>',
                             PS('hn', fontName='DVSans-Bold', fontSize=15, textColor=BLUE, leading=19))
    if logo_bytes:
        logo_buf = io.BytesIO(logo_bytes)
        max_w, max_h = 38*mm, 14.5*mm
        img_reader = ImageReader(logo_buf)
        img_w, img_h = img_reader.getSize()
        scale = min(max_w / img_w, max_h / img_h)
        logo = RLImage(logo_buf, width=img_w*scale, height=img_h*scale)
        hdr = Table([[header_text, logo]], colWidths=[142*mm, 38*mm])
    else:
        hdr = Table([[header_text, Paragraph('Accurex Biomedical',
                      PS('hb', fontName='DVSans-Bold', fontSize=9, textColor=DGRAY, alignment=TA_RIGHT))]],
                    colWidths=[142*mm, 38*mm])
    hdr.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BLU_BG), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (0,0), 10), ('RIGHTPADDING', (1,0), (1,0), 8),
    ]))
    story.append(hdr)

    sub_line = (f"{campaign['camp_type']} campaign · {campaign['duration']} · "
                f"Stage: {campaign['stage']} · Report date {today_str}")
    sub = Table([[Paragraph(sub_line, PS('sub1', fontSize=9, textColor=DGRAY))]], colWidths=[180*mm])
    sub.setStyle(TableStyle([
        ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(sub)
    story.append(HRFlowable(width='100%', thickness=0.5, color=MGRAY, spaceAfter=8))

    # ── KPI cards ──
    growth_color = GREEN if kpis['overall_change_pct'] >= 0 else RED
    kpi_labels = ['This Year Value', 'Last Year Value', 'Change', 'Top Distributor', 'Top HQ', 'Low-Performing HQ']
    kpi_vals = [inr(kpis['total_cy_amt']), inr(kpis['total_ly_amt']),
                f"{'+' if kpis['overall_change_pct']>=0 else ''}{kpis['overall_change_pct']}%",
                kpis['top_distributor'] or '—',
                hq_summary.get('top_hq') or 'No HQ mapping',
                hq_summary.get('low_hq') or 'No HQ mapping']
    kpi_colors = [BLUE, DGRAY, growth_color, BLUE, BLUE, RED]
    n = len(kpi_labels)
    CW = 180*mm / n
    row0 = [Paragraph(kpi_labels[i], PS(f'kl{i}', fontName='DVSans-Bold', fontSize=6.8, textColor=DGRAY, leading=9)) for i in range(n)]
    row1 = [Paragraph(f'<b><font name="DVSans">{kpi_vals[i]}</font></b>',
                       PS(f'kv{i}', fontName='DVSans-Bold', fontSize=10.5, textColor=kpi_colors[i], leading=14)) for i in range(n)]
    kpi_row = Table([row0, row1], colWidths=[CW]*n)
    kpi_row.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LGRAY), ('BOX', (0,0), (-1,-1), 0.5, MGRAY),
        ('LINEAFTER', (0,0), (n-2,1), 0.5, WHITE),
        ('TOPPADDING', (0,0), (-1,0), 7), ('BOTTOMPADDING', (0,0), (-1,0), 2),
        ('TOPPADDING', (0,1), (-1,1), 2), ('BOTTOMPADDING', (0,1), (-1,1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 5), ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(kpi_row)
    story.append(Spacer(1, 10))

    # ── Distributor table: LY vs CY ──
    story.append(Paragraph('Distributor Sales — Last Year vs This Year',
                            PS('sh2', fontName='DVSans-Bold', fontSize=8.5, textColor=DGRAY, spaceAfter=5)))
    t_hdr = [ph('Distributor'), ph('LY Qty', TA_RIGHT), ph('LY Value', TA_RIGHT),
             ph('CY Qty', TA_RIGHT), ph('CY Value', TA_RIGHT), ph('Change', TA_RIGHT), ph('Action', TA_CENTER)]
    t_data = [t_hdr]
    for r in dist_rows:
        up = r['change_pct'] >= 0
        color = '#3B6D11' if up else '#A32D2D'
        change_str = f"{'+' if up else ''}{round(r['change_pct'],1)}%"
        action = 'Sustain momentum' if up else 'Needs distributor follow-up'
        t_data.append([
            Paragraph(r['distributor'], PS(f"d_{r['distributor'][:8]}", fontSize=7, leading=9)),
            pc(str(r['ly_qty']), align=TA_RIGHT), pc(inr(r['ly_amt']), align=TA_RIGHT),
            pc(str(r['cy_qty']), align=TA_RIGHT), pc(inr(r['cy_amt']), align=TA_RIGHT),
            pc(change_str, color, TA_RIGHT, bold=True),
            pc(action, color, TA_CENTER),
        ])
    t = Table(t_data, colWidths=[42*mm, 18*mm, 24*mm, 18*mm, 24*mm, 24*mm, 30*mm], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), LGRAY), ('LINEBELOW', (0,0), (-1,0), 0.5, MGRAY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, LGRAY]),
        ('LINEBELOW', (0,1), (-1,-2), 0.3, MGRAY), ('BOX', (0,0), (-1,-1), 0.5, MGRAY),
        ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # ── Smart result ──
    story.append(Paragraph('Smart Result — Timeline &amp; Action',
                            PS('sh3', fontName='DVSans-Bold', fontSize=8.5, textColor=DGRAY, spaceAfter=5)))
    story.append(Paragraph(bold_markup(ai['smart_result']['timeline']), PS('tl', fontSize=8.5, leading=13, spaceAfter=4)))
    for act in ai['smart_result']['action']:
        row = Table([[
            Paragraph('●', PS('dot', fontName='DVSans-Bold', fontSize=9, textColor=BLUE, leading=12)),
            Paragraph(bold_markup(act), PS('at', fontSize=8.5, leading=12)),
        ]], colWidths=[6*mm, 174*mm])
        row.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'),
                                  ('TOPPADDING', (0,0), (-1,-1), 1), ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                                  ('LEFTPADDING', (0,0), (-1,-1), 0)]))
        story.append(row)
    story.append(Spacer(1, 10))

    # ── Checklist ──
    story.append(Paragraph('Checklist — Doers &amp; Timeline',
                            PS('sh4', fontName='DVSans-Bold', fontSize=8.5, textColor=DGRAY, spaceAfter=5)))
    c_hdr = [ph('Section'), ph('Activity'), ph('Doer (1 only)'), ph('Action & Tools'), ph('End Date', TA_CENTER)]
    c_data = [c_hdr]
    for item in ai['checklist']:
        c_data.append([
            pc(item['section']), pc(item['activity']),
            pc(item['doer'], bold=True), pc(item['action_tools']),
            pc(item['end_date'], align=TA_CENTER),
        ])
    ct = Table(c_data, colWidths=[28*mm, 40*mm, 26*mm, 62*mm, 24*mm], repeatRows=1)
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), LGRAY), ('LINEBELOW', (0,0), (-1,0), 0.5, MGRAY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, LGRAY]),
        ('BOX', (0,0), (-1,-1), 0.5, MGRAY), ('LINEBELOW', (0,1), (-1,-2), 0.3, MGRAY),
        ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(ct)
    story.append(Spacer(1, 10))

    # ── Competitor analysis ──
    story.append(Paragraph('Competitor Analysis',
                            PS('sh5', fontName='DVSans-Bold', fontSize=8.5, textColor=DGRAY, spaceAfter=5)))
    k_hdr = [ph('Competitor'), ph('Product'), ph('Price', TA_RIGHT), ph('Feature')]
    k_data = [k_hdr]
    for row in ai['competitor_analysis']:
        k_data.append([pc(row['competitor'], bold=True), pc(row['product']),
                        pc(row['price'], align=TA_RIGHT), pc(row['feature'])])
    kt = Table(k_data, colWidths=[36*mm, 40*mm, 28*mm, 76*mm], repeatRows=1)
    kt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), LGRAY), ('LINEBELOW', (0,0), (-1,0), 0.5, MGRAY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, LGRAY]),
        ('BOX', (0,0), (-1,-1), 0.5, MGRAY), ('LINEBELOW', (0,1), (-1,-2), 0.3, MGRAY),
        ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(kt)
    story.append(Spacer(1, 10))

    # ── Creative note ──
    story.append(Paragraph('Creative',
                            PS('sh6', fontName='DVSans-Bold', fontSize=8.5, textColor=DGRAY, spaceAfter=5)))
    story.append(Paragraph('Creative execution: <b>PMT</b>. Feedback below is AI-generated.',
                            PS('cn', fontSize=8.5, leading=12, spaceAfter=4)))
    if creative_feedback:
        story.append(Paragraph(bold_markup(creative_feedback), PS('cf', fontSize=8.5, leading=12)))
    else:
        story.append(Paragraph('No creative draft was submitted for feedback in this run.',
                                PS('cf2', fontSize=8, textColor=DGRAY, leading=11)))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width='100%', thickness=0.5, color=MGRAY))
    story.append(Paragraph('Accurex Biomedical  |  Confidential  |  For internal use only',
                            PS('footer', fontSize=7.5, textColor=DGRAY, alignment=TA_CENTER, spaceBefore=5)))

    doc.build(story)
    return buf.getvalue()


# ── Streamlit UI ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container{padding-top:2rem}
.stButton>button{background:#1A56A0;color:white;border:none;border-radius:8px;padding:0.5rem 1.5rem;font-weight:500}
.stButton>button:hover{background:#154a8e}
.stDownloadButton>button{background:#1A56A0;color:white;border:none;border-radius:8px}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])
with col1:
    st.title("Campaign Report Card Generator")
    st.caption("Accurex Biomedical — AI-assisted campaign report, plan or close-out, in the same visual format as the Distributor Order Report Card")
with col2:
    if os.path.exists(DEFAULT_LOGO_PATH):
        st.image(DEFAULT_LOGO_PATH, width=120)

st.divider()

with st.sidebar:
    st.header("Settings")
    api_key_input = st.text_input("Anthropic API key", type="password",
                                   help="Falls back to the ANTHROPIC_API_KEY Streamlit secret if left blank. Never shared outside this session.")
    if api_key_input:
        st.session_state['api_key'] = api_key_input
    st.divider()
    logo_file = st.file_uploader("Override logo for this run (optional)", type=['jpg', 'jpeg', 'png'])
    if logo_file:
        logo_bytes = logo_file.read()
    elif os.path.exists(DEFAULT_LOGO_PATH):
        with open(DEFAULT_LOGO_PATH, 'rb') as f:
            logo_bytes = f.read()
    else:
        logo_bytes = None
    st.divider()
    st.caption("**Sales file expected:**\nOne sheet per distributor, with two column blocks "
               "(Last Year / This Year), each containing Product, Qty and Amount columns. "
               "Header row is auto-detected within the first 6 rows of each sheet.")
    hq_file = st.file_uploader("Distributor → HQ mapping (optional CSV/XLSX, columns: Distributor, HQ)",
                                type=['csv', 'xlsx'])

st.subheader("1. Campaign details")
c1, c2, c3 = st.columns(3)
with c1:
    product = st.text_input("Product (per Tally)", placeholder="e.g. Acculab CBC 360 Neo")
    camp_type = st.selectbox("Campaign type", ["Primary (Distributor / Sales Admin)", "Secondary (Customer / MIS)"])
with c2:
    duration = st.text_input("Duration", placeholder="e.g. 3 months (Nov 2026 - Jan 2027)")
    stage = st.selectbox("Report stage", ["Launch (Plan)", "Close (Actual Results)"])
with c3:
    pmt_names = st.text_input("PMT doer names (comma-separated, optional)", placeholder="e.g. Rohan, Priya")

goal = st.text_area("Campaign goal & expected output", placeholder="What is the goal, and what output is expected?")
idea = st.text_area("Rough campaign idea", placeholder="Rough idea for the campaign; mention named competitors here if relevant")
usp = st.text_input("Technical USP (mandatory)", placeholder="Technical USP only — not product features")

st.subheader("2. Tasks")
st.caption("One task per row: name and frequency (e.g. 'Calling to distributor — daily').")
num_tasks = st.number_input("Number of tasks", min_value=1, max_value=15, value=4)
tasks = []
tcols = st.columns(2)
for i in range(num_tasks):
    with tcols[i % 2]:
        t_name = st.text_input(f"Task {i+1}", key=f"task_{i}")
        t_freq = st.text_input(f"Frequency {i+1}", key=f"freq_{i}")
        if t_name:
            tasks.append({"name": t_name, "frequency": t_freq})

st.subheader("3. Creative (optional)")
creative_text = st.text_area("Paste PMT's creative copy/brief for AI feedback (optional)")

st.subheader("4. Sales data")
uploaded = st.file_uploader("Upload sales Excel file", type=['xlsx', 'xls'])

st.divider()

if uploaded and product and goal and idea and usp:
    xl = pd.ExcelFile(uploaded)
    dist_data = {}
    with st.spinner("Parsing distributor sheets..."):
        for sheet in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet, header=None)
            ly, cy = parse_sheet(df)
            ly = filter_by_product(ly, product)
            cy = filter_by_product(cy, product)
            if ly or cy:
                dist_data[sheet.strip()] = (ly, cy)

    if not dist_data:
        st.warning("No matching rows found for this product across any sheet. "
                   "Check the product name matches what's in the file, or leave it broader.")
    else:
        st.success(f"Parsed **{len(dist_data)}** distributor sheets with data for '{product}'")

        hq_map = {}
        if hq_file:
            hq_df = pd.read_csv(hq_file) if hq_file.name.endswith('.csv') else pd.read_excel(hq_file)
            cols_lower = {c.lower(): c for c in hq_df.columns}
            if 'distributor' in cols_lower and 'hq' in cols_lower:
                hq_map = dict(zip(hq_df[cols_lower['distributor']], hq_df[cols_lower['hq']]))
            else:
                st.warning("HQ mapping file needs 'Distributor' and 'HQ' columns — ignoring it for this run.")

        kpis, dist_rows = compute_kpis(dist_data)
        hq_summary = compute_hq_summary(dist_rows, hq_map)

        with st.expander("Preview parsed sales KPIs", expanded=True):
            st.json(kpis)
            if hq_map:
                st.json(hq_summary)
            else:
                st.caption("No distributor → HQ mapping supplied — HQ rollups will show 'No HQ mapping'.")

        if st.button("Generate campaign report"):
            client = get_client()
            if not client:
                st.error("No Anthropic API key available. Enter one in the sidebar, or set ANTHROPIC_API_KEY as a Streamlit secret.")
            else:
                campaign = {
                    'product': product, 'camp_type': camp_type, 'duration': duration,
                    'stage': stage, 'goal': goal, 'idea': idea, 'usp': usp,
                    'tasks': tasks, 'pmt_names': pmt_names,
                }
                with st.spinner("Generating AI sections (smart result, checklist, competitor analysis)..."):
                    ai = generate_ai_sections(client, campaign, kpis, hq_summary.get('by_hq', {}))
                creative_feedback = None
                if creative_text.strip():
                    with st.spinner("Generating creative feedback..."):
                        creative_feedback = generate_creative_feedback(client, creative_text, campaign)

                pdf_bytes = generate_pdf(campaign, kpis, dist_rows, hq_summary, ai, creative_feedback, logo_bytes)
                fname = f"{product.replace(' ', '_')}_Campaign_Report_{date.today().strftime('%b_%Y')}.pdf"
                st.success("Report generated.")
                st.download_button("⬇ Download Campaign Report Card", data=pdf_bytes,
                                    file_name=fname, mime='application/pdf')
else:
    st.info("Fill in product, goal, idea, USP and upload the sales file to continue.")
