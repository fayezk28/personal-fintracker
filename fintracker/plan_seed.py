"""Seeds the 90-day financial recovery plan into the database."""


def seed(db):
    """Insert all plan data. Safe to call multiple times — checks for existing plan."""
    cur = db.execute("SELECT COUNT(*) FROM plan_periods")
    if cur.fetchone()[0] > 0:
        return  # already seeded

    # Plan period
    db.execute(
        """INSERT INTO plan_periods
           (name, start_date, end_date, gross_salary,
            net_paycheck_old, net_paycheck_new, raise_effective_date,
            pay_frequency, alloc_rent, alloc_efund, alloc_roth_ira,
            alloc_spending, alloc_buffer, monthly_rent, rent_account_start_balance)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "90-Day Recovery Plan",
            "2026-04-01",
            "2026-06-30",
            123935.40,
            2945.47,
            3030.00,
            "2026-04-07",
            "biweekly",
            1550.00,
            475.00,
            269.00,
            400.00,
            101.00,
            3100.00,
            3250.00,
        ),
    )
    plan_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Fixed costs (monthly amounts from financial_plan.html)
    fixed_costs = [
        ("Rent (your portion)", 3100.00),
        ("Car Payment (Driveway Finance)", 260.00),
        ("ConEd (split with roommate)", 66.50),
        ("Spectrum (split with roommate)", 40.00),
        ("Gym (net after $75 reimbursement)", 60.39),
        ("Hulu", 32.46),
        ("State Farm", 10.83),
    ]
    for name, amount in fixed_costs:
        db.execute(
            "INSERT INTO fixed_costs (plan_id, name, amount) VALUES (?, ?, ?)",
            (plan_id, name, amount),
        )

    # Debts
    debts = [
        ("Car Loan", 12863.00, 5.94, 260.00, "2030-12-25", "active", None),
        (
            "Student Loan 1-01 (Subsidized)",
            3662.00,
            2.75,
            0,
            "2040-07-25",
            "forbearance",
            "SAVE plan forbearance through 10/31/2028. Current balance w/ interest: $3,739.70",
        ),
        (
            "Student Loan 1-02 (Unsubsidized)",
            3838.00,
            2.75,
            0,
            "2040-07-25",
            "forbearance",
            "SAVE plan forbearance through 10/31/2028. Current balance w/ interest: $3,919.43",
        ),
    ]
    for name, balance, apr, min_pay, maturity, status, notes in debts:
        db.execute(
            """INSERT INTO debts
               (plan_id, name, balance, apr, min_payment, maturity_date, status, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (plan_id, name, balance, apr, min_pay, maturity, status, notes),
        )

    # 7 planned paychecks: Apr 3 (old rate), Apr 17-Jun 26 (new rate)
    # Per-paycheck bills = (total fixed - rent) / 2 = (3570.18 - 3100) / 2 = 235.09
    bills_per_check = 235.09
    paychecks = [
        # (date, net, rent, bills, efund, roth, spending, buffer, is_bonus, notes)
        ("2026-04-03", 2945.47, 1550, bills_per_check, 400, 269, 400, 91.38, 0, "Last check at old $120K rate"),
        ("2026-04-17", 3030.00, 1550, bills_per_check, 475, 269, 400, 100.91, 0, "First check at new rate"),
        ("2026-05-01", 3030.00, 1550, bills_per_check, 475, 269, 400, 100.91, 0, None),
        ("2026-05-15", 3030.00, 1550, bills_per_check, 475, 269, 400, 100.91, 0, None),
        ("2026-05-29", 3030.00, 1550, bills_per_check, 576, 269, 400, 0, 1, "Bonus 3rd paycheck — buffer redirected to E-Fund"),
        ("2026-06-12", 3030.00, 1550, bills_per_check, 475, 269, 400, 100.91, 0, None),
        ("2026-06-26", 3030.00, 1550, bills_per_check, 475, 269, 400, 100.91, 0, None),
    ]
    for date, net, rent, bills, efund, roth, spend, buf, bonus, notes in paychecks:
        db.execute(
            """INSERT INTO planned_paychecks
               (plan_id, pay_date, net_amount, alloc_rent, alloc_bills,
                alloc_efund, alloc_roth_ira, alloc_spending, alloc_buffer,
                is_bonus_check, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (plan_id, date, net, rent, bills, efund, roth, spend, buf, bonus, notes),
        )

    # Flag rules — gambling and subscription patterns
    flag_rules = [
        ("DraftKings", "name", "Gambling"),
        ("FanDuel", "name", "Gambling"),
        ("BetMGM", "name", "Gambling"),
        ("Caesars", "name", "Gambling"),
        ("PointsBet", "name", "Gambling"),
        ("BetRivers", "name", "Gambling"),
        ("Barstool", "name", "Gambling"),
        ("ESPN BET", "name", "Gambling"),
        ("Hard Rock Bet", "name", "Gambling"),
        ("Bet365", "name", "Gambling"),
        ("Gambling", "category", "Gambling"),
    ]
    for pattern, field, reason in flag_rules:
        db.execute(
            "INSERT INTO flag_rules (pattern, match_field, flag_reason) VALUES (?, ?, ?)",
            (pattern, field, reason),
        )

    # Budget category mappings (bank category → plan category)
    category_map = [
        ("Rent", None, "Fixed"),
        ("Mortgage & Rent", None, "Fixed"),
        ("Insurance", None, "Fixed"),
        ("Internet", None, "Fixed"),
        ("Utilities", None, "Fixed"),
        ("Phone", None, "Fixed"),
        ("Gym", "Health & Wellness", "Fixed"),
        ("Car", None, "Fixed"),
        ("Auto Payment", None, "Fixed"),
        ("Groceries", "Food & Drink", "Spending"),
        ("Restaurants", "Food & Drink", "Spending"),
        ("Fast Food", "Food & Drink", "Spending"),
        ("Coffee Shops", "Food & Drink", "Spending"),
        ("Food & Drink", None, "Spending"),
        ("Alcohol & Bars", "Food & Drink", "Spending"),
        ("Shopping", None, "Spending"),
        ("Clothing", "Shopping", "Spending"),
        ("Electronics", "Shopping", "Spending"),
        ("Entertainment", None, "Spending"),
        ("Movies & DVDs", "Entertainment", "Spending"),
        ("Music", "Entertainment", "Spending"),
        ("Gas & Fuel", "Auto & Transport", "Spending"),
        ("Parking", "Auto & Transport", "Spending"),
        ("Ride Share", "Auto & Transport", "Spending"),
        ("Public Transportation", "Auto & Transport", "Spending"),
        ("Auto & Transport", None, "Spending"),
        ("Personal Care", None, "Spending"),
        ("Health & Wellness", None, "Spending"),
        ("Education", None, "Spending"),
        ("Gifts & Donations", None, "Spending"),
        ("Travel", None, "Spending"),
        ("Transfer", None, "Transfer"),
        ("Credit Card Payment", None, "Transfer"),
        ("Internal Transfer", None, "Transfer"),
        ("Paycheck", "Income", "Income"),
        ("Income", None, "Income"),
        ("Returned Purchase", None, "Income"),
        ("Interest", None, "Income"),
        ("Gambling", None, "Spending"),
    ]
    for bank_cat, parent_cat, plan_cat in category_map:
        db.execute(
            """INSERT INTO budget_category_map
               (bank_category, bank_parent_category, plan_category)
               VALUES (?, ?, ?)""",
            (bank_cat, parent_cat, plan_cat),
        )

    # Checklist items from the 90-day plan
    checklist = [
        # Phase 1: April 1 — Before the First Paycheck
        ("April 1 — Day One", "Pay off all $7,220 in CC debt from Individual Cash Account", 1, "2026-04-01"),
        ("April 1 — Day One", "April rent paid from Checking account ($3,250 already there)", 2, "2026-04-01"),
        ("April 1 — Day One", "Contact student loan servicer — confirm forbearance active, request refund of Jan 1 payment ($475.58)", 3, "2026-04-07"),
        ("April 1 — Day One", "Cancel any student loan autopay immediately", 4, "2026-04-01"),
        ("April 1 — Day One", "Before April 15: Put remaining $3,780 into Roth IRA as 2025 contribution", 5, "2026-04-15"),

        # Phase 2: April setup
        ("April — Setup", "Verify Apr 17 paycheck reflects the raise", 10, "2026-04-17"),
        ("April — Setup", "Set up $1,550 auto-transfer to Checking each payday for rent funding", 11, "2026-04-03"),
        ("April — Setup", "Set up automatic $269/paycheck to Roth IRA", 12, "2026-04-03"),
        ("April — Setup", "Pull March pay stubs — identify what caused $1,329/$1,346 amounts", 13, "2026-04-07"),

        # Phase 3: Ongoing habits
        ("Ongoing — Every Paycheck", "Transfer $1,550 to Checking (rent account) on payday", 20, None),
        ("Ongoing — Every Paycheck", "Move $475 (or $400 for Apr 3) to emergency fund", 21, None),
        ("Ongoing — Every Paycheck", "Contribute $269 to Roth IRA", 22, None),
        ("Ongoing — Every Paycheck", "$400 spending — that's your ceiling", 23, None),
        ("Ongoing — Every Paycheck", "Sweep unspent buffer to E-Fund every Sunday", 24, None),

        # Phase 4: Monthly checks
        ("Monthly Checks", "Pay every CC statement in full — no exceptions", 30, None),
        ("Monthly Checks", "Weekly 10-min Sunday spending check — scan transactions", 31, None),
        ("Monthly Checks", "Hard cap on gambling: $50/month or $0", 32, None),
        ("Monthly Checks", "Confirm W-4 withholding is accurate on new salary", 33, "2026-05-15"),

        # Phase 5: May bonus month
        ("May — Bonus Month", "May 29 bonus paycheck — full buffer redirected to E-Fund", 40, "2026-05-29"),
        ("May — Bonus Month", "3rd paycheck rent allocation ($1,550) pre-funds July", 41, "2026-05-29"),

        # Phase 6: June — End of Plan
        ("June — End of Plan", "Evaluate increasing Roth 401K from 4% to 6%", 50, "2026-06-30"),
        ("June — End of Plan", "Set next 90-day targets", 51, "2026-06-30"),
    ]
    for phase, item, sort_order, due_date in checklist:
        db.execute(
            """INSERT INTO plan_checklist
               (plan_id, phase, item, sort_order, due_date)
               VALUES (?, ?, ?, ?, ?)""",
            (plan_id, phase, item, sort_order, due_date),
        )

    db.commit()
