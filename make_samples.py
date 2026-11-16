"""Builds the same sales data in four different layouts, to prove the reader handles any of them."""
import os
import random

import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "samples")
random.seed(7)

DISTS = ["Litmus ", "Medisure Diagnostics", "Shree Sai Enterprises", "Prime Lab Solutions", "Vardhman Surgicals",
         "Om Healthcare", "Nirmal Agencies", "Kalpataru Medical", "Sanjeevani Distributors", "Apex Bio Traders"]
HQ = {d: hq for d, hq in zip(DISTS, ["Mumbai", "Pune", "Nagpur", "Mumbai", "Ahmedabad", "Surat",
                                     "Pune", "Nashik", "Nagpur", "Ahmedabad"])}
CBC = ["Acculab CBC 360 Neo Analyser", "Diluent 20L for CBC 360 NEO (RFID)", "Lyse 500ml for CBC 360 NEO (RFID)",
       "Cleaner 100ml CBC 360 NEO", "3-Level Control for 360 NEO"]
OTHER = ["Accurex Glucose GOD-POD 500ml", "Accurex Creatinine 2x50ml", "CRP Latex Kit 100T"]
PRICE = {CBC[0]: 385000, CBC[1]: 6800, CBC[2]: 9200, CBC[3]: 2100, CBC[4]: 7400,
         OTHER[0]: 950, OTHER[1]: 1450, OTHER[2]: 2600}


def records():
    rows = []
    for i, d in enumerate(DISTS):
        trend = [1.45, 1.1, 0.7, 1.3, 0.0, 1.0, 0.85, 1.2, 0.0, 1.6][i]
        for p in CBC + OTHER:
            if i == 8 and p in CBC:   # Sanjeevani: never bought CBC -> Untapped
                continue
            base = random.randint(0, 2) if p == CBC[0] else random.randint(5, 60)
            if i == 9 and p in CBC:   # Apex: new this year
                ly_q, cy_q = 0, max(1, base)
            else:
                ly_q = base
                cy_q = round(base * (trend if p in CBC else 1.05))
            for per, q in (("LY", ly_q), ("CY", cy_q)):
                if q:
                    rows.append({"distributor": d, "hq": HQ[d], "product": p, "period": per, "qty": q,
                                 "amount": q * PRICE[p]})
    return pd.DataFrame(rows)


def write_all():
    os.makedirs(OUT, exist_ok=True)
    df = records()

    # 1. Tally style: one tab per distributor, title row with date ranges, two blocks, unlabelled product col
    with pd.ExcelWriter(os.path.join(OUT, "1_tab_per_distributor.xlsx")) as xw:
        for d, g in df.groupby("distributor", sort=False):
            ly, cy = g[g.period == "LY"], g[g.period == "CY"]
            n = max(len(ly), len(cy))
            sheet = [["01-Apr-2025 to 31-Oct-2025", None, None, None, "01-Apr-2026 to 31-Oct-2026", None, None],
                     [None, "QTY", "AMOUNT", None, None, "QTY", "AMOUNT"]]
            for k in range(n):
                a = ly.iloc[k] if k < len(ly) else None
                b = cy.iloc[k] if k < len(cy) else None
                sheet.append([a["product"] if a is not None else None, a["qty"] if a is not None else None,
                              a["amount"] if a is not None else None, None,
                              b["product"] if b is not None else None, b["qty"] if b is not None else None,
                              b["amount"] if b is not None else None])
            sheet.append(["Total", ly.qty.sum(), ly.amount.sum(), None, "Total", cy.qty.sum(), cy.amount.sum()])
            pd.DataFrame(sheet).to_excel(xw, sheet_name=d[:31], header=False, index=False)

    # 2. One long sheet with a Financial Year column
    long = df.assign(FY=df.period.map({"LY": "FY 2025-26 (Apr-Oct)", "CY": "FY 2026-27 (Apr-Oct)"}))
    long = long.rename(columns={"distributor": "Party Name", "hq": "Region", "product": "Item Description",
                                "qty": "Quantity", "amount": "Net Amount (Rs)"})
    long[["FY", "Region", "Party Name", "Item Description", "Quantity", "Net Amount (Rs)"]].to_excel(
        os.path.join(OUT, "2_single_long_sheet.xlsx"), index=False)

    # 3. Wide: one row per distributor x item, LY and CY columns
    wide = df.pivot_table(index=["distributor", "hq", "product"], columns="period", values=["qty", "amount"],
                          fill_value=0)
    wide.columns = [f"{p} {'Value' if m == 'amount' else 'Qty'}" for m, p in wide.columns]
    wide = wide.reset_index().rename(columns={"distributor": "Distributor", "hq": "HQ", "product": "Product"})
    # deliberately put This Year columns first: the reader must go by labels, not position
    wide = wide[["Distributor", "HQ", "Product", "CY Qty", "CY Value", "LY Qty", "LY Value"]]
    with pd.ExcelWriter(os.path.join(OUT, "3_wide_with_summary.xlsx")) as xw:
        pd.DataFrame({"Note": ["West zone sales summary", "Prepared by MIS"]}).to_excel(xw, sheet_name="Summary", index=False)
        wide.to_excel(xw, sheet_name="Data", index=False)

    # 4. Two tabs, one per year (CSV-like columns), no year column
    with pd.ExcelWriter(os.path.join(OUT, "4_tab_per_year.xlsx")) as xw:
        for per, name in (("LY", "Apr-Oct 2025"), ("CY", "Apr-Oct 2026")):
            g = df[df.period == per].rename(columns={"distributor": "Distributor", "hq": "HQ", "product": "Product",
                                                     "qty": "Qty", "amount": "Amount"})
            g[["Distributor", "HQ", "Product", "Qty", "Amount"]].to_excel(xw, sheet_name=name, index=False)
    return df


if __name__ == "__main__":
    d = write_all()
    print("rows", len(d), "LY", d[d.period == "LY"].amount.sum(), "CY", d[d.period == "CY"].amount.sum())
