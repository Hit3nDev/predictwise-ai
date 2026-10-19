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


# ---- sweet shop: customers and orders (for best/at-risk customers) ----------
def make_sweet_shop():
    rng = np.random.default_rng(23)
    first = ["Aarav","Priya","Rohit","Sneha","Vikram","Anjali","Karan","Neha","Suresh","Pooja","Amit","Kavita","Rahul","Meena","Deepak","Ritu","Manoj","Sunita","Arjun","Divya"]
    last = ["Sharma","Verma","Gupta","Singh","Yadav","Jain","Mehta","Kapoor","Malhotra","Bansal"]
    names = list(dict.fromkeys(f"{f} {l}" for f in first for l in last))[:140]
    items = {"Kaju Katli 500g": 620, "Gulab Jamun 1kg": 380, "Samosa (6)": 90, "Jalebi 500g": 160,
             "Gift Box": 950, "Rasgulla 1kg": 340, "Namkeen Mix 400g": 120}
    end = pd.Timestamp("2026-09-30")
    rows = []
    for n in names:
        kind = rng.choice(["loyal", "regular", "occasional", "lapsed", "new"], p=[.12, .28, .30, .18, .12])
        if kind == "loyal":   k, start, last_gap = int(rng.integers(30, 55)), 330, 0
        elif kind == "regular":  k, start, last_gap = int(rng.integers(12, 25)), 330, int(rng.integers(0, 20))
        elif kind == "occasional": k, start, last_gap = int(rng.integers(3, 8)), 330, int(rng.integers(10, 60))
        elif kind == "lapsed": k, start, last_gap = int(rng.integers(6, 20)), 330, int(rng.integers(100, 220))
        else:                 k, start, last_gap = int(rng.integers(1, 4)), 40, int(rng.integers(0, 10))
        span = max(start - last_gap, 1)
        days = sorted(rng.integers(last_gap, last_gap + span, k))
        for dd in days:
            it = rng.choice(list(items), p=[.2, .15, .25, .12, .08, .1, .1])
            qty = int(rng.integers(1, 3)) if items[it] < 500 else 1
            rows.append([n, (end - pd.Timedelta(days=int(dd))).strftime("%Y-%m-%d"), it, items[it] * qty])
    out = pd.DataFrame(rows, columns=["customer", "date", "item", "amount"]).sort_values("date")
    out.to_csv("samples/sweet_shop.csv", index=False)
    print(len(out), "orders,", out.customer.nunique(), "customers")


def make_provision_store():
    """A neighbourhood provision store: bills, regulars with phone numbers, udhaar, a Diwali rush."""
    rng = np.random.default_rng(31)
    items = {  # name: (selling price, cost price, weight)
        "Tea 250g": (120, 98, 9), "Sugar 1kg": (48, 42, 10), "Bread": (40, 34, 9), "Butter 100g": (58, 50, 6),
        "Maggi": (14, 11.5, 12), "Tomato Ketchup": (120, 95, 3), "Milk 1L": (66, 62, 14), "Biscuits": (10, 8, 12),
        "Atta 5kg": (245, 220, 6), "Rice 1kg": (85, 70, 6), "Cooking Oil 1L": (165, 150, 6), "Dal 1kg": (140, 118, 5),
        "Soap": (38, 30, 7), "Detergent 1kg": (120, 98, 4), "Cold Drink 2L": (95, 82, 5), "Chips": (20, 16, 9),
        "Diyas (6)": (60, 35, 1), "Dry Fruits 250g": (380, 300, 1), "Pickle Jar": (110, 88, 2), "Candles": (30, 22, 2),
    }
    names = list(items)
    pair = {"Tea 250g": "Sugar 1kg", "Bread": "Butter 100g", "Maggi": "Tomato Ketchup", "Biscuits": "Milk 1L",
            "Soap": "Detergent 1kg"}
    first = ["Ramesh","Sunita","Anil","Geeta","Mohan","Pushpa","Rakesh","Seema","Vijay","Kiran","Ashok","Lata","Naresh","Rekha","Sanjay","Usha","Dinesh","Madhu","Pawan","Asha"]
    last = ["Sharma","Gupta","Verma","Yadav","Singh","Saini","Tyagi","Chauhan"]
    custs = list(dict.fromkeys(f"{f} {l}" for f in first for l in last))[:70]
    phones = {c: (lambda n: f"+91 {n[:5]} {n[5:]}")(str(9800000000 + int(rng.integers(100000, 999999)))) for c in custs}
    # a few regulars stop coming; a few buy on credit
    gone = set(rng.choice(custs, 10, replace=False))
    gone_after = {c: pd.Timestamp("2026-10-10") - pd.Timedelta(days=int(rng.integers(60, 150))) for c in gone}
    udhaar = set(rng.choice(custs, 14, replace=False))
    start, end = pd.Timestamp("2025-07-01"), pd.Timestamp("2026-10-10")
    diwali = pd.Timestamp("2025-10-20")
    rows, bill = [], 1000
    for day in pd.date_range(start, end):
        wk = 1.35 if day.dayofweek >= 5 else 1.0
        rush = 1.7 if 0 <= (diwali - day).days <= 5 else 1.0
        n = int(rng.poisson(13 * wk * rush))
        for _ in range(n):
            c = str(rng.choice(custs))
            if c in gone_after and day > gone_after[c]:
                continue
            bill += 1
            k = int(rng.choice([1, 2, 3, 4, 5], p=[.2, .3, .25, .15, .1]))
            w = np.array([items[i][2] for i in names], float)
            for i, nm in enumerate(names):
                if nm in ("Diyas (6)", "Dry Fruits 250g") and rush > 1:
                    w[i] *= 9
                if nm in ("Pickle Jar", "Candles") and day > end - pd.Timedelta(days=30):
                    w[i] *= 0.05          # stopped selling
                if nm in ("Diyas (6)", "Dry Fruits 250g", "Candles") and rush == 1 and not (day.month in (10, 11) and day.year == 2025):
                    w[i] *= 0.2
            chosen = list(rng.choice(names, size=k, replace=False, p=w / w.sum()))
            for a, b in pair.items():
                if a in chosen and b not in chosen and rng.random() < 0.7:
                    chosen.append(b)
            pay = "Udhaar" if c in udhaar and rng.random() < 0.45 else str(rng.choice(["Cash", "UPI"], p=[.55, .45]))
            for nm in chosen:
                price, cost, _ = items[nm]
                q = int(rng.integers(1, 4)) if price < 100 else 1
                rows.append([f"B{bill}", day.strftime("%Y-%m-%d"), c, phones[c], nm, q, price, cost, price * q, pay])
    out = pd.DataFrame(rows, columns=["bill_no", "date", "customer", "phone", "item", "quantity", "selling_price", "cost_price", "amount", "payment"])
    out.to_csv("samples/provision_store.csv", index=False)
    print(len(out), "lines,", out.bill_no.nunique(), "bills")


if __name__ == "__main__":
    make_sweet_shop()
    make_provision_store()
