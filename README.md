# Accurex AI Marketing Manager

Marketing executives give a short brief and upload the sales dump. The app then runs a
five-step AI team and produces a complete, branded campaign plan:

| Step | AI role | Output |
|---|---|---|
| 1 | **Analyst** | What the numbers say, per-distributor actions with owner and week |
| 2 | **Market researcher** (live web search) | Competitor products, prices, specs; how other IVD companies run campaigns; what Accurex is missing |
| 3 | **Strategist** | Campaign name, motto, objective, technical USPs vs named competitors, mechanics, incentive slabs, phases, checklist (one doer + frequency per task), KPIs, forecast |
| 4 | **Creative director** | Brief per vertical and channel: exact sizes, brand hex colours, headline and copy, visual direction, CTA, frequency, content calendar, and the cockpit design |
| 5 | **Reviewer** | Scores the plan out of 10 as a director would. Below 7, the strategist reworks it automatically |

All arithmetic (last year vs this year, growth, targets, gaps, segments) is done by Python,
never by the AI, so the numbers are always exact.

## Outputs
- **Management Brief PDF (2 pages)** for directors. Page 1 is the cockpit: campaign name and motto, KPIs, summary, AI review score, chart and segments. Page 2 covers the decisions management must take, the expected outcome and budget, the plan on a page, the top 5 actions, KPIs to watch, risks, and the campaign name options.
- **Team Playbook PDF and Word** for the marketing team: strategy, name options, distributor plan and item mix, checklist (one doer and a frequency per task), competitors, creative brief, drip campaign, and the director review.
- **Excel action tracker**: distributor targets with weekly columns, actions, checklist, KPIs, creatives, drip contacts and messages.

## Campaign name
A dedicated AI step proposes 5 names drawn from the language of the lab (QC, calibration,
precision, assay, run and so on), checks them on the web against existing Indian IVD campaign
and product names, and picks one. All 5 options are shown so the team can choose differently.

## Unverified technical claims
Any technical spec in the AI's text (µL, °C, tests/hour, cuvettes and so on) that is not in
`knowledge/company.json` is marked **[⚠ unverified]** and listed for PMT to confirm. Add real
specs to the product's `brief` in the knowledge file and they stop being flagged.

## Sales file: any layout
The AI looks at the workbook and works out its structure. Supported layouts:
- One tab per distributor with Last Year and This Year blocks side by side (Tally style, unlabelled product column, date-range title row)
- One long sheet with a Year / FY / Period column
- One sheet with separate LY and CY columns (column order does not matter)
- One tab per year
- Extra summary or notes tabs are skipped automatically

You can check and correct the reading before going ahead. Without an API key, a rule-based
reader handles all of the layouts above.

The AI then picks which line items belong to the campaign product, including its reagents and
consumables (Tally names rarely repeat the brand). You can add or remove items.

**Distributor segments:** Star (+15% or more), Growing, Declining, Lost (bought last year, nothing this year),
New, and Untapped (buys other Accurex products but never this one, which makes it a cross-sell target).

## Company knowledge
`knowledge/company.json` holds the company goals, hierarchy (used as task owners), Accurex Brand
Guide v1.1 (Orange #F28421, Clinical Blue #0376BD used sparingly, Ink #231F20, Montserrat, voice
rules), creative size specs, verticals, product briefs, and the competitor list. The AI reads it
on every run. **Fill in the TODO lines** (revenue goal, product specs) for sharper output.
You can also edit it for one session from the app sidebar, and upload the AI Verdict competitor sheet there.

## Deploy (replacing the current campaign app)
1. In the GitHub repo `mis1-alt/accurex-campaign-report-card`, delete the old `app.py`.
2. **Add file → Upload files**: drag in everything from this folder (`app.py`, `requirements.txt`,
   `README.md`, and the folders `core`, `reports`, `knowledge`, `assets`, `.streamlit`, `tests`). Commit.
3. Streamlit Cloud redeploys automatically. In **Manage app → Settings → Secrets** keep:
   ```
   OPENAI_API_KEY = "sk-..."
   ```
4. In **Settings**, set the Python version to 3.12 if the build fails on 3.14.

`packages.txt` is no longer needed: fonts come bundled with matplotlib. For real Montserrat in
the PDFs, add `Montserrat-Regular.ttf` and `Montserrat-Bold.ttf` to `assets/fonts/`.

## Models
Default is `gpt-4.1` (fast, supports web search). `gpt-5` reasons more deeply but is slower. A full run makes
about 7–9 AI calls and takes 1–3 minutes.

## Tests (offline, no API key needed)
```
python tests/test_end_to_end.py   # 4 file layouts, analytics, 5-step pipeline with a fake AI, all exports
python tests/test_app_ui.py       # drives the Streamlit screens headlessly
```
