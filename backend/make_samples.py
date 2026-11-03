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


# ---- Sharma General Store: the demonstration file ---------------------------
# One file that every tool can read: bills with a time of day, a known customer with a phone
# and an area, the product with its category, quantity, selling and cost price, the amount and
# how it was paid. Sixteen months, so last year's Diwali is in the file and this year's is in
# the next fortnight. Patterns are planted on purpose so each screen has something to say.

FIRST = ["Ramesh", "Sunita", "Anil", "Geeta", "Mohan", "Pushpa", "Rakesh", "Seema", "Vijay", "Kiran", "Ashok", "Lata",
         "Naresh", "Rekha", "Sanjay", "Usha", "Dinesh", "Madhu", "Pawan", "Asha", "Suresh", "Kavita", "Rajesh", "Meena",
         "Deepak", "Nisha", "Manoj", "Savita", "Arjun", "Priya", "Gopal", "Sarla", "Harish", "Babita", "Mukesh", "Shobha",
         "Vinod", "Anita", "Prakash", "Hemlata"]
LAST = ["Sharma", "Gupta", "Verma", "Yadav", "Singh", "Saini", "Jain", "Agarwal", "Meena", "Chauhan", "Rathore", "Joshi"]
AREAS = ["Malviya Nagar", "Raja Park", "Jawahar Nagar", "Tilak Nagar", "Adarsh Nagar"]


def make_sharma_store():
    rng = np.random.default_rng(2026)
    items = {  # name: (category, selling price, cost price, base weight)
        "Atta 10kg": ("Staples", 420, 385, 7), "Basmati Rice 5kg": ("Staples", 520, 470, 4),
        "Toor Dal 1kg": ("Staples", 150, 132, 6), "Sugar 1kg": ("Staples", 46, 42, 9),
        "Cooking Oil 1L": ("Staples", 160, 146, 7), "Ghee 500ml": ("Staples", 320, 285, 3),
        "Milk 1L": ("Dairy", 66, 62, 18), "Butter 100g": ("Dairy", 58, 51, 5), "Bread": ("Bakery", 40, 34, 10),
        "Biscuits": ("Snacks", 20, 16, 12), "Maggi": ("Snacks", 14, 11.5, 11), "Chips": ("Snacks", 20, 16, 8),
        "Tea 500g": ("Beverages", 260, 225, 7), "Cold Drink 2L": ("Beverages", 95, 82, 5),
        "Instant Coffee 50g": ("Beverages", 180, 150, 1.2), "Soap (4 pack)": ("Household", 130, 108, 5),
        "Detergent 1kg": ("Household", 120, 100, 4), "Candles": ("Household", 30, 22, 2),
        "Dry Fruits 250g": ("Festival", 380, 310, 1.5), "Diyas (12 pack)": ("Festival", 80, 45, 0.0),
    }
    names = list(items)
    J = {n: i for i, n in enumerate(names)}
    base_w = np.array([items[n][3] for n in names], float)
    pairs = {"Tea 500g": ("Sugar 1kg", .6), "Bread": ("Butter 100g", .65), "Maggi": ("Chips", .45),
             "Atta 10kg": ("Ghee 500ml", .3), "Soap (4 pack)": ("Detergent 1kg", .5), "Dry Fruits 250g": ("Ghee 500ml", .4)}
    area_pref = {  # what each neighbourhood buys more of
        "Malviya Nagar": {"Dry Fruits 250g": 1.6, "Instant Coffee 50g": 1.8, "Butter 100g": 1.3, "Atta 10kg": 0.7},
        "Raja Park": {"Atta 10kg": 2.8, "Ghee 500ml": 1.4, "Toor Dal 1kg": 1.3},
        "Jawahar Nagar": {"Milk 1L": 1.2, "Maggi": 1.3, "Biscuits": 1.2},
        "Tilak Nagar": {"Tea 500g": 1.4, "Sugar 1kg": 1.3},
        "Adarsh Nagar": {"Basmati Rice 5kg": 1.5, "Cold Drink 2L": 1.2},
    }

    start, end = pd.Timestamp("2025-07-01"), pd.Timestamp("2026-11-03")
    diwali25, holi26, rakhi26, dussehra26, karva26 = (pd.Timestamp(x) for x in ("2025-10-20", "2026-03-04", "2026-08-28", "2026-10-20", "2026-10-29"))

    # customers: a type decides how often they come and how big the basket is
    pool = [f"{f} {l}" for f in FIRST for l in LAST]
    custs = [pool[i] for i in rng.choice(len(pool), 84, replace=False)]
    types = (["daily"] * 14 + ["regular"] * 40 + ["occasional"] * 18 + ["gone"] * 8 + ["new"] * 4)
    rng.shuffle(types)
    info = {}
    for c, kind in zip(custs, types):
        area = AREAS[int(rng.choice(5, p=[.27, .24, .19, .17, .13]))]
        weight = {"daily": 3.0, "regular": 1.2, "occasional": 0.4, "gone": 1.2, "new": 0.9}[kind] * float(rng.lognormal(0, 0.25))
        favs = list(rng.choice(names[:18], 3, replace=False))
        phone = f"+91 {int(rng.integers(70000, 99999))} {int(rng.integers(10000, 99999))}"
        first_day = start if kind != "new" else end - pd.Timedelta(days=int(rng.integers(6, 24)))
        last_day = end if kind != "gone" else end - pd.Timedelta(days=int(rng.integers(50, 160)))
        info[c] = dict(kind=kind, area=area, weight=weight, favs=favs, phone=phone, first=first_day, last=last_day, credit_from=None)
    # udhaar: a dozen households buy on credit; two of them have also stopped coming
    gone = [c for c in custs if info[c]["kind"] == "gone"]
    others = [c for c in custs if info[c]["kind"] in ("daily", "regular")]
    for c in list(rng.choice(gone, 2, replace=False)) + list(rng.choice(others, 10, replace=False)):
        info[c]["credit_from"] = end - pd.Timedelta(days=int(rng.integers(70, 230)))
    info[others[0]]["credit_from"] = end - pd.Timedelta(days=320)          # one old, chronic balance
    for c in rng.choice(others, 3, replace=False):
        info[c]["phone"] = None                                             # no number on file
    cust_names = np.array(custs)
    cust_w = np.array([info[c]["weight"] for c in custs])

    hour_w = {7: .5, 8: 1.3, 9: 1.9, 10: 1.1, 11: .8, 12: .6, 13: .4, 14: .3, 15: .4, 16: .6, 17: 1.0, 18: 1.3, 19: 1.8, 20: 1.2, 21: .6}
    # prices move a few times in sixteen months (MRP revisions); cost moves with them, except cooking oil
    days = pd.date_range(start, end)
    price_of = {}
    for nm, (_, price, cost, _) in items.items():
        p, c = np.full(len(days), float(price)), np.full(len(days), float(cost))
        for k in sorted(rng.choice(np.arange(40, len(days) - 20), int(rng.integers(1, 4)), replace=False)):
            f = 1 + float(rng.uniform(0.02, 0.06))
            p[k:], c[k:] = np.round(p[k:] * f), np.round(c[k:] * f, 1)
        if nm == "Cooking Oil 1L":
            k = int((pd.Timestamp("2026-09-10") - start).days)
            p[:], c[:] = 160.0, 146.0
            p[k:], c[k:] = 170.0, 160.0
        price_of[nm] = (p, c)
    hours = np.array(list(hour_w)); hp = np.array(list(hour_w.values())); hp = hp / hp.sum()
    basket_p = {"daily": [.45, .3, .15, .07, .03, 0], "regular": [.18, .27, .25, .16, .09, .05],
                "occasional": [.08, .2, .27, .22, .14, .09], "gone": [.18, .27, .25, .16, .09, .05], "new": [.2, .3, .25, .15, .07, .03]}

    def day_factor(day):
        f = [0.9, 0.78, 0.9, 0.95, 1.05, 1.22, 1.42][day.dayofweek]
        if day.day <= 5: f *= 1.2
        elif day.day >= 26: f *= 0.9
        gap = (diwali25 - day).days
        if 0 <= gap <= 7: f *= [1.9, 1.9, 1.6, 1.6, 1.6, 1.3, 1.3, 1.3][gap]
        elif -4 <= gap < 0: f *= 0.75
        if 0 <= (holi26 - day).days <= 3: f *= 1.25 if day != holi26 else 0.6
        if 0 <= (rakhi26 - day).days <= 2: f *= 1.15
        if 0 <= (dussehra26 - day).days <= 9: f *= 1.08
        if day == dussehra26: f *= 1.2
        if 0 <= (karva26 - day).days <= 1: f *= 1.15
        if day >= pd.Timestamp("2026-10-31"): f *= 1.15 + 0.05 * (day - pd.Timestamp("2026-10-31")).days
        return f * float(rng.lognormal(0, 0.08))

    def product_factor(day):
        w = base_w.copy()
        m, progress = day.month, (day - start).days / (end - start).days
        gap = (diwali25 - day).days
        if 0 <= gap <= 10:                                            # last Diwali
            w[J["Diyas (12 pack)"]] = 9.0; w[J["Dry Fruits 250g"]] *= 8; w[J["Ghee 500ml"]] *= 3.5
            w[J["Sugar 1kg"]] *= 1.8; w[J["Atta 10kg"]] *= 1.4; w[J["Basmati Rice 5kg"]] *= 1.3
        if day >= pd.Timestamp("2026-10-28"):                          # the run-up to this one
            k = (day - pd.Timestamp("2026-10-28")).days
            w[J["Diyas (12 pack)"]] = 1.5 + 1.0 * k; w[J["Dry Fruits 250g"]] *= 2 + 0.6 * k; w[J["Ghee 500ml"]] *= 1.5 + 0.2 * k
        if 0 <= (rakhi26 - day).days <= 2: w[J["Dry Fruits 250g"]] *= 2.5; w[J["Ghee 500ml"]] *= 1.6
        if m in (11, 12, 1, 2): w[J["Dry Fruits 250g"]] *= 1.5; w[J["Tea 500g"]] *= 1.25
        w[J["Cold Drink 2L"]] *= {4: 1.9, 5: 1.9, 6: 1.9, 7: 1.4, 8: 1.4, 9: 1.4, 10: 0.6, 3: 0.9}.get(m, 0.45)
        w[J["Instant Coffee 50g"]] *= 1 + 2.0 * progress
        if day >= pd.Timestamp("2026-10-15"): w[J["Instant Coffee 50g"]] *= 1.6
        if day >= pd.Timestamp("2026-10-20"): w[J["Tea 500g"]] *= 1.15
        if day >= pd.Timestamp("2026-09-01"): w[J["Candles"]] = 0.0            # stopped selling
        if day.dayofweek >= 5: w[J["Chips"]] *= 1.3; w[J["Cold Drink 2L"]] *= 1.3
        return w

    rows, bill = [], 10000
    for i, day in enumerate(pd.date_range(start, end)):
        growth = 1 + 0.012 * (i / 30.4)
        n_bills = int(rng.poisson(24 * growth * day_factor(day)))
        pw = product_factor(day)
        ok = np.array([info[c]["first"] <= day <= info[c]["last"] for c in custs])
        cw = cust_w * ok
        cw = cw / cw.sum()
        p_upi = 0.42 + 0.18 * (i / 490)
        for _ in range(n_bills):
            c = str(rng.choice(cust_names, p=cw))
            ci = info[c]
            bill += 1
            k = int(rng.choice(6, p=basket_p[ci["kind"]])) + 1
            w = pw.copy()
            for nm, mult in area_pref[ci["area"]].items():
                w[J[nm]] *= mult
            for nm in ci["favs"]:
                w[J[nm]] *= 3
            chosen = list(rng.choice(names, size=k, replace=False, p=w / w.sum()))
            if ci["kind"] == "daily" and "Milk 1L" not in chosen and rng.random() < 0.8:
                chosen[0] = "Milk 1L"
            for a, (b, p) in pairs.items():
                if a in chosen and b not in chosen and rng.random() < p:
                    chosen.append(b)
            if ci["credit_from"] is not None and day >= ci["credit_from"] and rng.random() < 0.45:
                pay = "Udhaar"
            else:
                pay = "UPI" if rng.random() < p_upi else "Cash"
            hr = int(rng.choice(hours, p=hp)) if ci["kind"] != "daily" or rng.random() < 0.4 else int(rng.choice([7, 8, 9, 18, 19]))
            stamp = f"{day:%Y-%m-%d} {hr:02d}:{int(rng.integers(0, 60)):02d}"
            for nm in dict.fromkeys(chosen):
                cat = items[nm][0]
                price, cost = float(price_of[nm][0][i]), float(price_of[nm][1][i])
                if price < 50: q = int(rng.integers(1, 5))
                elif price < 150: q = int(rng.integers(1, 3))
                else: q = 2 if rng.random() < 0.1 else 1
                if nm in ("Dry Fruits 250g", "Diyas (12 pack)") and (0 <= (diwali25 - day).days <= 10 or day >= pd.Timestamp("2026-10-28")):
                    q = int(rng.integers(1, 5))
                rows.append([f"B{bill}", stamp, c, ci["phone"], nm, cat, q, price, cost, round(price * q, 2), pay, ci["area"]])

    cols = ["bill_no", "date", "customer", "phone", "item", "category", "quantity", "selling_price", "cost_price", "amount", "payment", "area"]
    out = pd.DataFrame(rows, columns=cols)
    # realistic blemishes: a wedding order, one typo, a few blanks, a few repeated lines
    wedding = next(c for c in custs if info[c]["kind"] == "regular" and info[c]["phone"])
    k = int((pd.Timestamp("2026-10-24") - start).days)
    for nm, q in (("Dry Fruits 250g", 40), ("Ghee 500ml", 12), ("Basmati Rice 5kg", 10), ("Sugar 1kg", 15)):
        price, cost = float(price_of[nm][0][k]), float(price_of[nm][1][k])
        out.loc[len(out)] = [f"B{bill + 1}", "2026-10-24 11:20", wedding, info[wedding]["phone"], nm, items[nm][0], q, price, cost, price * q, "UPI", info[wedding]["area"]]
    typo = out[(out["item"] == "Maggi") & (out["date"] >= "2026-09-01")].index[5]
    out.loc[typo, ["quantity", "amount"]] = [100, 1400]
    out.loc[out.sample(30, random_state=3).index, "area"] = np.nan
    out = pd.concat([out, out.sample(8, random_state=4)], ignore_index=True)
    out = out.sort_values(["date", "bill_no"], kind="stable").reset_index(drop=True)
    out.to_csv("samples/sharma_store.csv", index=False)
    print(len(out), "lines,", out.bill_no.nunique(), "bills,", out.customer.nunique(), "customers,", f"{out.amount.sum():,.0f} rupees")


def make_udhaar_khata(n=600):
    """The credit ledger as a table a model can learn from: who repaid on time, and what was known about them."""
    rng = np.random.default_rng(77)
    area = rng.choice(AREAS, n, p=[.27, .24, .19, .17, .13])
    gender = rng.choice(["Female", "Male"], n, p=[.46, .54])
    age = rng.integers(21, 71, n)
    months = rng.integers(1, 61, n)
    visits = np.clip(rng.normal(8, 4, n), 1, 24).round(0)
    avg_bill = np.clip(rng.lognormal(np.log(320), 0.45, n), 60, 2500).round(0)
    udhaar = np.clip(rng.lognormal(np.log(1800), 0.6, n), 150, 15000).round(-1)
    previous = rng.poisson(months / 8, n)
    late = np.minimum(rng.poisson(0.6, n), previous)
    days_since = np.clip(rng.exponential(12, n), 0, 150).round(0)
    area_effect = pd.Series(area).map({"Malviya Nagar": 0.2, "Raja Park": 0.1, "Jawahar Nagar": 0.0, "Tilak Nagar": -0.6, "Adarsh Nagar": -0.1}).to_numpy()
    logit = (0.4 + 0.09 * visits + 0.025 * months - 0.00028 * udhaar + 0.0008 * avg_bill
             - 0.75 * late + 0.08 * previous - 0.02 * days_since + area_effect + rng.normal(0, 0.9, n))
    repaid = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    df = pd.DataFrame({
        "customer_id": np.arange(1, n + 1), "area": area, "gender": gender, "age": age,
        "months_as_customer": months, "visits_per_month": visits.astype(int), "avg_bill": avg_bill,
        "udhaar_amount": udhaar, "previous_udhaar": previous, "late_before": late,
        "days_since_last_visit": days_since.astype(int), "repaid_on_time": repaid,
    })
    df.loc[df.sample(18, random_state=1).index, "age"] = np.nan
    df.loc[df.sample(12, random_state=2).index, "avg_bill"] = np.nan
    df.loc[df.sample(2, random_state=5).index, "udhaar_amount"] = 90000
    df = pd.concat([df, df.sample(6, random_state=6)], ignore_index=True)
    df.to_csv("samples/udhaar_khata.csv", index=False)
    print(len(df), "customers in the khata,", f"{df.repaid_on_time.mean():.0%} repaid on time")


if __name__ == "__main__":
    make_sweet_shop()
    make_provision_store()
    make_sharma_store()
    make_udhaar_khata()
