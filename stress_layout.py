"""Long, realistic AI text -> management brief must stay 2 pages with no overlaps."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import pipeline  # noqa: E402
from core.analytics import analyse, facts_for_ai  # noqa: E402
from core.data_reader import combine, fuzzy_products, read_file  # noqa: E402
from reports.pdf_report import build_management, build_playbook, page_count  # noqa: E402
from tests.test_end_to_end import KB, FakeAI  # noqa: E402

real = sys.argv[1]
files = {f: read_file(open(os.path.join(real, f), "rb").read(), f) for f in os.listdir(real)}
tidy, contacts, periods = combine(files)
a = analyse(tidy, fuzzy_products(tidy, "Acculab 200"), 20, periods=periods, contacts=contacts)
print("period label:", a["kpis"]["cy_label"])
brief = {"product": "Acculab 200", "camp_type": "Primary (to distributors)", "duration": "3 months", "start_date": "2026-11-16",
         "stage": "Launch (plan)", "goal": "Grow", "idea": "", "usp": "", "tasks": [], "budget": ""}
res = pipeline.run_all(FakeAI(), KB, brief, facts_for_ai(a))
long = ("Acculab 200 mix is **87.5% instruments** (₹92.85 L) vs **12.5% reagents** (₹13.28 L), risking margin unless "
        "reagent pull-through rises; focus on **reagent sales and high-activity distributor engagement** in every HQ.")
res["plan"]["management_summary"] = [long] * 5
res["analysis"]["distributor_actions"] = [{"distributor": "ODISHA SCIENTIFIC HOUSE", "segment": "Anchor",
    "action": "Push for ₹1.44 L more (targets: 1 instrument, max reagent bundling); include field demo with Application Specialist and weekly follow-up calls",
    "owner": "Regional / Area Sales Manager", "by_when": "Week 4"}] * 6
res["analysis"]["risks"] = ["Reagent pull-through remains weak (12.5% of value): risking failure to reach margin goals if instrument placements are not tied to reagent orders"] * 3
res["plan"]["kpis"] = [{"kpi": "Instruments placed (units)", "target": "≥31 units (target uplift)", "frequency": "Weekly"}] * 4
res["plan"]["phases"] = [{"phase": "Kick-off & Enablement", "weeks": "Week 1–2", "milestone": "100% distributor teams trained; demo units allotted; contenders confirmed and leads assigned"}] * 4
res["plan"]["decisions_needed"] = [{"decision": "Approve ₹3 L incentive pool for placement + reagent slabs", "why": "Without it the slab scheme cannot launch in Week 1 and distributors lose momentum", "cost": "₹3 L"}] * 3
res["naming"]["options"] = [{"name": n, "tagline": "Calibrating growth with every Acculab 200 run",
    "idea": "Integrates 'run' (lab workflow) and the model '200', emphasising reagent pull-through and repeat testing", "conflict_check": "No match"}
    for n in ("Reagent Run-200", "Precision 200 Run", "Acculab Control-200", "Calibrate 200", "QC Pact 200")]
res["naming"]["chosen"] = "Reagent Run-200"
mg = build_management(brief, a, res)
pb = build_playbook(brief, a, res)
out = os.path.join(ROOT, "tests", "samples", "out")
open(os.path.join(out, "stress_management.pdf"), "wb").write(mg)
open(os.path.join(out, "stress_playbook.pdf"), "wb").write(pb)
print("management pages:", page_count(mg), "| playbook pages:", page_count(pb))
assert page_count(mg) == 2
