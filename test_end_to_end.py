"""
Offline end-to-end test: four file layouts -> tidy data -> analytics -> 5-step pipeline (with a
fake AI that returns realistic JSON) -> PDF, Word and Excel outputs.
Run from the repo root:  python -m tests.test_end_to_end
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import pipeline  # noqa: E402
from core.analytics import analyse, facts_for_ai  # noqa: E402
import pandas as pd  # noqa: E402

from core.data_reader import combine, fuzzy_products, read_file, read_sales  # noqa: E402
from reports.office_exports import build_docx, build_tracker  # noqa: E402
from reports.pdf_report import build_management, build_pdf, build_playbook  # noqa: E402
from tests.make_samples import CBC, OUT, write_all  # noqa: E402

KB = json.load(open(os.path.join(os.path.dirname(OUT), "..", "knowledge", "company.json"), encoding="utf-8"))


class FakeAI:
    """Answers each pipeline prompt with plausible JSON; first review fails to test the rework loop."""
    def __init__(self):
        self.calls, self.reviews = [], 0

    def json(self, prompt, system="", web=False, max_tokens=0):
        self.calls.append((prompt[:60], web))
        if "Work out its structure" in prompt and "Sales Report" in prompt:
            # reproduces the real bug: the AI stops the instrument table where the preview stopped (r13)
            cols = lambda n, q, a: {"name": n, "qty": q, "amount": a}  # noqa: E731
            return {"blocks": [
                {"sheets": ["Sales Report"], "title": "Acculab 200 Instrument Sales April 2026 - October 2026", "kind": "by_distributor",
                 "header_row": 1, "last_row": 13, "columns": cols(0, 1, 2), "product_label": "Acculab 200 Instrument",
                 "category": "instrument", "period": "CY", "period_label": "Apr-Oct 2026"},
                {"sheets": ["Sales Report"], "title": "Acculab 200 Reagents Sales April 2026 - October 2026", "kind": "by_product",
                 "header_row": 1, "last_row": None, "columns": cols(4, 5, 6), "category": "consumable", "period": "CY",
                 "period_label": "Apr-Oct 2026"}], "notes": "Instrument and reagent tables, same period."}
        if "Work out its structure" in prompt:
            # what a model would answer for layout 4 (tab per year)
            return {"blocks": [{"sheets": ["Apr-Oct 2025", "Apr-Oct 2026"], "title": "Sales", "kind": "by_distributor_product",
                                "header_row": 0, "columns": {"distributor": 0, "hq": 1, "product": 2, "qty": 3, "amount": 4},
                                "sheet_periods": {"Apr-Oct 2025": "LY", "Apr-Oct 2026": "CY"}, "category": "mixed"}],
                    "notes": "One tab per year."}
        if "Create the campaign name" in prompt:
            assert web, "naming must check names on the web"
            return {"options": [{"name": "Precision Pact 200", "tagline": "Every run, every reagent, on record.",
                                 "idea": "Precision is the lab's core value; 200 ties it to the analyser", "conflict_check": "No IVD campaign found"},
                                {"name": "Calibrate 200", "tagline": "Set the standard in every lab.", "idea": "Calibration language", "conflict_check": "Clear"}],
                    "chosen": "Precision Pact 200", "why_chosen": "Distinct, lab-native, works for distributors and labs."}
        if "DRIP CAMPAIGN" in prompt:
            return {"audience_summary": "531 labs across West Bengal, UP, Rajasthan, Odisha and Maharashtra.",
                    "segments": [{"segment": "Pathology labs East", "who": "Labs in WB/Odisha", "approx_count": "180", "angle": "Reagent cost per test"}],
                    "sequence": [{"touch": 1, "day": "Day 0", "channel": "WhatsApp", "objective": "Introduce", "message": "Dear {{lab_name}}, Autopure reagents for your Acculab 200 now ship in 48 hours through your distributor.",
                                  "media": "Image 1080x1080", "cta": "Reply ORDER", "owner": "Digital Marketing Team"}],
                    "follow_up_rules": ["Reply ORDER -> distributor calls within 24h"], "kpis": [{"kpi": "Reply rate", "target": "8%"}],
                    "compliance": ["Use approved WhatsApp Business templates"], "list_hygiene": ["Fix 4 invalid numbers"]}
        if "Select every item" in prompt:
            return {"selected": CBC, "reason": "Analyser plus its RFID reagents, cleaner and controls."}
        if "Analyse like a sales director" in prompt:
            return {"headline": "Growth is carried by **3 distributors**; Vardhman bought nothing this year.",
                    "insights": [{"title": "Concentration", "detail": "Top 3 hold **62%** of value", "so_what": "Spread risk"},
                                 {"title": "Lost account", "detail": "Vardhman Surgicals ₹4.1 L LY, ₹0 CY", "so_what": "Win-back visit in Week 1"}],
                    "distributor_actions": [
                        {"distributor": "Vardhman Surgicals", "segment": "Lost", "action": "Win-back meeting; offer 5% reagent scheme on ₹3 L order", "owner": "Regional / Area Sales Manager", "by_when": "Week 1"},
                        {"distributor": "Shree Sai Enterprises", "segment": "Declining", "action": "Install-base audit; recover 40 diluent units", "owner": "Application Specialist", "by_when": "Week 2"},
                        {"distributor": "Sanjeevani Distributors", "segment": "Untapped", "action": "Demo at 3 labs; first analyser placement", "owner": "PMT (Product Management Team)", "by_when": "Week 3"},
                        {"distributor": "Litmus", "segment": "Star", "action": "Reference site visit for 2 prospects", "owner": "Marketing Manager", "by_when": "Week 4"}],
                    "risks": ["Reagent stock-outs at RFID SKUs", "Competitor reagent-rental offers"]}
        if "Research the Indian market" in prompt:
            assert web, "research step must request web search"
            return {"competitors": [{"company": "Mindray", "product": "BC-30s", "price": "approx. ₹3.5-4 L", "key_specs": "3-part, 60 T/hr", "positioning": "Value leader", "source": "industry knowledge"},
                                    {"company": "Sysmex", "product": "XP-100", "price": "approx. ₹5 L", "key_specs": "3-part, 60 T/hr", "positioning": "Premium reliability", "source": "industry knowledge"}],
                    "industry_playbook": [{"company": "Transasia", "tactic": "Reagent-rental placements", "channel": "Distributors", "why_it_works": "Zero capex for labs"},
                                          {"company": "Mindray", "tactic": "CME for pathologists", "channel": "Events", "why_it_works": "KOL credibility"}],
                    "gaps": [{"what_others_do": "Monthly distributor leaderboards", "accurex_today": "Ad hoc", "recommendation": "Weekly scoreboard on WhatsApp", "priority": "High"}],
                    "market_notes": "Indian hematology analyser market is growing with tier-2 lab expansion."}
        if "Build the full campaign plan" in prompt:
            fixed = "REVIEWER REJECTED" in prompt
            return {"campaign_name": "Count On 360", "motto": "Every count, every lab, every week.",
                    "objective": {"statement": "Grow CBC 360 Neo value 20% over last year in West", "target_value": "₹62 L", "target_growth_pct": 20, "measure": "Sales Admin primary data, weekly"},
                    "management_summary": ["Gap to close: **₹9.8 L** in 12 weeks", "Win back **Vardhman** and convert **Sanjeevani**",
                                           "Weekly scoreboard drives the top 5", "Expected outcome **₹58-66 L**" + (" (reworked)" if fixed else "")],
                    "technical_usps": [{"usp": "RFID reagent tracking", "proof": "Lot and expiry auto-read", "vs_competitor": "Mindray BC-30s has manual entry"},
                                       {"usp": "Low dispense volume", "proof": "Dispenses as low as 0.1 µL; cooled tray 2-14°C", "vs_competitor": "vs 10 µL on others"}],
                    "decisions_needed": [{"decision": "Approve ₹3 L incentive pool", "why": "Funds the slabs", "cost": "₹3 L"}],
                    "target_segments": [{"segment": "Lost", "distributors": ["Vardhman Surgicals"], "play": "Win-back scheme", "expected_value": "₹3 L"}],
                    "mechanics": [{"name": "360 League", "how_it_works": "Weekly leaderboard, slab rewards", "owner": "Marketing Manager"}],
                    "incentive_scheme": {"type": "Slab on growth over LY", "slabs": [{"slab": "110-120%", "reward": "2% credit note"}, {"slab": ">120%", "reward": "3.5% credit note + trophy"}], "budget_note": "Approx. ₹1.8 L at target"},
                    "phases": [{"phase": "Ignite", "weeks": "Week 1-2", "focus": "Launch + training", "milestone": "All 10 distributors briefed"}],
                    "checklist": [{"section": "Back End Activities", "activity": "Pull LY/CY data", "doer": "Sales Admin", "frequency": "Weekly", "tool": "Tally", "deadline": "Week 1", "kpi": "Data on Monday 11am"},
                                  {"section": "Execution", "activity": "Calling to distributor", "doer": "Regional / Area Sales Manager", "frequency": "Daily", "tool": "Phone + CRM", "deadline": "Ongoing", "kpi": "10 calls/day"}],
                    "kpis": [{"kpi": "Value vs LY", "target": "+20%", "frequency": "Weekly", "source": "Sales Admin"}],
                    "forecast": {"conservative": "₹58 L", "target": "₹62 L", "stretch": "₹66 L", "assumptions": ["Vardhman returns at 70% of LY"]},
                    "competitor_response": "Counter reagent-rental with a 12-month reagent price lock."}
        if "creative director" in prompt:
            return {"big_idea": "The count you can trust", "key_message": "RFID-tracked accuracy, run after run", "tone": "Factual, precise",
                    "verticals": [{"vertical": "Standalone pathology labs", "audience": "Lab owners, tier-2 West", "message_angle": "No wasted reagent",
                                   "assets": [{"asset": "WhatsApp post", "channel": "Distributor groups", "size": "1080 x 1080 px", "headline": "Zero expired reagent runs",
                                               "body_copy": "RFID reads lot and expiry automatically.", "visual_direction": "Close-up of RFID pack on analyser, candid lab light",
                                               "colours": "#F28421 headline bar, #231F20 text, white bg", "cta": "Book a demo", "frequency": "Twice a week", "phase": "Ignite"}]}],
                    "content_calendar": [{"week": "Week 1", "posts": "Launch post, scoreboard template"}],
                    "cockpit_design": {"zones": [{"zone": "Top strip", "shows": "LY, CY, gap", "visual": "KPI tiles", "colour_rule": "Orange for gap"}], "update_frequency": "Weekly", "owner": "MIS"},
                    "dos": ["Show real lab photos"], "donts": ["No exclamation marks"]}
        if "Director reviewing" in prompt:
            self.reviews += 1
            if self.reviews == 1:
                return {"score": 5, "verdict": "Rework", "aligned_with_company_goal": False, "strengths": ["Clear data"],
                        "issues": [{"area": "Targets", "issue": "Not tied to distributors", "fix": "Name a target per distributor"}], "director_questions": []}
            return {"score": 8, "verdict": "Approve with changes", "aligned_with_company_goal": True, "strengths": ["Targets tied to names", "Clear owners"],
                    "issues": [{"area": "Budget", "issue": "Incentive cost not capped", "fix": "Cap at ₹2 L"}],
                    "director_questions": ["What if Vardhman does not return?"]}
        raise AssertionError("unexpected prompt: " + prompt[:120])


def main():
    truth = write_all()
    t_ly = truth[truth.period == "LY"].amount.sum()
    t_cy = truth[truth.period == "CY"].amount.sum()
    print(f"truth LY {t_ly:,.0f}  CY {t_cy:,.0f}")

    # Rule-based reading (no AI) for all four layouts
    for f in sorted(os.listdir(OUT)):
        if not f.endswith(".xlsx") or not f[0].isdigit():
            continue
        b = open(os.path.join(OUT, f), "rb").read()
        try:
            tidy, m, _ = read_sales(b, f)
            ly, cy = tidy[tidy.period == "LY"].amount.sum(), tidy[tidy.period == "CY"].amount.sum()
            ok = abs(ly - t_ly) < 1 and abs(cy - t_cy) < 1
            print(f"[rules] {f:32s} dists={tidy.distributor.nunique():2d} LY {ly:,.0f} CY {cy:,.0f} {'OK' if ok else 'MISMATCH'}")
        except Exception as e:
            print(f"[rules] {f:32s} could not read without AI: {e}")

    # AI-assisted reading for layout 4 (the one rules can't decide LY/CY for)
    ai = FakeAI()
    f = "4_tab_per_year.xlsx"
    tidy, m, _ = read_sales(open(os.path.join(OUT, f), "rb").read(), f, ai=ai)
    ly, cy = tidy[tidy.period == "LY"].amount.sum(), tidy[tidy.period == "CY"].amount.sum()
    assert abs(ly - t_ly) < 1 and abs(cy - t_cy) < 1, (ly, cy)
    print(f"[AI]    {f:32s} LY {ly:,.0f} CY {cy:,.0f} OK")

    # Product selection + analytics on the Tally-style file
    tidy, m, _ = read_sales(open(os.path.join(OUT, "1_tab_per_distributor.xlsx"), "rb").read(), "1.xlsx")
    fz = fuzzy_products(tidy, "Acculab CBC 360 Neo")
    print("fuzzy match picked", len(fz), "of", len(CBC), "CBC items:", fz)
    a = analyse(tidy, CBC, 20)
    print(a["segments"][["segment", "count"]].to_string(index=False))
    seg = dict(zip(a["distributors"].distributor, a["distributors"].segment))
    assert seg["Vardhman Surgicals"] == "Lost" and seg["Sanjeevani Distributors"] == "Untapped" \
        and seg["Apex Bio Traders"] == "New", seg
    assert "Litmus" in seg, "trailing space in sheet name should be stripped"

    brief = {"product": "Acculab CBC 360 Neo", "camp_type": "Primary (to distributors)", "duration": "3 months",
             "start_date": "2026-11-16", "stage": "Launch (plan)", "goal": "Grow CBC 360 Neo 20% in West",
             "idea": "Distributor league", "usp": "", "tasks": ["Calling to distributor - Daily"], "budget": ""}
    steps = []
    res = pipeline.run_all(ai, KB, brief, facts_for_ai(a), lambda s, msg: steps.append(s))
    assert res["first_review"]["score"] == 5 and res["review"]["score"] == 8
    assert "(reworked)" in res["plan"]["management_summary"][-1]
    print("pipeline steps:", steps, "| AI calls:", len(ai.calls), "| web used:", [w for _, w in ai.calls if w])

    os.makedirs(os.path.join(OUT, "out"), exist_ok=True)
    for name, data in (("plan.pdf", build_pdf(brief, a, res)), ("cockpit.pdf", build_pdf(brief, a, res, cockpit_only=True)),
                       ("plan.docx", build_docx(brief, a, res)), ("tracker.xlsx", build_tracker(brief, a, res))):
        open(os.path.join(OUT, "out", name), "wb").write(data)
        print(f"wrote {name} ({len(data) / 1024:.0f} KB)")

    # Two single-period files for different years must combine into LY + CY
    long = pd.read_excel(os.path.join(OUT, "2_single_long_sheet.xlsx"))
    res = {}
    for fy, name in (("FY 2025-26 (Apr-Oct)", "Sales Apr-Oct 2025.xlsx"), ("FY 2026-27 (Apr-Oct)", "Sales Apr-Oct 2026.xlsx")):
        p = os.path.join(OUT, name)
        long[long.FY == fy].drop(columns="FY").to_excel(p, index=False)
        res[name] = read_file(open(p, "rb").read(), name)
    t2, _, per = combine(res)
    ly, cy = t2[t2.period == "LY"].amount.sum(), t2[t2.period == "CY"].amount.sum()
    assert abs(ly - t_ly) < 1 and abs(cy - t_cy) < 1, (ly, cy, per)
    print(f"[2 files] separate year files -> LY {ly:,.0f} CY {cy:,.0f} OK")

    # The director's real files, if present
    real = os.environ.get("REAL_FILES_DIR")
    if real:
        files = {f: read_file(open(os.path.join(real, f), "rb").read(), f, ai=FakeAI()) for f in os.listdir(real)}
        for f, r in files.items():
            print(f"[real] {f}: {r['mapping'].notes} | checks: "
                  + ", ".join(f"{'OK' if c['ok'] else 'FAIL'} {c['read_total']:,.0f}/{c['file_total']:,.0f}" for c in r.get("checks", [])))
        tidy, contacts, periods = combine(files)
        inst = tidy[tidy.category == "instrument"]
        cons = tidy[tidy.category == "consumable"]
        print(f"[real] periods {periods} | instruments {inst.qty.sum():.0f} units Rs {inst.amount.sum():,.0f} | "
              f"reagents Rs {cons.amount.sum():,.2f} | contacts {len(contacts)}")
        assert inst.amount.sum() == 9285000 and inst.qty.sum() == 28
        assert abs(cons.amount.sum() - 1327748.1) < 1
        a = analyse(tidy, fuzzy_products(tidy, "Acculab 200"), 20, periods=periods, contacts=contacts)
        brief2 = {**brief, "product": "Acculab 200", "goal": "Grow Acculab 200 reagent pull-through"}
        res = pipeline.run_all(FakeAI(), KB, brief2, facts_for_ai(a))
        assert "drip" in res
        assert res["plan"]["campaign_name"] == "Precision Pact 200", res["plan"]["campaign_name"]
        claims = [u["claim"] for u in res["unverified"]]
        assert any("0.1 µL" in c for c in claims) and any("°C" in c for c in claims), claims
        assert "[⚠ unverified]" in res["plan"]["technical_usps"][1]["proof"]
        print("unverified claims flagged:", claims)
        mg = build_management(brief2, a, res)
        for name, data in (("real_management.pdf", mg), ("real_playbook.pdf", build_playbook(brief2, a, res)),
                           ("real_playbook.docx", build_docx(brief2, a, res)), ("real_tracker.xlsx", build_tracker(brief2, a, res))):
            open(os.path.join(OUT, "out", name), "wb").write(data)
            print(f"wrote {name} ({len(data) / 1024:.0f} KB)")
        pages = mg.count(b"/Type /Page") - mg.count(b"/Type /Pages")
        assert pages <= 2, f"management brief has {pages} pages"
        print("management brief pages:", pages)
    print("ALL OK")


if __name__ == "__main__":
    main()
