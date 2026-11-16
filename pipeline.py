"""
The thinking part. Five AI steps, each building on the previous one:

  1. Analyst            reads the computed numbers -> insights, per-distributor actions
  2. Market researcher  live web search -> competitor products/prices, how competitors run
                        campaigns, what Accurex is missing
  3. Strategist         company goal + data + research -> motto, objective, technical USPs,
                        mechanics, incentive slabs, phases, checklist (doer + frequency), forecast
  4. Creative director  brand guide -> creative brief per vertical and channel (sizes, colours,
                        copy, visuals) + the campaign cockpit design
  5. Reviewer           challenges the plan against the company goal; weak plans go back to the
                        strategist once with the reviewer's fixes
"""
from __future__ import annotations

import json

SYSTEM = ("You are the AI Marketing Manager of Accurex Biomedical, an Indian IVD company. You think "
          "like a director: every recommendation must move a number that serves the company goal. "
          "Be specific (names, rupee figures, dates, owners), never generic. Use the exact numbers "
          "you are given; never invent sales figures. Indian business context, rupees, Indian "
          "English. Keep text short and scannable for management. "
          "MONEY: copy figures exactly as given; write them as ₹ X.XX L (lakh) or ₹ X.XX Cr (crore), where "
          "1 Cr = 100 L; double-check the unit before writing any figure. "
          "FACTS ONLY: never state product specifications, performance numbers, test menus, certifications, "
          "installations, customer names or testimonials unless they appear in the product knowledge or the facts "
          "given. Where such a detail would help, write a placeholder like [PMT to confirm: sample volume per test]. "
          "Output only JSON.")


def find_product(kb: dict, name: str):
    n = name.lower().strip()
    exact = [p for p in kb.get("products", []) if p["name"].lower() == n]
    if exact:
        return exact[0]
    cands = [p for p in kb.get("products", []) if p["name"].lower() in n or n in p["name"].lower()]
    return max(cands, key=lambda p: len(p["name"])) if cands else None


def _competitors(kb, product):
    allc = kb.get("competitors", [])
    cat = (product or {}).get("competitor_category")
    same = [c for c in allc if cat and c.get("category", "").lower() == cat.lower()]
    return same or ([] if cat else allc)


def _ctx(kb: dict, brief: dict) -> str:
    c = kb.get("company", {})
    product = find_product(kb, brief["product"])
    return f"""COMPANY: {c.get('name')} - {c.get('industry')}
Business model: {c.get('business_model')}
Company goals: {json.dumps(c.get('goals', []))}
Hierarchy (use these roles as task owners): {json.dumps([h['role'] + ': ' + h['owns'] for h in kb.get('hierarchy', [])])}

CAMPAIGN BRIEF (from the marketing executive):
- Product: {brief['product']}
- Product knowledge: {json.dumps(product) if product else brief.get('product_notes') or 'n/a'}
- Campaign type: {brief['camp_type']}
- Duration: {brief['duration']} (start {brief.get('start_date', 'n/a')})
- Stage: {brief['stage']}
- Campaign goal: {brief['goal']}
- Rough idea: {brief['idea'] or 'none given - propose one'}
- Technical USP from executive: {brief['usp'] or 'not given - derive from product knowledge'}
- Tasks executive wants included: {json.dumps(brief.get('tasks', []))}
- Budget: {brief.get('budget') or 'not given'}
- Known competitors for this product: {json.dumps(_competitors(kb, product)) if _competitors(kb, product) else 'none listed - identify them from the product category'}
- Extra competitor sheet data: {brief.get('competitor_sheet') or 'none'}
- Who is on the uploaded contact list: {brief.get('contact_audience') or 'no contact list'}"""


# ── 1. Analyst ───────────────────────────────────────────────────────────────
def analyst(ai, kb, brief, facts):
    p = f"""{_ctx(kb, brief)}

SALES FACTS (computed exactly by code from the uploaded file):
{facts}

Analyse like a sales director. Return JSON:
{{
 "headline": "one sentence: the single most important thing the data says",
 "insights": [{{"title": "...", "detail": "with exact figures", "so_what": "what we must do about it"}}],   // 4-5
 "distributor_actions": [{{"distributor": "exact name", "segment": "...", "action": "specific next step with a rupee or unit target", "owner": "role from hierarchy", "by_when": "Week N"}}],  // top 12 by impact, include Lost/Declining/Untapped
 "risks": ["..."]   // 2-3
}}"""
    return ai.json(p, system=SYSTEM, max_tokens=3000)


# ── 2. Market researcher (web) ───────────────────────────────────────────────
def researcher(ai, kb, brief, items=""):
    p = f"""{_ctx(kb, brief)}

ITEMS ACTUALLY SOLD under this campaign (use them to identify the product category correctly,
e.g. GPT / creatinine / HbA1c reagents = clinical chemistry; CBC diluent / lyse = hematology):
{items or 'n/a'}

First decide the exact product category. Then research the Indian market for that category
using web search (current year).
1. Competitor products: for each known competitor plus any other major player, the comparable
   product, approximate Indian price (instrument and/or per-test reagent cost; write 'approx.' or
   'not public' honestly), 2-3 key specs, and positioning.
2. How IVD companies in India actually run marketing campaigns for distributors and labs
   (e.g. distributor incentive schemes, reagent-rental / placement offers, CME and lab-tech
   training, demo camps, conferences, WhatsApp/LinkedIn content, KOL testimonials, EQAS/quality
   messaging). Name the company and the tactic.
3. Gap analysis: what competitors do that Accurex (per the brief) is not doing, with a priority.

Return JSON:
{{
 "competitors": [{{"company": "", "product": "", "price": "", "key_specs": "", "positioning": "", "source": "site or 'industry knowledge'"}}],
 "industry_playbook": [{{"company": "", "tactic": "", "channel": "", "why_it_works": ""}}],   // 6-8
 "gaps": [{{"what_others_do": "", "accurex_today": "", "recommendation": "", "priority": "High|Medium|Low"}}],  // 4-6
 "market_notes": "2 sentences on market size / trend, if found"
}}"""
    return ai.json(p, system=SYSTEM, web=True, max_tokens=4000)


# ── 3. Strategist ────────────────────────────────────────────────────────────
def strategist(ai, kb, brief, facts, analysis, research, review_feedback=None):
    fix = ""
    if review_feedback:
        fix = f"\nA REVIEWER REJECTED THE PREVIOUS DRAFT. Fix every issue:\n{json.dumps(review_feedback)}\n"
    p = f"""{_ctx(kb, brief)}

SALES FACTS:
{facts}

ANALYST VIEW: {json.dumps(analysis)}
MARKET RESEARCH: {json.dumps(research)}
{fix}
Build the full campaign plan. The campaign exists to sell more of this product; tie everything
to the rupee gap. If the facts say there is no last-year data, base targets on this period's
run-rate and never claim growth versus last year. If instruments and reagents are both present,
treat reagent pull-through on the installed base as a lever. If a contact list is present, use it
(the drip campaign to labs is planned in detail in a later step; reference it as a mechanic). Technical USPs must be technical (measurable specs/performance vs a named
competitor), not generic features. Every checklist line has exactly ONE doer (a role from the
hierarchy) and a frequency (Daily / Weekly / Fortnightly / Monthly / One-time). Include the
executive's tasks. Use the checklist sections {kb.get('checklist_structure')}.

Return JSON:
{{
 "campaign_name": "short, memorable",
 "motto": "one line rallying the distributor network, on brand voice (no exclamation marks)",
 "objective": {{"statement": "", "target_value": "Rs figure", "target_growth_pct": 0, "measure": "how it is measured and from which data (Sales Admin primary / MIS secondary)"}},
 "management_summary": ["4-5 bullets a director reads in 20 seconds; bold key numbers with **"],
 "technical_usps": [{{"usp": "", "proof": "spec/number ONLY if it is in Product knowledge, else [PMT to confirm: which spec]", "vs_competitor": "named competitor; compare only on facts given, else [PMT to confirm]"}}],   // 3
 "decisions_needed": [{{"decision": "what management must approve", "why": "one line", "cost": "Rs or effort"}}],   // 2-3
 "target_segments": [{{"segment": "Star|Growing|Declining|Lost|New|Untapped", "distributors": ["names"], "play": "what we do with them", "expected_value": "Rs"}}],
 "mechanics": [{{"name": "", "how_it_works": "", "owner": "role"}}],   // 3-5 campaign mechanics (scheme, contest, demo drive...)
 "incentive_scheme": {{"type": "", "slabs": [{{"slab": "e.g. 110-120% of LY", "reward": ""}}], "budget_note": ""}},
 "phases": [{{"phase": "", "weeks": "Week 1-2", "focus": "", "milestone": "measurable"}}],   // 3-4
 "checklist": [{{"section": "", "activity": "", "doer": "ONE role", "frequency": "", "tool": "WhatsApp / call / CRM / deck...", "deadline": "Week N", "kpi": ""}}],   // 12-16
 "kpis": [{{"kpi": "", "target": "", "frequency": "", "source": ""}}],   // 5-6
 "forecast": {{"conservative": "Rs", "target": "Rs", "stretch": "Rs", "assumptions": ["..."]}},
 "competitor_response": "how we answer the strongest competitor's offer"
}}"""
    return ai.json(p, system=SYSTEM, max_tokens=6000)


# ── 3b. Campaign namer ───────────────────────────────────────────────────────
def namer(ai, kb, brief, plan, research):
    comp = [c.get("company") for c in research.get("competitors", [])][:8]
    p = f"""{_ctx(kb, brief)}

CAMPAIGN PLAN: objective={json.dumps(plan.get('objective'))}, mechanics={json.dumps([m.get('name') for m in plan.get('mechanics', [])])},
working name={plan.get('campaign_name')}, competitors={comp}

Create the campaign name. It must be UNIQUE and memorable, yet clearly from the IVD / clinical
laboratory world: borrow the language labs live in (calibration, QC, control levels, assay,
run, cuvette, reagent, accuracy, precision, turnaround, sample, Westgard, NABL, result, flag),
or a clever play on the product name or number. 1-3 words. No generic words like 'Growth
Drive', 'Mega', 'Bonanza', 'Utsav', 'Champions'. Must work for distributors AND labs, in Indian
English, and sit well with a factual brand voice (no exclamation marks).
Use web search to make sure the top options are not existing campaign or product names of
Indian IVD companies. Give 5 options, then pick one.

Return JSON:
{{
 "options": [{{"name": "", "tagline": "one-line motto", "idea": "why it fits IVD and this campaign", "conflict_check": "what the search found"}}],
 "chosen": "one of the option names",
 "why_chosen": "one sentence"
}}"""
    return ai.json(p, system=SYSTEM, web=True, max_tokens=2000)


# ── Guard against invented technical specs ───────────────────────────────────
import re as _re

SPEC_RX = _re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:-|–|to)?\s*\d*(?:[.,]\d+)?\s*"
                      r"(?:µl\b|ul\b|μl\b|nm\b|°\s?c\b|deg\s?c\b|tests?\s*/\s*h(?:ou)?r|tests?\s+per\s+hour|t/h\b|tph\b|"
                      r"samples?\s*/\s*h(?:ou)?r|reagent\s+positions?|sample\s+positions?|cuvettes?\b|"
                      r"%\s*carry)", _re.I)


def flag_unverified(result: dict, kb: dict) -> list[dict]:
    """Any technical spec number in AI text that is not in the knowledge base is marked in place
    (⚠ unverified) and listed, so nobody sends an invented spec to a customer."""
    known = json.dumps(kb, ensure_ascii=False).lower().replace(" ", "")
    found = []

    def walk(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("research",):
                    continue
                obj[k] = walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(obj)]
        elif isinstance(obj, str):
            def mark(m):
                tok = m.group(0)
                if tok.lower().replace(" ", "") in known or "unverified" in obj[m.end():m.end() + 14]:
                    return tok
                found.append({"where": path.strip("."), "claim": tok.strip()})
                return f"{tok} [⚠ unverified]"
            return SPEC_RX.sub(mark, obj)
        return obj

    for key in ("plan", "creative", "drip"):
        if key in result:
            result[key] = walk(result[key], key)
    return found


# ── 4. Creative director ─────────────────────────────────────────────────────
def creative(ai, kb, brief, plan):
    p = f"""{_ctx(kb, brief)}

BRAND GUIDE: {json.dumps(kb.get('brand_guide'))}
CREATIVE SIZE SPECS: {json.dumps(kb.get('creative_specs'))}
VERTICALS: {json.dumps(kb.get('verticals'))}
CAMPAIGN PLAN: name={plan.get('campaign_name')}, motto={plan.get('motto')},
USPs={json.dumps(plan.get('technical_usps'))}, mechanics={json.dumps(plan.get('mechanics'))},
phases={json.dumps(plan.get('phases'))}

You are the creative director. Write a brief the Digital Marketing team can execute without
asking questions. Pick the 3-4 verticals that matter for this product. For each, 2-4 assets
with exact size from the specs, exact hex colours from the brand guide, headline and body copy
(on brand voice, no exclamation marks), visual direction, CTA and posting frequency. Also design
the CAMPAIGN COCKPIT: the one-page dashboard management sees weekly (zones, what each shows,
chart type, colour rules).

Return JSON:
{{
 "big_idea": "the creative concept in one line",
 "key_message": "",
 "tone": "",
 "verticals": [{{"vertical": "", "audience": "who exactly", "message_angle": "", "assets": [
    {{"asset": "", "channel": "", "size": "", "headline": "", "body_copy": "", "visual_direction": "", "colours": "hex codes and where", "cta": "", "frequency": "", "phase": ""}}]}}],
 "content_calendar": [{{"week": "Week 1", "posts": "what goes out where"}}],
 "cockpit_design": {{"zones": [{{"zone": "e.g. Top strip", "shows": "", "visual": "chart/tile type", "colour_rule": ""}}], "update_frequency": "", "owner": "role"}},
 "dos": ["..."], "donts": ["..."]
}}"""
    return ai.json(p, system=SYSTEM, max_tokens=6000)


# ── 4b. Drip campaign planner (only when a contact list is uploaded) ─────────
def drip(ai, kb, brief, facts, plan, creative_out):
    p = f"""{_ctx(kb, brief)}

BRAND GUIDE: {json.dumps(kb.get('brand_guide'))}
FACTS (includes the contact list summary and sample names):
{facts}
CAMPAIGN: name={plan.get('campaign_name')}, motto={plan.get('motto')}, USPs={json.dumps(plan.get('technical_usps'))},
big idea={creative_out.get('big_idea')}

Plan the WhatsApp / SMS DRIP CAMPAIGN to these labs, hospitals and diagnostic centres. They are
end customers (secondary market); orders flow through distributors. Read 'Who is on the uploaded
contact list' in the brief: if they are EXISTING USERS of the instrument, the drip must drive reagent
re-orders and test-menu expansion (pull-through), not instrument sales; if PROSPECTS, drive demos
and placements; if mixed or unknown, write messages that work for both and say so. Segment the list by customer
type and by region (infer regions from place names in the sample), and write a 5-7 touch sequence
spread over the campaign. Each message must be short (under 60 words), factual, on brand voice (no
exclamation marks, no emojis overload, no hype), personalised with {{{{lab_name}}}}, and end with
one clear CTA (reply for demo / call / order through your distributor). Include an opt-out line
where required. Note WhatsApp Business template approval and DND/consent rules for India.

Return JSON:
{{
 "audience_summary": "2 sentences",
 "segments": [{{"segment": "", "who": "type and regions", "approx_count": "", "angle": ""}}],   // 3-5
 "sequence": [{{"touch": 1, "day": "Day 0", "channel": "WhatsApp", "objective": "", "message": "", "media": "image/video/PDF + size", "cta": "", "owner": "role"}}],
 "follow_up_rules": ["e.g. replied 'demo' -> Application Specialist calls within 24h"],
 "kpis": [{{"kpi": "", "target": ""}}],
 "compliance": ["..."],
 "list_hygiene": ["what to fix in the contact list before sending"]
}}"""
    return ai.json(p, system=SYSTEM, max_tokens=4500)


# ── 5. Reviewer ──────────────────────────────────────────────────────────────
def reviewer(ai, kb, brief, facts, plan):
    p = f"""{_ctx(kb, brief)}

SALES FACTS:
{facts}

PLAN TO REVIEW: {json.dumps(plan)}

You are the Director reviewing this plan before approval. Be tough. Check: does it close the
rupee gap with realistic numbers; are targets tied to named distributors; are USPs truly
technical; does every task have one owner and a frequency; is the incentive affordable; is
anything important missing (data tracking, secondary sales, training, competitor answer)?

Return JSON:
{{
 "score": 0-10,
 "verdict": "Approve | Approve with changes | Rework",
 "aligned_with_company_goal": true|false,
 "strengths": ["..."],
 "issues": [{{"area": "", "issue": "", "fix": ""}}],
 "director_questions": ["questions management will ask in the review meeting"]
}}"""
    return ai.json(p, system=SYSTEM, max_tokens=2500)


# ── Orchestration ────────────────────────────────────────────────────────────
def run_all(ai, kb, brief, facts, progress=lambda step, msg: None, min_score=7):
    out = {}
    progress(1, "Analysing your sales data")
    out["analysis"] = analyst(ai, kb, brief, facts)
    progress(2, "Researching competitors and the IVD market (web search)")
    try:
        items = facts.split("\nITEMS", 1)[1].split("\n\n", 1)[0] if "\nITEMS" in facts else ""
        out["research"] = researcher(ai, kb, brief, items)
    except Exception as e:
        out["research"] = {"competitors": [], "industry_playbook": [], "gaps": [],
                           "market_notes": f"Research step failed: {e}"}
    progress(3, "Building the campaign strategy")
    out["plan"] = strategist(ai, kb, brief, facts, out["analysis"], out["research"])
    progress(5, "Director review of the plan")
    out["review"] = reviewer(ai, kb, brief, facts, out["plan"])
    if float(out["review"].get("score", 10)) < min_score:
        progress(3, f"Plan scored {out['review'].get('score')}/10 - reworking with the reviewer's fixes")
        out["plan"] = strategist(ai, kb, brief, facts, out["analysis"], out["research"],
                                 review_feedback=out["review"].get("issues"))
        out["first_review"] = out["review"]
        out["review"] = reviewer(ai, kb, brief, facts, out["plan"])
    progress(3, "Naming the campaign (checking names are not already used)")
    try:
        out["naming"] = namer(ai, kb, brief, out["plan"], out["research"])
        pick = next((o for o in out["naming"].get("options", []) if o.get("name") == out["naming"].get("chosen")),
                    (out["naming"].get("options") or [None])[0])
        if pick:
            out["plan"]["campaign_name"], out["plan"]["motto"] = pick["name"], pick.get("tagline") or out["plan"].get("motto")
    except Exception as e:
        out["naming"] = {"options": [], "error": str(e)}
    progress(4, "Writing the creative brief and cockpit design")
    out["creative"] = creative(ai, kb, brief, out["plan"])
    if "CONTACT LIST" in facts:
        progress(4, "Planning the drip campaign to the uploaded labs")
        out["drip"] = drip(ai, kb, brief, facts, out["plan"], out["creative"])
    out["unverified"] = flag_unverified(out, kb)
    progress(6, "Done")
    return out
