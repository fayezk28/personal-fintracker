"""SQLite query helpers for FinTracker. No ORM — raw sqlite3."""

from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def get_plan(db, plan_id=1):
    row = db.execute("SELECT * FROM plan_periods WHERE id = ?", (plan_id,)).fetchone()
    return dict(row) if row else None


def get_fixed_costs(db, plan_id=1):
    rows = db.execute(
        "SELECT * FROM fixed_costs WHERE plan_id = ? ORDER BY amount DESC", (plan_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_debts(db, plan_id=1):
    rows = db.execute(
        "SELECT * FROM debts WHERE plan_id = ? ORDER BY apr DESC", (plan_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Paychecks
# ---------------------------------------------------------------------------

def get_planned_paychecks(db, plan_id=1):
    rows = db.execute(
        """SELECT pp.*, ap.id AS actual_id, ap.received_date, ap.net_amount AS actual_net,
                  ap.rent_done, ap.efund_done, ap.roth_done, ap.spending_done, ap.notes AS actual_notes
           FROM planned_paychecks pp
           LEFT JOIN actual_paychecks ap ON ap.planned_id = pp.id
           WHERE pp.plan_id = ?
           ORDER BY pp.pay_date""",
        (plan_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def log_paycheck(db, planned_id, received_date, net_amount, rent_done, efund_done, roth_done, spending_done, notes=""):
    # Check if already logged
    existing = db.execute(
        "SELECT id FROM actual_paychecks WHERE planned_id = ?", (planned_id,)
    ).fetchone()
    if existing:
        db.execute(
            """UPDATE actual_paychecks
               SET received_date=?, net_amount=?, rent_done=?, efund_done=?,
                   roth_done=?, spending_done=?, notes=?
               WHERE planned_id=?""",
            (received_date, net_amount, rent_done, efund_done, roth_done, spending_done, notes, planned_id),
        )
    else:
        db.execute(
            """INSERT INTO actual_paychecks
               (planned_id, received_date, net_amount, rent_done, efund_done, roth_done, spending_done, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (planned_id, received_date, net_amount, rent_done, efund_done, roth_done, spending_done, notes),
        )
    db.commit()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def get_transactions(db, page=1, per_page=50, date_from=None, date_to=None,
                     category=None, account=None, flagged_only=False, search=None):
    conditions = []
    params = []

    if date_from:
        conditions.append("t.date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("t.date <= ?")
        params.append(date_to)
    if category:
        conditions.append("(t.category = ? OR t.parent_category = ? OR t.budget_category = ?)")
        params.extend([category, category, category])
    if account:
        conditions.append("t.account = ?")
        params.append(account)
    if flagged_only:
        conditions.append("t.flagged = 1")
    if search:
        conditions.append("t.name LIKE ?")
        params.append(f"%{search}%")

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    count = db.execute(f"SELECT COUNT(*) FROM transactions t WHERE {where}", params).fetchone()[0]

    rows = db.execute(
        f"""SELECT t.* FROM transactions t
            WHERE {where}
            ORDER BY t.date DESC, t.id DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    return {
        "transactions": [dict(r) for r in rows],
        "total": count,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (count + per_page - 1) // per_page),
    }


def get_transaction_categories(db):
    rows = db.execute(
        "SELECT DISTINCT category FROM transactions WHERE category IS NOT NULL AND category != '' ORDER BY category"
    ).fetchall()
    return [r[0] for r in rows]


def get_transaction_accounts(db):
    rows = db.execute(
        "SELECT DISTINCT account FROM transactions WHERE account IS NOT NULL AND account != '' ORDER BY account"
    ).fetchall()
    return [r[0] for r in rows]


def get_flagged_transactions(db, limit=20):
    rows = db.execute(
        """SELECT * FROM transactions
           WHERE flagged = 1
           ORDER BY date DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Monthly summary
# ---------------------------------------------------------------------------

def get_monthly_summary(db, year, month):
    date_from = f"{year}-{month:02d}-01"
    if month == 12:
        date_to = f"{year + 1}-01-01"
    else:
        date_to = f"{year}-{month + 1:02d}-01"

    # Spending by budget_category
    rows = db.execute(
        """SELECT budget_category, SUM(amount) as total, COUNT(*) as count
           FROM transactions
           WHERE date >= ? AND date < ? AND excluded = 'false' AND type = 'regular'
           GROUP BY budget_category
           ORDER BY total DESC""",
        (date_from, date_to),
    ).fetchall()
    by_category = [dict(r) for r in rows]

    # Spending by bank category (detail)
    detail_rows = db.execute(
        """SELECT category, parent_category, budget_category,
                  SUM(amount) as total, COUNT(*) as count
           FROM transactions
           WHERE date >= ? AND date < ? AND excluded = 'false' AND type = 'regular'
           GROUP BY category
           ORDER BY total DESC""",
        (date_from, date_to),
    ).fetchall()
    by_detail = [dict(r) for r in detail_rows]

    # Total income
    income = db.execute(
        """SELECT COALESCE(SUM(ABS(amount)), 0)
           FROM transactions
           WHERE date >= ? AND date < ? AND type = 'income'""",
        (date_from, date_to),
    ).fetchone()[0]

    # Total spending (positive amounts, regular transactions)
    spending = db.execute(
        """SELECT COALESCE(SUM(amount), 0)
           FROM transactions
           WHERE date >= ? AND date < ? AND excluded = 'false'
                 AND type = 'regular' AND amount > 0""",
        (date_from, date_to),
    ).fetchone()[0]

    # Flagged this month
    flagged = db.execute(
        """SELECT COUNT(*)
           FROM transactions
           WHERE date >= ? AND date < ? AND flagged = 1""",
        (date_from, date_to),
    ).fetchone()[0]

    return {
        "year": year,
        "month": month,
        "by_category": by_category,
        "by_detail": by_detail,
        "income": income,
        "spending": spending,
        "flagged_count": flagged,
    }


# ---------------------------------------------------------------------------
# Rent waterfall
# ---------------------------------------------------------------------------

def get_rent_waterfall(db, plan_id=1):
    plan = get_plan(db, plan_id)
    if not plan:
        return []

    paychecks = db.execute(
        "SELECT pay_date, alloc_rent FROM planned_paychecks WHERE plan_id = ? ORDER BY pay_date",
        (plan_id,),
    ).fetchall()

    balance = plan["rent_account_start_balance"]
    rent = plan["monthly_rent"]
    events = []

    events.append({
        "date": plan["start_date"],
        "event": "Starting balance",
        "amount": None,
        "balance": balance,
    })

    # Build timeline of rent payments and paycheck deposits
    rent_dates = []
    start = datetime.strptime(plan["start_date"], "%Y-%m-%d")
    end = datetime.strptime(plan["end_date"], "%Y-%m-%d") + timedelta(days=31)
    d = start
    while d <= end:
        rent_dates.append(d.strftime("%Y-%m-%d"))
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1)
        else:
            d = d.replace(month=d.month + 1)

    # Merge events chronologically
    all_events = []
    for rd in rent_dates:
        all_events.append((rd, "rent", rent))
    for pc in paychecks:
        all_events.append((pc["pay_date"], "deposit", pc["alloc_rent"]))
    all_events.sort(key=lambda x: x[0])

    for date, etype, amount in all_events:
        if etype == "rent":
            balance -= amount
            events.append({
                "date": date,
                "event": f"Rent payment",
                "amount": -amount,
                "balance": balance,
            })
        else:
            balance += amount
            events.append({
                "date": date,
                "event": f"Paycheck → Checking",
                "amount": amount,
                "balance": balance,
            })

    return events


# ---------------------------------------------------------------------------
# Plan progress / scorecard
# ---------------------------------------------------------------------------

def get_plan_progress(db, plan_id=1):
    plan = get_plan(db, plan_id)
    if not plan:
        return None

    paychecks = get_planned_paychecks(db, plan_id)

    # Count logged paychecks
    logged = [p for p in paychecks if p.get("actual_id")]
    total_planned_efund = sum(p["alloc_efund"] for p in paychecks)
    total_planned_roth = sum(p["alloc_roth_ira"] for p in paychecks)
    total_planned_buffer = sum(p["alloc_buffer"] for p in paychecks)

    completed_efund = sum(1 for p in logged if p.get("efund_done"))
    completed_roth = sum(1 for p in logged if p.get("roth_done"))
    completed_rent = sum(1 for p in logged if p.get("rent_done"))

    return {
        "plan": plan,
        "total_paychecks": len(paychecks),
        "logged_paychecks": len(logged),
        "total_planned_efund": total_planned_efund,
        "total_planned_roth": total_planned_roth,
        "total_planned_buffer": total_planned_buffer,
        "completed_efund": completed_efund,
        "completed_roth": completed_roth,
        "completed_rent": completed_rent,
    }


# ---------------------------------------------------------------------------
# Import batches
# ---------------------------------------------------------------------------

def get_import_batches(db, limit=10):
    rows = db.execute(
        "SELECT * FROM import_batches ORDER BY imported_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Settings / recalculate
# ---------------------------------------------------------------------------

def get_checklist(db, plan_id=1):
    rows = db.execute(
        "SELECT * FROM plan_checklist WHERE plan_id = ? ORDER BY sort_order, id",
        (plan_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def toggle_checklist_item(db, item_id, is_done):
    done_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if is_done else None
    db.execute(
        "UPDATE plan_checklist SET is_done = ?, done_at = ? WHERE id = ?",
        (1 if is_done else 0, done_at, item_id),
    )
    db.commit()


def get_spending_by_period(db, plan_id=1):
    """Calculate actual spending per pay period (between paycheck dates)."""
    paychecks = db.execute(
        "SELECT id, pay_date FROM planned_paychecks WHERE plan_id = ? ORDER BY pay_date",
        (plan_id,),
    ).fetchall()
    plan = get_plan(db, plan_id)
    if not plan or not paychecks:
        return []

    periods = []
    for i, pc in enumerate(paychecks):
        start = pc["pay_date"]
        if i + 1 < len(paychecks):
            end = paychecks[i + 1]["pay_date"]
        else:
            end = plan["end_date"]

        actual = db.execute(
            """SELECT COALESCE(SUM(amount), 0)
               FROM transactions
               WHERE date >= ? AND date < ? AND excluded = 'false'
                     AND type = 'regular' AND amount > 0""",
            (start, end),
        ).fetchone()[0]

        tx_count = db.execute(
            """SELECT COUNT(*)
               FROM transactions
               WHERE date >= ? AND date < ? AND excluded = 'false'
                     AND type = 'regular' AND amount > 0""",
            (start, end),
        ).fetchone()[0]

        flagged_count = db.execute(
            "SELECT COUNT(*) FROM transactions WHERE date >= ? AND date < ? AND flagged = 1",
            (start, end),
        ).fetchone()[0]

        budget = plan["alloc_spending"]
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        days = (end_dt - start_dt).days or 1
        periods.append({
            "paycheck_id": pc["id"],
            "start": start,
            "end": end,
            "days": days,
            "budget": budget,
            "actual": actual,
            "delta": budget - actual,
            "pct_used": round(actual / budget * 100) if budget else 0,
            "tx_count": tx_count,
            "flagged_count": flagged_count,
        })

    return periods


def update_plan(db, plan_id, **kwargs):
    allowed = {
        "alloc_rent", "alloc_efund", "alloc_roth_ira", "alloc_spending",
        "alloc_buffer", "monthly_rent", "net_paycheck_new", "gross_salary",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [plan_id]
    db.execute(f"UPDATE plan_periods SET {set_clause} WHERE id = ?", params)
    db.commit()


def recalculate_paychecks(db, plan_id=1):
    plan = get_plan(db, plan_id)
    if not plan:
        return

    paychecks = db.execute(
        "SELECT id, pay_date, is_bonus_check FROM planned_paychecks WHERE plan_id = ? ORDER BY pay_date",
        (plan_id,),
    ).fetchall()

    for pc in paychecks:
        net = plan["net_paycheck_new"]
        rent = plan["alloc_rent"]
        bills = (sum(fc["amount"] for fc in get_fixed_costs(db, plan_id)) - plan["monthly_rent"]) / 2
        roth = plan["alloc_roth_ira"]
        spending = plan["alloc_spending"]

        if pc["is_bonus_check"]:
            # No rent allocation — June 12 + June 26 pre-fund July rent.
            # Full remainder goes to e-fund.
            rent = 0
            efund = net - bills - roth - spending
            buffer = 0
        else:
            efund = plan["alloc_efund"]
            buffer = net - rent - bills - efund - roth - spending

        db.execute(
            """UPDATE planned_paychecks
               SET net_amount=?, alloc_rent=?, alloc_bills=?, alloc_efund=?,
                   alloc_roth_ira=?, alloc_spending=?, alloc_buffer=?
               WHERE id=?""",
            (net, rent, bills, efund, roth, spending, buffer, pc["id"]),
        )
    db.commit()
