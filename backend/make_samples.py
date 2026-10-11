"""Regenerates samples/kirana_sales.csv (deterministic). Run: python make_samples.py"""
import numpy as np, pandas as pd

rng = np.random.default_rng(11)
products = {
    "Basmati Rice 5kg": ("Staples", 520), "Atta 10kg": ("Staples", 410), "Toor Dal 1kg": ("Staples", 165),
    "Sunflower Oil 1L": ("Staples", 145), "Tea 500g": ("Beverages", 260), "Cold Drink 2L": ("Beverages", 95),
    "Biscuits Family Pack": ("Snacks", 60), "Namkeen 400g": ("Snacks", 110), "Soap (4 pack)": ("Household", 130),
    "Detergent 2kg": ("Household", 230), "Milk 1L": ("Dairy", 68), "Paneer 200g": ("Dairy", 90),
}
weights = dict(zip(products, [5, 8, 6, 7, 6, 8, 12, 7, 6, 4, 18, 5]))
areas = ["Sector 12", "Sector 15", "Old Market", "Colony Road"]
pays = ["UPI", "Cash", "Card"]
rows = []
days = pd.date_range("2025-10-01", "2026-09-30")
for i, d in enumerate(days):
    growth = 1 + 0.0012 * i
    weekend = 1.35 if d.weekday() >= 5 else 1.0
    festive = 1.8 if pd.Timestamp("2025-10-17") <= d <= pd.Timestamp("2025-10-23") else 1.0
    for p, (cat, price) in products.items():
        lam = weights[p] * 0.5 * growth * weekend * festive
        q = int(rng.poisson(lam))
        if q == 0:
            continue
        up = round(price * (1 + rng.normal(0, 0.015)), 0)
        rows.append([d.strftime("%Y-%m-%d"), p, cat, q, up, round(q * up, 0),
                     rng.choice(pays, p=[.55, .3, .15]), rng.choice(areas, p=[.35, .25, .25, .15])])
df = pd.DataFrame(rows, columns=["date", "product", "category", "quantity", "unit_price", "sales", "payment_mode", "area"])
# a few realistic blemishes
df.loc[df.sample(25, random_state=1).index, "payment_mode"] = np.nan
bulk = df.sample(3, random_state=5).index
df.loc[bulk, "quantity"] = df.loc[bulk, "quantity"] * 12
df.loc[bulk, "sales"] = df.loc[bulk, "quantity"] * df.loc[bulk, "unit_price"]
df.to_csv("samples/kirana_sales.csv", index=False)
print(len(df), "rows")
