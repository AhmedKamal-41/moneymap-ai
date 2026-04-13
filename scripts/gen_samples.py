"""
Generate realistic sample CSVs for MoneyMap AI.
Run from the project root: python scripts/gen_samples.py
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

rng = random.Random(2024)


def R(lo, hi):
    return round(rng.uniform(lo, hi), 2)


def clamp_day(y, m, d):
    """Return date(y,m,d) clamping d to a valid day for that month."""
    import calendar
    max_day = calendar.monthrange(y, m)[1]
    return date(y, m, min(d, max_day))


# ─────────────────────────────────────────────────────────────────────────────
# PERSONAL CSV  (~500 rows)
# ─────────────────────────────────────────────────────────────────────────────
personal = []   # (date, category, amount, description)

GROCERY_STORES = [
    "Trader Joe's", "Whole Foods Market", "Kroger", "Safeway",
    "Aldi", "Wegmans", "Publix", "Stop & Shop",
]
COFFEE_PLACES = [
    "Starbucks", "Dunkin", "Local Brew Coffee", "Blue Bottle Coffee",
    "Peets Coffee", "Caribou Coffee", "Tim Hortons",
]
RESTAURANTS = [
    "Chipotle Mexican Grill", "Pizza Hut Delivery", "DoorDash - Thai Kitchen",
    "Sushi Nozomi", "The Burger Den", "Panera Bread", "Olive Garden",
    "Shake Shack", "Grubhub - Italian Restaurant", "Local Tavern Grill",
    "Bonefish Grill", "Cheesecake Factory", "Uber Eats - Ramen Bar",
    "Applebees", "Sunday Brunch The Larder", "Cosi Sandwich Shop",
    "Noodles and Company", "Five Guys", "Sweetgreen", "Chilis Bar Grill",
]
GAS_STATIONS = ["Shell Gas Station", "Chevron", "Exxon", "BP Gas", "Citgo"]
SHOPS = [
    "Amazon.com", "Target", "TJ Maxx", "Old Navy", "Best Buy",
    "Home Depot", "Etsy", "Nordstrom Rack", "HM", "Nike.com",
    "Wayfair", "Barnes Noble",
]

for m in range(1, 13):
    # ── Income ────────────────────────────────────────────────────────────────
    salary = round(5500 + (m - 1) * 30, 2)
    personal.append((date(2024, m, 1), "income", salary, "Direct Deposit - Employer Payroll"))

    if m in (2, 4, 6, 9, 11):
        personal.append((clamp_day(2024, m, rng.randint(10, 20)),
                         "income", R(680, 1480), "Freelance Consulting Payment"))

    if m == 11:
        personal.append((date(2024, 11, 15), "income", 2000.00, "Annual Performance Bonus"))

    # ── Rent ──────────────────────────────────────────────────────────────────
    personal.append((date(2024, m, 1), "rent", -1800.00, "Monthly Rent - Apartment 4B"))

    # ── Debt payments ─────────────────────────────────────────────────────────
    personal.append((clamp_day(2024, m, 15), "debt_payment", -385.00,
                     "Navient Student Loan Payment"))
    personal.append((clamp_day(2024, m, 28), "debt_payment", -R(280, 580),
                     "Chase Sapphire Reserve CC Payment"))

    # ── Utilities ─────────────────────────────────────────────────────────────
    if m in (1, 2, 12):      elec = R(118, 148)
    elif m in (6, 7, 8):     elec = R(135, 165)
    elif m in (3, 4, 5, 9):  elec = R(82, 108)
    else:                    elec = R(90, 120)
    personal.append((clamp_day(2024, m, rng.randint(8, 12)), "utilities",
                     -round(elec, 2), "ConEd Electric Bill"))
    personal.append((clamp_day(2024, m, 3), "utilities", -65.00, "Xfinity Internet Monthly"))
    personal.append((clamp_day(2024, m, 5), "utilities", -85.00, "Verizon Wireless Phone Bill"))

    # ── Subscriptions ─────────────────────────────────────────────────────────
    personal.append((clamp_day(2024, m, 2), "subscriptions", -15.99, "Netflix Standard Plan"))
    personal.append((clamp_day(2024, m, 2), "subscriptions", -9.99,  "Spotify Premium"))
    personal.append((clamp_day(2024, m, 2), "subscriptions", -45.00, "Planet Fitness Monthly Membership"))
    personal.append((clamp_day(2024, m, 2), "subscriptions", -2.99,  "iCloud Storage 50GB"))
    personal.append((clamp_day(2024, m, 2), "subscriptions", -18.99, "Hulu Plus Live TV"))
    if m == 3:
        personal.append((date(2024, 3, 2), "subscriptions", -139.00, "Amazon Prime Annual Renewal"))
    else:
        personal.append((clamp_day(2024, m, 2), "subscriptions", -14.99, "Amazon Prime Monthly"))
    if m in (1, 4, 7, 10):
        personal.append((clamp_day(2024, m, 2), "subscriptions", -17.99, "YouTube Premium Family Plan"))

    # ── Groceries — 4 weekly trips ────────────────────────────────────────────
    for week_start in (2, 9, 16, 23):
        d = clamp_day(2024, m, week_start + rng.randint(0, 2))
        store = rng.choice(GROCERY_STORES)
        personal.append((d, "groceries", -R(62, 128), f"{store} Weekly Grocery Run"))

    # ── Coffee shops — 3-5 per month ─────────────────────────────────────────
    for _ in range(rng.randint(3, 5)):
        d = clamp_day(2024, m, rng.randint(1, 28))
        personal.append((d, "dining", -R(5.50, 19.75), rng.choice(COFFEE_PLACES)))

    # ── Restaurants — 5-8 per month ──────────────────────────────────────────
    for _ in range(rng.randint(5, 8)):
        d = clamp_day(2024, m, rng.randint(1, 28))
        personal.append((d, "dining", -R(14.50, 88.00), rng.choice(RESTAURANTS)))

    # ── Transport — gas, rideshare, parking ───────────────────────────────────
    for _ in range(2):
        d = clamp_day(2024, m, rng.randint(1, 28))
        personal.append((d, "transport", -R(44.00, 68.00),
                         f"{rng.choice(GAS_STATIONS)} Fill Up"))
    for _ in range(rng.randint(2, 4)):
        d = clamp_day(2024, m, rng.randint(1, 28))
        svc = rng.choice(["Uber", "Lyft"])
        personal.append((d, "transport", -R(11.50, 42.00), f"{svc} Ride"))
    personal.append((clamp_day(2024, m, rng.randint(5, 25)),
                     "transport", -R(12, 28), "ParkWhiz Street Parking"))

    # ── Shopping — 1-3 per month ──────────────────────────────────────────────
    for _ in range(rng.randint(1, 3)):
        d = clamp_day(2024, m, rng.randint(1, 28))
        personal.append((d, "shopping", -R(18.00, 195.00),
                         f"{rng.choice(SHOPS)} Purchase"))

# ── Seasonal / irregular ─────────────────────────────────────────────────────
# Quarterly car insurance
for m_ins in (1, 4, 7, 10):
    personal.append((clamp_day(2024, m_ins, 20), "other",
                     -R(218, 248), "Geico Auto Insurance Quarterly Premium"))

# Healthcare
healthcare_rows = [
    (date(2024, 1, 22), -35.00,  "CVS Pharmacy Prescription Refill"),
    (date(2024, 3, 14), -175.00, "Dr Chen Annual Physical Copay"),
    (date(2024, 5, 8),  -220.00, "Downtown Dental Cleaning and Checkup"),
    (date(2024, 6, 19), -28.50,  "Walgreens OTC Medication"),
    (date(2024, 8, 5),  -190.00, "Urgent Care Visit Copay"),
    (date(2024, 10, 2), -42.00,  "CVS Pharmacy Prescription"),
    (date(2024, 11, 18),-165.00, "Eye Doctor Annual Exam and Lenses"),
]
for d, amt, desc in healthcare_rows:
    personal.append((d, "healthcare", amt, desc))

# Travel
travel_rows = [
    (date(2024, 3, 22), "other", -385.00, "Delta Airlines Spring Break Flights"),
    (date(2024, 3, 23), "other", -224.00, "Airbnb 3 Night Stay Nashville"),
    (date(2024, 3, 24), "other", -68.40,  "Dining Out Nashville Trip"),
    (date(2024, 3, 25), "other", -52.00,  "Uber Airport Transfers"),
    (date(2024, 7, 12), "other", -612.00, "United Airlines Summer Vacation"),
    (date(2024, 7, 13), "other", -890.00, "Hotel Marriott 4 Nights"),
    (date(2024, 7, 14), "other", -145.00, "Dining Vacation Week"),
    (date(2024, 7, 15), "other", -88.00,  "Excursion and Activities"),
    (date(2024, 7, 16), "other", -62.50,  "Dining Last Vacation Day"),
    (date(2024, 10, 18),"other", -298.00, "Southwest Airlines Fall Trip"),
    (date(2024, 10, 19),"other", -178.00, "Airbnb Weekend Stay"),
    (date(2024, 10, 20),"other", -94.00,  "Car Rental Weekend"),
]
for d, cat, amt, desc in travel_rows:
    personal.append((d, cat, amt, desc))

# Entertainment
entertainment_rows = [
    (date(2024, 1, 19), "other", -28.00,  "AMC Movie Tickets"),
    (date(2024, 2, 14), "other", -145.00, "Valentines Dinner Nobu Restaurant"),
    (date(2024, 4, 6),  "other", -82.00,  "MLB Baseball Game Tickets"),
    (date(2024, 5, 24), "other", -198.00, "Concert Tickets Live Nation"),
    (date(2024, 6, 8),  "other", -55.00,  "Comedy Club Night Out"),
    (date(2024, 8, 17), "other", -36.00,  "Cinema Evening"),
    (date(2024, 9, 28), "other", -110.00, "NFL Game Tickets"),
    (date(2024, 11, 29),"other", -42.00,  "Museum Holiday Exhibit"),
    (date(2024, 12, 20),"other", -188.00, "Holiday Concert Tickets"),
]
for d, cat, amt, desc in entertainment_rows:
    personal.append((d, cat, amt, desc))

# Car maintenance
car_rows = [
    (date(2024, 3, 9),  "other", -89.00,  "Jiffy Lube Oil Change and Filter"),
    (date(2024, 6, 22), "other", -320.00, "Firestone Tires and Brake Service"),
    (date(2024, 9, 14), "other", -145.00, "Mechanic Misc Auto Repair"),
]
for d, cat, amt, desc in car_rows:
    personal.append((d, cat, amt, desc))

# Home purchases
home_rows = [
    (date(2024, 2, 10), "shopping", -245.00, "IKEA Desk and Chair"),
    (date(2024, 5, 18), "shopping", -68.99,  "Amazon Kitchen Gadgets"),
    (date(2024, 8, 3),  "shopping", -159.00, "Wayfair Bedding Set"),
    (date(2024, 12, 5), "shopping", -200.00, "Holiday Gifts Amazon"),
]
for d, cat, amt, desc in home_rows:
    personal.append((d, cat, amt, desc))

# Savings transfers
personal.append((date(2024, 9, 8),   "savings", -500.00, "Transfer to Savings Account"))
personal.append((date(2024, 12, 31), "savings", -500.00, "Transfer to Savings Account Year End"))

# Misc
personal.append((date(2024, 12, 22), "other", -75.00, "Donation Local Food Bank"))
personal.append((date(2024, 4, 15),  "other", -80.00, "Birthday Gift for Friend"))
personal.append((date(2024, 2, 8),   "other", -52.00, "Gym Gear REI Purchase"))

personal.sort(key=lambda r: r[0])
print(f"Personal rows: {len(personal)}")

out = Path("data/sample/sample_personal.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "category", "amount", "description"])
    for r in personal:
        w.writerow([r[0].isoformat(), r[1], r[2], r[3]])

# ─────────────────────────────────────────────────────────────────────────────
# BUSINESS CSV  (~200 rows)
# ─────────────────────────────────────────────────────────────────────────────
business = []  # (date, type, category, amount, description)

# Revenue grows ~5-8% per month
saas_base = 42000
services_base = 8000

SOFTWARE_TOOLS = [
    ("AWS Cloud Infrastructure",    1800, 2800),
    ("GitHub Enterprise",             210,  210),
    ("Slack Business Plus",           180,  260),
    ("Figma Organization",            150,  220),
    ("Salesforce CRM",                900, 1400),
    ("HubSpot Marketing",             600,  900),
    ("Notion Team",                    80,   80),
    ("Zoom Business",                 200,  300),
    ("Linear Project Management",     100,  140),
    ("Datadog Monitoring",            400,  700),
]

MARKETING_ITEMS = [
    ("Google Ads - Search Campaign",   2800, 5500),
    ("LinkedIn Ads - B2B Targeting",   1500, 3200),
    ("Content Agency - Blog Posts",     800, 1600),
    ("PR Agency Retainer",            2000, 3000),
    ("SEO Tools - Ahrefs",              200,  200),
    ("Webinar Platform - Demio",        150,  150),
    ("Trade Show Booth Deposit",       3500, 6000),
    ("Email Platform - Klaviyo",        180,  350),
]

for m in range(1, 13):
    growth = 1 + 0.055 * (m - 1) + rng.uniform(-0.01, 0.015)
    saas_rev      = round(saas_base * growth, 2)
    services_rev  = round(services_base * (1 + 0.03 * (m - 1)) + rng.uniform(-500, 800), 2)

    # Revenue
    business.append((clamp_day(2024, m, 1), "revenue", "revenue",
                     saas_rev, "SaaS Subscription Revenue - Monthly ARR"))
    business.append((clamp_day(2024, m, 5), "revenue", "revenue",
                     services_rev, "Professional Services Revenue"))
    if m in (3, 6, 9, 12):
        upsell = round(rng.uniform(2500, 6000), 2)
        business.append((clamp_day(2024, m, rng.randint(10, 20)), "revenue", "revenue",
                         upsell, "Upsell / Expansion Revenue - Existing Accounts"))
    if m == 12:
        business.append((date(2024, 12, 28), "revenue", "revenue",
                         round(rng.uniform(4000, 8000), 2), "Year-End Enterprise Deal Close"))

    # COGS (hosting, support infra)
    cogs = round(saas_rev * rng.uniform(0.12, 0.18), 2)
    business.append((clamp_day(2024, m, 3), "expense", "cogs",
                     cogs, "Cloud Hosting and Infrastructure Costs"))

    # Payroll — lean team, grows as revenue scales
    eng_count = 2 if m <= 4 else (3 if m <= 9 else 4)
    eng_payroll = round(eng_count * rng.uniform(5800, 7000), 2)
    business.append((clamp_day(2024, m, 1), "expense", "payroll",
                     eng_payroll, f"Engineering Team Payroll ({eng_count} engineers)"))

    sales_count = 1 if m <= 5 else 2
    sales_payroll = round(sales_count * rng.uniform(3500, 4500), 2)
    business.append((clamp_day(2024, m, 1), "expense", "payroll",
                     sales_payroll, f"Sales and Marketing Team Payroll ({sales_count} reps)"))

    if m in (3, 7):  # Part-time contractor
        business.append((clamp_day(2024, m, 1), "expense", "payroll",
                         round(rng.uniform(400, 900), 2), "Contractor - Product Design"))

    # Office rent (flat)
    business.append((clamp_day(2024, m, 1), "expense", "rent",
                     3200.00, "Office Lease - 123 Startup Ave Suite 400"))

    # Software / SaaS tools — 2-3 items per month (small team = lean tooling)
    tools_this_month = rng.sample(SOFTWARE_TOOLS, k=rng.randint(2, 3))
    for tool_name, lo, hi in tools_this_month:
        business.append((clamp_day(2024, m, rng.randint(5, 20)), "expense", "software",
                         R(lo, hi), tool_name))

    # Marketing — 1-2 items per month
    mkt_items = rng.sample(MARKETING_ITEMS, k=rng.randint(1, 2))
    for mkt_name, lo, hi in mkt_items:
        business.append((clamp_day(2024, m, rng.randint(5, 25)), "expense", "marketing",
                         R(lo, hi), mkt_name))

    # Professional services
    business.append((clamp_day(2024, m, 28), "expense", "other",
                     650.00, "CPA Firm - Monthly Bookkeeping"))
    if m in (1, 4, 7, 10):
        business.append((clamp_day(2024, m, 20), "expense", "other",
                         round(rng.uniform(1200, 2500), 2), "Legal - Startup Counsel Retainer"))

    # Quarterly taxes
    if m in (4, 6, 9, 12):
        tax = round(rng.uniform(8000, 14000), 2)
        business.append((clamp_day(2024, m, 15), "expense", "other",
                         tax, "IRS Estimated Quarterly Tax Payment"))

    # Inventory (some months)
    if m in (2, 5, 8, 11):
        inv = round(rng.uniform(3500, 8000), 2)
        business.append((clamp_day(2024, m, rng.randint(8, 20)), "expense", "inventory",
                         inv, "Product Inventory Restock - Vendor Payment"))

    # Capex (occasional)
    if m == 3:
        business.append((date(2024, 3, 15), "expense", "other",
                         4800.00, "MacBook Laptops - New Engineering Hires (x3)"))
    if m == 7:
        business.append((date(2024, 7, 12), "expense", "other",
                         2200.00, "Office Standing Desks and Monitors"))

    # Office supplies and misc operating expenses
    business.append((clamp_day(2024, m, rng.randint(10, 22)), "expense", "other",
                     R(85, 320), "Office Supplies and Operating Expenses"))

    # Business insurance (semi-annual)
    if m in (1, 7):
        business.append((clamp_day(2024, m, 8), "expense", "other",
                         round(rng.uniform(1400, 1900), 2), "Business Liability Insurance Premium"))

    # Bank / payment processing fees
    processing_fee = round(saas_rev * rng.uniform(0.022, 0.028), 2)
    business.append((clamp_day(2024, m, rng.randint(20, 28)), "expense", "cogs",
                     processing_fee, "Stripe Payment Processing Fees"))

    # Travel / conferences
    if m in (3, 5, 9, 11):
        business.append((clamp_day(2024, m, rng.randint(10, 25)), "expense", "other",
                         round(rng.uniform(1200, 3500), 2), "Team Travel - Conference and Client Meetings"))

business.sort(key=lambda r: r[0])
print(f"Business rows: {len(business)}")

out_biz = Path("data/sample/sample_business.csv")
with open(out_biz, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "type", "category", "amount", "description"])
    for r in business:
        w.writerow([r[0].isoformat(), r[1], r[2], r[3], r[4]])

# ─────────────────────────────────────────────────────────────────────────────
# Quick validation
# ─────────────────────────────────────────────────────────────────────────────
import sys
sys.path.insert(0, ".")
from src.data_loader import parse_personal_csv, parse_business_csv, compute_summary

p_df = parse_personal_csv("data/sample/sample_personal.csv")
p_sum = compute_summary(p_df, "personal")
print(f"\nPersonal validation:")
print(f"  Rows parsed:       {len(p_df)}")
print(f"  Months covered:    {p_sum['n_months']}")
print(f"  Total income:      ${p_sum['total_income']:,.2f}")
print(f"  Total spending:    ${p_sum['total_spending']:,.2f}")
print(f"  Savings rate:      {p_sum['savings_rate']:.1%}")
print(f"  Monthly burn:      ${p_sum['monthly_burn']:,.2f}")
print(f"  Debt payments:     ${p_sum['debt_payments_total']:,.2f}")
print(f"  Subscriptions:     ${p_sum['subscription_total']:,.2f}")
print(f"  Top categories:    {list(p_sum['top_spending_categories'].keys())}")

b_df = parse_business_csv("data/sample/sample_business.csv")
b_sum = compute_summary(b_df, "business")
print(f"\nBusiness validation:")
print(f"  Rows parsed:       {len(b_df)}")
print(f"  Months covered:    {b_sum['n_months']}")
print(f"  Total revenue:     ${b_sum['total_revenue']:,.2f}")
print(f"  Total expenses:    ${b_sum['total_expenses']:,.2f}")
print(f"  Net income:        ${b_sum['net_income']:,.2f}")
print(f"  Gross margin:      {b_sum['gross_margin']:.1%}")
print(f"  Monthly burn:      ${b_sum['burn_rate']:,.2f}")
print(f"  Runway months:     {b_sum['runway_months']:.1f}")
print(f"  Top expense cats:  {list(b_sum['top_expense_categories'].keys())}")
