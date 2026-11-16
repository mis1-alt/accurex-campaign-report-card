"""Accurex AI Marketing Manager - Streamlit app."""
import json
import os
from datetime import date

import pandas as pd
import streamlit as st

import pipeline
from ai import AI
from analytics import SEGMENTS, analyse, facts_for_ai, inr, kpi_tiles
from data_reader import (Mapping, ai_select_products, apply_mapping, combine, fuzzy_products, read_file,
                              total_checks)
from brand import BLUE, INK, LOGO, ORANGE, SEG_COLOURS, TONES
from charts import chart_data
from office_exports import build_docx, build_tracker
from pdf_report import build_management, build_playbook

HERE = os.path.dirname(os.path.abspath(__file__))
st.set_page_config(page_title="Accurex AI Marketing Manager", page_icon="📈", layout="wide")

st.markdown(f"""
<style>
html, body, [class*="css"] {{ font-family: 'Montserrat', Arial, sans-serif; color: {INK}; }}
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap');
.block-container {{ padding-top: 1.6rem; max-width: 1250px; }}
.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button {{
  background:{ORANGE}; color:#fff; border:0; border-radius:6px; font-weight:600; }}
.stButton>button:hover, .stDownloadButton>button:hover {{ background:#d9701a; color:#fff; }}
.kpi {{ background:#FDF1E6; border-top:3px solid {ORANGE}; padding:10px 12px; border-radius:4px; }}
.kpi .l {{ font-size:11px; color:#6B6B6B; font-weight:600; text-transform:uppercase; letter-spacing:.03em; }}
.kpi .v {{ font-size:22px; font-weight:700; }}
.step {{ display:inline-block; padding:4px 12px; margin-right:6px; border-radius:20px; font-size:13px;
         background:#F1EEEA; color:#6B6B6B; }}
.step.on {{ background:{ORANGE}; color:#fff; font-weight:600; }}
.step.done {{ background:#FDF1E6; color:{ORANGE}; }}
.motto {{ color:{ORANGE}; font-weight:700; font-size:18px; }}
</style>""", unsafe_allow_html=True)

ss = st.session_state
ss.setdefault("step", 1)


# ── Knowledge base ───────────────────────────────────────────────────────────
@st.cache_data
def load_kb():
    path = os.path.join(HERE, "knowledge", "company.json")
    if not os.path.exists(path):
        path = os.path.join(HERE, "company.json")          # flat layout
    with open(path, encoding="utf-8") as f:
        return json.load(f)


ss.setdefault("kb", load_kb())


def secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    if os.path.exists(LOGO):
        st.image(LOGO, width=170)
    st.caption("AI Marketing Manager")
    key = st.text_input("OpenAI API key", type="password",
                        help="Leave blank if OPENAI_API_KEY is set in Streamlit secrets.") or secret("OPENAI_API_KEY")
    model = st.selectbox("AI model", ["gpt-4.1", "gpt-5", "gpt-4o"], index=0,
                         help="gpt-4.1 is fast and supports web search. gpt-5 thinks deeper but is slower.")
    target_growth = st.slider("Target growth over last year (%)", 5, 100, 20, 5)
    st.divider()
    with st.expander("Company knowledge base"):
        st.caption("Goals, hierarchy, brand guide, products, competitors. The AI reads this on every run. "
                   "Edit here for this session; make it permanent in knowledge/company.json in the repo.")
        kb_txt = st.text_area("knowledge (JSON)", json.dumps(ss.kb, indent=2, ensure_ascii=False), height=300,
                              label_visibility="collapsed")
        if st.button("Apply knowledge changes"):
            try:
                ss.kb = json.loads(kb_txt)
                st.success("Applied for this session.")
            except json.JSONDecodeError as e:
                st.error(f"Not valid JSON: {e}")
        st.download_button("Download knowledge file", json.dumps(ss.kb, indent=2, ensure_ascii=False),
                           "company.json", "application/json")
    comp_file = st.file_uploader("Competitor sheet (optional)", type=["xlsx", "csv"],
                                 help="The sheet used for AI Verdict: competitor, product, price, features.")
    hq_file = st.file_uploader("Distributor → HQ mapping (optional)", type=["xlsx", "csv"],
                               help="Two columns: Distributor, HQ. Not needed if HQ is already in the sales file.")


def get_ai():
    if not key:
        return None
    return AI(key, model=model, log=lambda m: ss.setdefault("ai_log", []).append(m))


def read_table(f):
    return pd.read_csv(f) if f.name.lower().endswith(".csv") else pd.read_excel(f)


# ── Header and stepper ───────────────────────────────────────────────────────
st.markdown(f"<h2 style='margin-bottom:0'>AI Marketing Manager</h2>"
            f"<div style='color:#6B6B6B'>You give the brief and the sales file. The AI analyses, researches "
            f"competitors, builds the strategy and the creative brief, and reviews it like a director.</div>",
            unsafe_allow_html=True)
labels = ["1 Brief", "2 Sales data", "3 AI thinking", "4 Campaign plan"]
st.markdown("".join(f"<span class='step {'on' if i + 1 == ss.step else 'done' if i + 1 < ss.step else ''}'>{l}</span>"
                    for i, l in enumerate(labels)), unsafe_allow_html=True)
st.write("")

# ── Step 1: brief ────────────────────────────────────────────────────────────
if ss.step == 1:
    b = ss.get("brief", {})
    kb_products = [p["name"] for p in ss.kb.get("products", [])]
    with st.form("brief_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            product = st.text_input("Product (as in Tally)", b.get("product", kb_products[0] if kb_products else ""))
            camp_type = st.selectbox("Campaign type", ["Primary (to distributors)", "Secondary (to labs / customers)"],
                                     index=0 if "Primary" in b.get("camp_type", "Primary") else 1)
        with c2:
            duration = st.text_input("Duration", b.get("duration", "3 months"))
            start = st.date_input("Start date", b.get("start_date_obj", date.today()))
        with c3:
            stage = st.selectbox("Stage", ["Launch (plan)", "Mid-campaign review", "Close (results)"],
                                 index=["Launch (plan)", "Mid-campaign review", "Close (results)"].index(b.get("stage", "Launch (plan)")))
            budget = st.text_input("Budget (optional)", b.get("budget", ""), placeholder="e.g. ₹3 L for incentives + ₹50k creatives")
        goal = st.text_area("Campaign goal and expected output", b.get("goal", ""),
                            placeholder="e.g. Increase CBC 360 Neo reagent sales by 25% in West, add 5 new active distributors")
        idea = st.text_area("Rough idea (the AI will develop it)", b.get("idea", ""),
                            placeholder="e.g. Distributor contest with weekly scoreboard, demo camps in tier-2 cities")
        usp = st.text_input("Technical USP (optional, the AI will sharpen it)", b.get("usp", ""))
        aud_opts = ["Existing users of this product (installed base)", "Prospects (do not have it yet)",
                    "Mixed / not sure", "No contact list"]
        contact_audience = st.selectbox("If you upload a contact list: who is on it?", aud_opts,
                                        index=aud_opts.index(b.get("contact_audience", "Mixed / not sure")),
                                        help="Decides whether the drip campaign pushes reagent re-orders or new placements.")
        tasks = st.text_area("Tasks you want included, one per line: task - frequency",
                             b.get("tasks_txt", "Calling to distributor - Daily\nDistributor training / concall - Weekly\n"
                                                "Scoreboard sharing - Weekly\nCreatives on WhatsApp group - Daily"), height=110)
        if st.form_submit_button("Continue to sales data →"):
            if not product.strip() or not goal.strip():
                st.error("Product and campaign goal are required.")
            else:
                ss.brief = {"product": product.strip(), "camp_type": camp_type, "duration": duration,
                            "start_date": str(start), "start_date_obj": start, "stage": stage, "budget": budget,
                            "goal": goal, "idea": idea, "usp": usp, "tasks_txt": tasks,
                            "contact_audience": contact_audience,
                            "tasks": [t.strip() for t in tasks.splitlines() if t.strip()]}
                ss.step = 2
                st.rerun()

# ── Step 2: sales data ───────────────────────────────────────────────────────
elif ss.step == 2:
    st.markdown("Upload **all the reports** for this campaign at once: sales reports (last year and/or this year, "
                "any layout, one file or several) and **contact lists** for drip marketing (name + mobile). "
                "The AI works out what each file is.")
    ups = st.file_uploader("Reports", type=["xlsx", "xlsm", "xls", "csv"], accept_multiple_files=True)
    ss.setdefault("files", {})
    names = {u.name for u in ups or []}
    for f in list(ss.files):
        if f not in names:
            ss.files.pop(f)
            ss.pop("products_sel", None)
    for up in ups or []:
        if up.name not in ss.files:
            ai = get_ai()
            with st.spinner(f"Reading {up.name}..."):
                try:
                    ss.files[up.name] = read_file(up.getvalue(), up.name, ai=ai)
                    ss.pop("products_sel", None)
                except Exception as e:
                    st.error(f"Could not read {up.name}: {e}")

    if ss.files:
        tidy, contacts, periods = combine(ss.files)
        ss.tidy, ss.contacts, ss.periods = tidy, contacts, periods
        for fname, r in ss.files.items():
            with st.container(border=True):
                if r["kind"] == "contacts":
                    st.markdown(f"📇 **{fname}** · contact list · **{len(r['contacts'])} contacts**")
                    st.dataframe(r["contacts"].head(8), hide_index=True, use_container_width=True)
                    continue
                t = r["tidy"]
                st.markdown(f"📊 **{fname}** · sales report")
                st.caption(r["mapping"].notes)
                if t.empty:
                    st.error("No sales rows came out of this file. Correct the reading below.")
                else:
                    summ = (t.groupby(["source", "period"]).agg(rows=("amount", "size"), units=("qty", "sum"),
                                                               value=("amount", "sum")).reset_index())
                    summ["value"] = summ["value"].map(inr)
                    summ["period"] = summ["period"].map(lambda p: f"{p} · {periods.get(p, '')}")
                    summ.columns = ["Table", "Period", "Rows", "Units", "Value"]
                    st.dataframe(summ, hide_index=True, use_container_width=True)
                    for chk in r.get("checks", []):
                        if chk["ok"]:
                            st.markdown(f"✅ **{chk['table']}**: {inr(chk['read_total'])} matches the file's Total row")
                        else:
                            st.warning(f"⚠ **{chk['table']}**: read {inr(chk['read_total'])} but the file's Total row says "
                                       f"{inr(chk['file_total'])}. Correct the reading below before continuing.")
                with st.expander("Check or correct how this file was read"):
                    st.dataframe(t.head(40), use_container_width=True)
                    m_txt = st.text_area("Reading instructions (advanced)", json.dumps(r["mapping"].to_dict(), indent=2,
                                         default=str), height=220, key=f"map_{fname}")
                    if st.button("Re-read with these instructions", key=f"reread_{fname}"):
                        m = Mapping.from_dict(json.loads(m_txt))
                        ss.files[fname] = {**r, "mapping": m, "tidy": apply_mapping(r["sheets"], m),
                                           "checks": total_checks(r["sheets"], m)}
                        ss.pop("products_sel", None)
                        st.rerun()
        if periods.get("LY") is None and not tidy.empty:
            st.info("Only one period found. The plan will use this period's numbers; add last year's report "
                    "to get growth and last-year comparisons.")

        if tidy.empty:
            st.warning("Add at least one sales report to build the campaign.")
            if st.button("← Back"):
                ss.step = 1
                st.rerun()
        else:
            all_items = (tidy.groupby("product").amount.sum().sort_values(ascending=False).index.tolist())
            if "products_sel" not in ss:
                ai = get_ai()
                kbp = pipeline.find_product(ss.kb, ss.brief["product"]) or {}
                sel, why = [], ""
                if ai:
                    with st.spinner("AI is picking the line items that belong to this product..."):
                        try:
                            sel, why = ai_select_products(ai, tidy, ss.brief["product"], kbp.get("brief", ""))
                        except Exception as e:
                            why = f"AI selection failed ({e}); used name matching."
                if not sel:
                    sel = fuzzy_products(tidy, ss.brief["product"])
                ss.products_sel, ss.products_why = sel, why
            st.markdown(f"#### Line items counted for **{ss.brief['product']}**")
            if ss.get("products_why"):
                st.caption(ss.products_why)
            chosen = st.multiselect("Add or remove items", all_items, default=ss.products_sel)
            c1, c2 = st.columns([1, 5])
            if c1.button("← Back"):
                ss.step = 1
                st.rerun()
            if c2.button("Analyse and build the campaign →", disabled=not chosen):
                hq_map = {}
                if hq_file:
                    h = read_table(hq_file)
                    cols = {c.lower().strip(): c for c in h.columns}
                    dcol = next((cols[c] for c in cols if "distributor" in c or "party" in c), h.columns[0])
                    hcol = next((cols[c] for c in cols if c in ("hq", "region", "zone") or "hq" in c), h.columns[1])
                    hq_map = dict(zip(h[dcol].astype(str), h[hcol].astype(str)))
                ss.products_sel = chosen
                try:
                    ss.analysis_data = analyse(tidy, chosen, target_growth, hq_map, periods=periods, contacts=contacts)
                except ValueError as e:
                    st.error(str(e))
                    st.stop()
                if comp_file:
                    ss.brief["competitor_sheet"] = read_table(comp_file).head(40).to_csv(index=False)
                ss.step = 3
                st.rerun()
    else:
        if st.button("← Back"):
            ss.step = 1
            st.rerun()

# ── Step 3: AI thinking ──────────────────────────────────────────────────────
elif ss.step == 3:
    ai = get_ai()
    if not ai:
        st.error("Add the OpenAI API key in the sidebar (or as the OPENAI_API_KEY secret) to run the AI.")
        if st.button("← Back"):
            ss.step = 2
            st.rerun()
    else:
        a = ss.analysis_data
        names = {1: "Analyst", 2: "Market researcher", 3: "Strategist", 4: "Creative director", 5: "Reviewer", 6: "Done"}
        with st.status("The AI team is working on your campaign...", expanded=True) as status:
            def progress(step, msg):
                status.write(f"**{names[step]}:** {msg}")
            try:
                ss.result = pipeline.run_all(ai, ss.kb, ss.brief, facts_for_ai(a), progress)
                status.update(label="Campaign plan ready", state="complete")
                ss.step = 4
            except Exception as e:
                status.update(label="The AI run stopped", state="error")
                st.error(f"{type(e).__name__}: {e}")
                if st.button("Try again"):
                    st.rerun()
        if ss.step == 4:
            st.rerun()

# ── Step 4: results ──────────────────────────────────────────────────────────
elif ss.step == 4:
    a, r, b = ss.analysis_data, ss.result, ss.brief
    k, plan, rv = a["kpis"], r.get("plan", {}), r.get("review", {})
    st.markdown(f"## {plan.get('campaign_name', b['product'])}")
    st.markdown(f"<div class='motto'>{plan.get('motto', '')}</div>", unsafe_allow_html=True)
    st.caption(f"{b['product']} · {b['camp_type']} · {b['duration']} · {b['stage']}")

    tiles = kpi_tiles(k)[:5] + [("AI review", f"{rv.get('score', '–')}/10", "good")]
    for col, (l, v, tone) in zip(st.columns(len(tiles)), tiles):
        col.markdown(f"<div class='kpi'><div class='l'>{l}</div><div class='v' style='color:{TONES[tone]}'>{v}</div></div>",
                     unsafe_allow_html=True)
    st.write("")

    d1, d2, d3, d4 = st.columns(4)
    fname = f"{b['product'].replace(' ', '_')}_Campaign_{date.today():%d%b%Y}"
    d1.download_button("⬇ Management brief (PDF, 2 pages)", build_management(b, a, r), f"{fname}_Management_Brief.pdf",
                       "application/pdf", help="Bird's-eye view for directors")
    d2.download_button("⬇ Team playbook (PDF)", build_playbook(b, a, r), f"{fname}_Team_Playbook.pdf", "application/pdf",
                       help="Full working detail for the marketing team")
    d3.download_button("⬇ Team playbook (Word)", build_docx(b, a, r), f"{fname}_Team_Playbook.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    if r.get("unverified"):
        st.error(f"⚠ {len(r['unverified'])} technical claims in the AI text are not in the knowledge base and are marked "
                 f"[⚠ unverified]. PMT must confirm them before any creative or message goes out (see Director review tab).")
    d4.download_button("⬇ Action tracker (Excel)", build_tracker(b, a, r), f"{fname}_Tracker.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    tabs = st.tabs(["Cockpit", "Strategy", "Distributors & items", "Execution", "Competitors", "Creative brief",
                    "Drip campaign", "Director review"])

    def seg_style(df, col="Segment"):
        return df.style.apply(lambda s: [f"background-color:{SEG_COLOURS.get(v, ('', '#fff'))[1]};"
                                         f"color:{SEG_COLOURS.get(v, ('#000', ''))[0]};font-weight:600"
                                         if s.name == col else "" for v in s], axis=0)

    with tabs[0]:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("#### Management summary")
            for x in plan.get("management_summary", []):
                st.markdown(f"- {x}")
            ctitle, labels, ly, cy, has_ly = chart_data(a)
            st.markdown(f"#### {ctitle}")
            cdf = pd.DataFrame({"Last year": [v / 1e5 for v in ly], "This year": [v / 1e5 for v in cy]},
                               index=[s[:30] for s in labels])
            if has_ly:
                st.bar_chart(cdf, horizontal=True, color=["#C9C5C0", ORANGE], y_label="₹ lakh", stack=False)
            else:
                st.bar_chart(cdf[["This year"]], horizontal=True, color=[ORANGE], y_label="₹ lakh")
        with c2:
            if not a["segments"].empty:
                st.markdown("#### Segments")
                seg = a["segments"].rename(columns={"segment": "Segment", "count": "Distributors", "cy_amt": "Value"})
                seg["Value"] = seg["Value"].map(inr)
                st.dataframe(seg_style(seg[["Segment", "Distributors", "Value"]]), hide_index=True, use_container_width=True)
                for s in seg["Segment"]:
                    st.caption(f"**{s}**: {SEGMENTS.get(s, '')}")
            if k["pull_through_per_unit"]:
                st.markdown("#### Instrument vs reagent")
                st.markdown(f"**{k['instrument_units']:,.0f}** instruments · **{inr(k['consumable_amt'])}** reagents "
                            f"({k['consumable_share_pct']}% of value) · **{inr(k['pull_through_per_unit'])}** reagent per instrument")
        st.markdown("#### Priority actions")
        acts = pd.DataFrame(r.get("analysis", {}).get("distributor_actions", []))
        if not acts.empty:
            acts.columns = [c.replace("_", " ").title() for c in acts.columns]
            st.dataframe(seg_style(acts), hide_index=True, use_container_width=True)

    with tabs[1]:
        obj = plan.get("objective", {})
        st.info(f"**Objective:** {obj.get('statement', '')}  \n**Target:** {obj.get('target_value', '')} · "
                f"**Measured by:** {obj.get('measure', '')}")
        nm = r.get("naming", {})
        if nm.get("options"):
            st.markdown("#### Campaign name options")
            st.caption(f"Chosen: **{nm.get('chosen')}**. {nm.get('why_chosen', '')}")
            st.dataframe(pd.DataFrame(nm["options"]).rename(columns={"name": "Name", "tagline": "Tagline", "idea": "Why it fits",
                                                                     "conflict_check": "Name check"}),
                         hide_index=True, use_container_width=True)
        if plan.get("decisions_needed"):
            st.markdown("#### Decisions needed from management")
            st.dataframe(pd.DataFrame(plan["decisions_needed"]), hide_index=True, use_container_width=True)
        an = r.get("analysis", {})
        if an.get("headline"):
            st.markdown(f"**What the data says:** {an['headline']}")
            st.dataframe(pd.DataFrame(an.get("insights", [])), hide_index=True, use_container_width=True)
        st.markdown("#### Technical USPs")
        st.dataframe(pd.DataFrame(plan.get("technical_usps", [])), hide_index=True, use_container_width=True)
        st.markdown("#### Campaign mechanics")
        st.dataframe(pd.DataFrame(plan.get("mechanics", [])), hide_index=True, use_container_width=True)
        inc = plan.get("incentive_scheme", {})
        if inc:
            st.markdown(f"#### Incentive scheme: {inc.get('type', '')}")
            st.dataframe(pd.DataFrame(inc.get("slabs", [])), hide_index=True, use_container_width=True)
            st.caption(inc.get("budget_note", ""))
        st.markdown("#### Phases")
        st.dataframe(pd.DataFrame(plan.get("phases", [])), hide_index=True, use_container_width=True)
        fc = plan.get("forecast", {})
        if fc:
            st.markdown("#### Expected outcome")
            f1, f2, f3 = st.columns(3)
            f1.metric("Conservative", fc.get("conservative", ""))
            f2.metric("Target", fc.get("target", ""))
            f3.metric("Stretch", fc.get("stretch", ""))
            for x in fc.get("assumptions", []):
                st.caption(f"• {x}")
        if plan.get("competitor_response"):
            st.markdown(f"**Answer to the strongest competitor:** {plan['competitor_response']}")

    with tabs[2]:
        d = a["distributors"].copy()
        if not d.empty:
            if k["has_ly"]:
                show = pd.DataFrame({"Distributor": d.distributor, "HQ": d.hq, "Segment": d.segment,
                                     "LY value": d.ly_amt.map(inr), "CY value": d.cy_amt.map(inr),
                                     "Growth %": d.growth_pct, "Target": d.target_amt.map(inr), "Gap": d.gap_amt.map(inr),
                                     "Other Accurex products": d.other_products_amt.map(inr)})
            else:
                st.caption("No last-year data uploaded: distributors are grouped by share of value.")
                show = pd.DataFrame({"Distributor": d.distributor, "HQ": d.hq, "Segment": d.segment,
                                     "Units": d.cy_qty, "Value": d.cy_amt.map(inr), "Share %": d.share_pct,
                                     f"Target +{k['target_growth_pct']:.0f}%": d.target_amt.map(inr)})
            st.dataframe(seg_style(show), hide_index=True, use_container_width=True, height=420)
        else:
            st.info("The uploaded reports have no distributor-wise numbers.")
        if not a["hq"].empty:
            st.markdown("#### By HQ")
            st.dataframe(a["hq"], hide_index=True, use_container_width=True)
        st.markdown("#### Play per segment")
        st.dataframe(pd.DataFrame(plan.get("target_segments", [])), hide_index=True, use_container_width=True)
        st.markdown("#### Items counted")
        p = a["products"].copy()
        cols = {"product": "Item", "category": "Type", "qty_CY": "Units", "amount_CY": "Value", "share_pct": "Share %"}
        if k["has_ly"]:
            cols.update({"amount_LY": "LY value", "growth_pct": "Growth %"})
        p = p[list(cols)].rename(columns=cols)
        st.dataframe(p, hide_index=True, use_container_width=True)

    with tabs[3]:
        st.dataframe(pd.DataFrame(plan.get("checklist", [])), hide_index=True, use_container_width=True, height=460)
        st.markdown("#### KPIs")
        st.dataframe(pd.DataFrame(plan.get("kpis", [])), hide_index=True, use_container_width=True)

    with tabs[4]:
        rs = r.get("research", {})
        if rs.get("market_notes"):
            st.caption(rs["market_notes"])
        st.markdown("#### Competitor products")
        st.dataframe(pd.DataFrame(rs.get("competitors", [])), hide_index=True, use_container_width=True)
        st.markdown("#### How competitors run campaigns")
        st.dataframe(pd.DataFrame(rs.get("industry_playbook", [])), hide_index=True, use_container_width=True)
        st.markdown("#### What we are missing")
        st.dataframe(pd.DataFrame(rs.get("gaps", [])), hide_index=True, use_container_width=True)

    with tabs[5]:
        cr = r.get("creative", {})
        st.markdown(f"### {cr.get('big_idea', '')}")
        st.markdown(f"**Key message:** {cr.get('key_message', '')}  \n**Tone:** {cr.get('tone', '')}")
        st.markdown(f"<span style='display:inline-block;width:14px;height:14px;background:{ORANGE}'></span> Accurex Orange #F28421 (primary) &nbsp; "
                    f"<span style='display:inline-block;width:14px;height:14px;background:{BLUE}'></span> Clinical Blue #0376BD (max 15%) &nbsp; "
                    f"<span style='display:inline-block;width:14px;height:14px;background:{INK}'></span> Ink #231F20 · Montserrat",
                    unsafe_allow_html=True)
        for v in cr.get("verticals", []):
            st.markdown(f"#### {v.get('vertical', '')}")
            st.caption(f"Audience: {v.get('audience', '')} · Angle: {v.get('message_angle', '')}")
            st.dataframe(pd.DataFrame(v.get("assets", [])), hide_index=True, use_container_width=True)
        if cr.get("content_calendar"):
            st.markdown("#### Content calendar")
            st.dataframe(pd.DataFrame(cr["content_calendar"]), hide_index=True, use_container_width=True)
        cd = cr.get("cockpit_design", {})
        if cd.get("zones"):
            st.markdown(f"#### Cockpit design (updated {cd.get('update_frequency', '')}, owner {cd.get('owner', '')})")
            st.dataframe(pd.DataFrame(cd["zones"]), hide_index=True, use_container_width=True)
        c1, c2 = st.columns(2)
        c1.markdown("**Do**\n" + "\n".join(f"- {x}" for x in cr.get("dos", [])))
        c2.markdown("**Don't**\n" + "\n".join(f"- {x}" for x in cr.get("donts", [])))

    with tabs[6]:
        dr, c = r.get("drip"), a.get("contacts")
        if not c:
            st.info("Upload a contact list (name + mobile) in step 2 to get a drip campaign plan.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Contacts uploaded", c["total"])
            m2.metric("Reachable", c["reachable"])
            m3.metric("Invalid numbers", len(c["invalid"]))
            m4.metric("Repeated numbers", len(c["duplicates"]))
            st.caption("Reachable by type: " + " · ".join(f"{t} {n}" for t, n in c["by_type"].items()))
            if dr:
                st.markdown(dr.get("audience_summary", ""))
                st.markdown("#### Segments")
                st.dataframe(pd.DataFrame(dr.get("segments", [])), hide_index=True, use_container_width=True)
                st.markdown("#### Message sequence")
                for s in dr.get("sequence", []):
                    with st.container(border=True):
                        st.markdown(f"**Touch {s.get('touch')} · {s.get('day')} · {s.get('channel')}** — {s.get('objective', '')}")
                        st.markdown(f"> {s.get('message', '')}")
                        st.caption(f"Media: {s.get('media', '')} · CTA: {s.get('cta', '')} · Owner: {s.get('owner', '')}")
                if dr.get("follow_up_rules"):
                    st.markdown("#### When a lab replies")
                    for x in dr["follow_up_rules"]:
                        st.markdown(f"- {x}")
                c1, c2 = st.columns(2)
                c1.markdown("**Compliance**\n" + "\n".join(f"- {x}" for x in dr.get("compliance", [])))
                c2.markdown("**Fix the list before sending**\n" + "\n".join(f"- {x}" for x in dr.get("list_hygiene", [])))
            with st.expander("Contact list with checks"):
                st.dataframe(c["table"], hide_index=True, use_container_width=True)

    with tabs[7]:
        st.markdown(f"### {rv.get('score', '–')}/10 · {rv.get('verdict', '')}")
        if r.get("unverified"):
            st.markdown("#### ⚠ Unverified technical claims (PMT to confirm)")
            st.dataframe(pd.DataFrame(r["unverified"]), hide_index=True, use_container_width=True)
        if r.get("first_review"):
            st.caption(f"The first draft scored {r['first_review'].get('score')}/10 and was reworked automatically.")
        for x in rv.get("strengths", []):
            st.markdown(f"✅ {x}")
        st.dataframe(pd.DataFrame(rv.get("issues", [])), hide_index=True, use_container_width=True)
        st.markdown("**Questions management will ask**")
        for x in rv.get("director_questions", []):
            st.markdown(f"- {x}")

    st.divider()
    c1, c2, c3 = st.columns([1, 1, 4])
    if c1.button("Edit brief"):
        ss.step = 1
        st.rerun()
    if c2.button("Re-run AI"):
        ss.step = 3
        st.rerun()
    if c3.button("New campaign"):
        for kk in ("brief", "tidy", "files", "contacts", "periods", "products_sel", "analysis_data", "result"):
            ss.pop(kk, None)
        ss.step = 1
        st.rerun()
