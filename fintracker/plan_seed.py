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
        ("Car Loan", 13063.09, 5.94, 260.00, "2030-12-25", "active", None),
        (
            "Student Loan 1-01 (Subsidized)",
            3662.00,
            2.75,
            0,
            "2040-07-25",
            "forbearance",
            "SAVE plan forbearance through 10/31/2028",
        ),
        (
            "Student Loan 1-02 (Unsubsidized)",
            3838.00,
            2.75,
            0,
            "2040-07-25",
            "forbearance",
            "SAVE plan forbearance through 10/31/2028",
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

    db.commit()
