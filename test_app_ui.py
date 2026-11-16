"""Headless UI test: drives the Streamlit app through the brief form and renders the results screen.
Run from the repo root:  python tests/test_app_ui.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

from core import pipeline  # noqa: E402
from core.analytics import analyse, facts_for_ai  # noqa: E402
from core.data_reader import read_sales  # noqa: E402
from tests.make_samples import CBC, OUT, write_all  # noqa: E402
from tests.test_end_to_end import KB, FakeAI  # noqa: E402

APP = os.path.join(ROOT, "app.py")

# Step 1 -> 2
at = AppTest.from_file(APP, default_timeout=60).run()
assert not at.exception, at.exception
at.text_area[0].input("Grow CBC 360 Neo value 20% in West")
at.button[0].click().run()   # form submit
assert not at.exception, at.exception
assert at.session_state["step"] == 2, at.session_state["step"]
print("step 1 -> 2 OK; brief:", at.session_state["brief"]["product"])

# Step 4 rendering with real analysis + fake AI result
write_all()
tidy, _, _ = read_sales(open(os.path.join(OUT, "1_tab_per_distributor.xlsx"), "rb").read(), "1.xlsx")
a = analyse(tidy, CBC, 20)
brief = at.session_state["brief"]
res = pipeline.run_all(FakeAI(), KB, brief, facts_for_ai(a))
at.session_state["analysis_data"] = a
at.session_state["result"] = res
at.session_state["step"] = 4
at.run()
assert not at.exception, at.exception
print("results screen OK: tabs =", len(at.tabs), "| dataframes =", len(at.dataframe),
      "| headings:", [m.value for m in at.markdown if m.value.startswith("## ")][:1])

# Edit brief returns to step 1 with values kept
[b for b in at.button if b.label == "Edit brief"][0].click().run()
assert at.session_state["step"] == 1 and not at.exception
print("Edit brief -> step 1 OK, goal kept:", at.text_area[0].value[:30])
print("UI OK")
