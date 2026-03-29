"""Budget vs actual comparison engine and plan scorecard."""

from datetime import datetime, timedelta

from models import (
    get_plan, get_fixed_costs, get_planned_paychecks, get_monthly_summary,
    get_rent_waterfall, get_checklist, get_spending_by_period,
)


def monthly_scorecard(db, year, month, plan_id=1):
    """Compare actual spending vs. plan allocations for a given month."""
    plan = get_plan(db, plan_id)
    if not plan:
        return None

    summary = get_monthly_summary(db, year, month)

    # Planned spending for this month
    paychecks = db.execute(
        """SELECT * FROM planned_paychecks
           WHERE plan_id = ? AND pay_date >= ? AND pay_date < ?
           ORDER BY pay_date""",
        (plan_id, f"{year}-{month:02d}-01",
         f"{year}-{month + 1:02d}-01" if month < 12 else f"{year + 1}-01-01"),
    ).fetchall()

    planned_spending = sum(p["alloc_spending"] for p in paychecks)
    planned_efund = sum(p["alloc_efund"] for p in paychecks)
    planned_roth = sum(p["alloc_roth_ira"] for p in paychecks)
    num_checks = len(paychecks)

    actual_spending = summary["spending"]
    spending_delta = planned_spending - actual_spending  # positive = under budget

    # Fixed costs comparison
    fixed_costs = get_fixed_costs(db, plan_id)
    planned_fixed = sum(fc["amount"] for fc in fixed_costs)

    # Get actual fixed spending from transactions
    actual_fixed = 0
    for cat in summary["by_category"]:
        if cat["budget_category"] == "Fixed":
            actual_fixed += cat["total"]

    fixed_delta = planned_fixed - actual_fixed

    return {
        "year": year,
        "month": month,
        "num_checks": num_checks,
        "planned_spending": planned_spending,
        "actual_spending": actual_spending,
        "spending_delta": spending_delta,
        "spending_status": "under" if spending_delta >= 0 else "over",
        "planned_fixed": planned_fixed,
        "actual_fixed": actual_fixed,
        "fixed_delta": fixed_delta,
        "planned_efund": planned_efund,
        "planned_roth": planned_roth,
        "income": summary["income"],
        "flagged_count": summary["flagged_count"],
        "by_category": summary["by_category"],
        "by_detail": summary["by_detail"],
    }


def plan_scorecard(db, plan_id=1):
    """Overall 90-day plan progress."""
    plan = get_plan(db, plan_id)
    if not plan:
        return None

    paychecks = get_planned_paychecks(db, plan_id)
    logged = [p for p in paychecks if p.get("actual_id")]

    # Totals
    total_efund = sum(p["alloc_efund"] for p in paychecks)
    total_roth = sum(p["alloc_roth_ira"] for p in paychecks)
    total_buffer = sum(p["alloc_buffer"] for p in paychecks)

    # Confirmed allocations
    confirmed_rent = sum(1 for p in logged if p.get("rent_done"))
    confirmed_efund = sum(1 for p in logged if p.get("efund_done"))
    confirmed_roth = sum(1 for p in logged if p.get("roth_done"))

    # E-fund running total (starting balance + confirmed deposits)
    efund_start = 9561  # post-CC-payoff liquid reserves
    efund_deposits = sum(
        p["alloc_efund"] for p in logged if p.get("efund_done")
    )
    efund_current = efund_start + efund_deposits
    efund_target = efund_start + total_efund  # $9,946

    # Roth IRA
    roth_deposits = sum(
        p["alloc_roth_ira"] for p in logged if p.get("roth_done")
    )
    roth_target = total_roth  # $1,883

    waterfall = get_rent_waterfall(db, plan_id)

    return {
        "plan": plan,
        "total_paychecks": len(paychecks),
        "logged_paychecks": len(logged),
        "pct_complete": round(len(logged) / len(paychecks) * 100) if paychecks else 0,
        "total_efund_planned": total_efund,
        "total_roth_planned": total_roth,
        "total_buffer_planned": total_buffer,
        "confirmed_rent": confirmed_rent,
        "confirmed_efund": confirmed_efund,
        "confirmed_roth": confirmed_roth,
        "efund_start": efund_start,
        "efund_current": efund_current,
        "efund_target": efund_target,
        "efund_pct": round(efund_deposits / total_efund * 100) if total_efund else 0,
        "roth_deposits": roth_deposits,
        "roth_target": roth_target,
        "roth_pct": round(roth_deposits / roth_target * 100) if roth_target else 0,
        "waterfall": waterfall,
    }


def tracker_summary(db, plan_id=1):
    """Build the full tracker view: timeline, checklist, spending periods, next actions."""
    plan = get_plan(db, plan_id)
    if not plan:
        return None

    today = datetime.now()
    start = datetime.strptime(plan["start_date"], "%Y-%m-%d")
    end = datetime.strptime(plan["end_date"], "%Y-%m-%d")
    total_days = (end - start).days
    elapsed_days = max(0, min((today - start).days, total_days))
    days_remaining = max(0, total_days - elapsed_days)
    pct_elapsed = round(elapsed_days / total_days * 100) if total_days else 0

    paychecks = get_planned_paychecks(db, plan_id)
    scorecard = plan_scorecard(db, plan_id)
    checklist = get_checklist(db, plan_id)
    spending_periods = get_spending_by_period(db, plan_id)

    # Group checklist by phase
    phases = {}
    for item in checklist:
        phase = item["phase"]
        if phase not in phases:
            phases[phase] = {"name": phase, "checklist_items": [], "done": 0, "total": 0}
        phases[phase]["checklist_items"].append(item)
        phases[phase]["total"] += 1
        if item["is_done"]:
            phases[phase]["done"] += 1

    checklist_total = len(checklist)
    checklist_done = sum(1 for c in checklist if c["is_done"])

    # Current spending period
    current_period = None
    for sp in spending_periods:
        if sp["start"] <= today.strftime("%Y-%m-%d") < sp["end"]:
            current_period = sp
            break
    if not current_period and spending_periods:
        if today.strftime("%Y-%m-%d") >= spending_periods[-1]["start"]:
            current_period = spending_periods[-1]

    # Next upcoming paycheck
    next_paycheck = None
    for pc in paychecks:
        if pc["pay_date"] >= today.strftime("%Y-%m-%d") and not pc.get("actual_id"):
            next_paycheck = pc
            break

    # Upcoming checklist items (not done, with due dates, sorted by due date)
    upcoming_items = sorted(
        [c for c in checklist if not c["is_done"] and c["due_date"]],
        key=lambda c: c["due_date"],
    )[:5]

    return {
        "plan": plan,
        "today": today.strftime("%Y-%m-%d"),
        "total_days": total_days,
        "elapsed_days": elapsed_days,
        "days_remaining": days_remaining,
        "pct_elapsed": pct_elapsed,
        "scorecard": scorecard,
        "phases": list(phases.values()),
        "checklist_total": checklist_total,
        "checklist_done": checklist_done,
        "checklist_pct": round(checklist_done / checklist_total * 100) if checklist_total else 0,
        "spending_periods": spending_periods,
        "current_period": current_period,
        "next_paycheck": next_paycheck,
        "upcoming_items": upcoming_items,
    }


def tracker_chart_data(db, plan_id=1):
    """Return JSON-serializable data for the tracker charts."""
    spending_periods = get_spending_by_period(db, plan_id)

    # Spending by period: label, budget, actual, cumulative
    cumulative_budget = 0
    cumulative_actual = 0
    periods_chart = []
    for i, sp in enumerate(spending_periods):
        cumulative_budget += sp["budget"]
        cumulative_actual += sp["actual"]
        periods_chart.append({
            "label": f"Pay {i + 1}\n{sp['start']}",
            "budget": sp["budget"],
            "actual": sp["actual"],
            "cumulative_budget": cumulative_budget,
            "cumulative_actual": cumulative_actual,
        })

    # Savings timeline: per-paycheck planned vs actual running totals
    paychecks = get_planned_paychecks(db, plan_id)
    efund_start = 9561
    cumulative_efund_planned = efund_start
    cumulative_efund_actual = efund_start
    cumulative_roth_planned = 0
    cumulative_roth_actual = 0

    savings_timeline = [
        {
            "label": "Apr 1 (start)",
            "efund_planned": efund_start,
            "efund_actual": efund_start,
            "roth_planned": 0,
            "roth_actual": 0,
        }
    ]
    for pc in paychecks:
        cumulative_efund_planned += pc["alloc_efund"]
        cumulative_roth_planned += pc["alloc_roth_ira"]
        if pc.get("actual_id"):
            if pc.get("efund_done"):
                cumulative_efund_actual += pc["alloc_efund"]
            if pc.get("roth_done"):
                cumulative_roth_actual += pc["alloc_roth_ira"]
        savings_timeline.append({
            "label": pc["pay_date"],
            "efund_planned": cumulative_efund_planned,
            "efund_actual": cumulative_efund_actual,
            "roth_planned": cumulative_roth_planned,
            "roth_actual": cumulative_roth_actual,
        })

    return {
        "spending_periods": periods_chart,
        "savings_timeline": savings_timeline,
    }


def end_of_year_forecast(db, year=None):
    """Project end-of-year totals based on actual weekly pace."""
    today = datetime.now().date()
    target_year = year or today.year
    year_start = datetime(target_year, 1, 1).date()
    year_end = datetime(target_year, 12, 31).date()
    cutoff = min(today, year_end)

    tx_rows = db.execute(
        """SELECT date, amount, type, excluded
           FROM transactions
           WHERE date >= ? AND date <= ?
           ORDER BY date""",
        (year_start.strftime("%Y-%m-%d"), cutoff.strftime("%Y-%m-%d")),
    ).fetchall()

    income_actual = 0.0
    spending_actual = 0.0
    weekly = {}

    for row in tx_rows:
        dt = datetime.strptime(row["date"], "%Y-%m-%d").date()
        week_key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        if week_key not in weekly:
            weekly[week_key] = {"income": 0.0, "spending": 0.0}

        if row["type"] == "income":
            amount = abs(float(row["amount"] or 0))
            income_actual += amount
            weekly[week_key]["income"] += amount
        elif row["type"] == "regular" and str(row["excluded"]).lower() == "false" and float(row["amount"] or 0) > 0:
            amount = float(row["amount"])
            spending_actual += amount
            weekly[week_key]["spending"] += amount

    week_labels = sorted(weekly.keys())
    weeks_elapsed = max(1, len(week_labels))
    weeks_total = datetime(target_year, 12, 28).isocalendar().week
    weeks_remaining = max(0, weeks_total - weeks_elapsed)

    income_weekly_avg = income_actual / weeks_elapsed
    spending_weekly_avg = spending_actual / weeks_elapsed

    income_projected = income_actual + (income_weekly_avg * weeks_remaining)
    spending_projected = spending_actual + (spending_weekly_avg * weeks_remaining)

    weekly_points = [
        {
            "week": wk,
            "income": round(weekly[wk]["income"], 2),
            "spending": round(weekly[wk]["spending"], 2),
        }
        for wk in week_labels
    ]

    return {
        "year": target_year,
        "as_of": cutoff.strftime("%Y-%m-%d"),
        "weeks_elapsed": weeks_elapsed,
        "weeks_total": weeks_total,
        "weeks_remaining": weeks_remaining,
        "income_actual": round(income_actual, 2),
        "spending_actual": round(spending_actual, 2),
        "net_actual": round(income_actual - spending_actual, 2),
        "income_weekly_avg": round(income_weekly_avg, 2),
        "spending_weekly_avg": round(spending_weekly_avg, 2),
        "income_projected": round(income_projected, 2),
        "spending_projected": round(spending_projected, 2),
        "net_projected": round(income_projected - spending_projected, 2),
        "weekly_points": weekly_points,
    }


def trip_scenario_plan(db, trip_cost, trip_date, contingency_pct=10, plan_id=1):
    """Model allocation adjustments needed to fund a one-time upcoming trip."""
    plan = get_plan(db, plan_id)
    paychecks = get_planned_paychecks(db, plan_id)
    today = datetime.now().date()
    trip_dt = datetime.strptime(trip_date, "%Y-%m-%d").date()

    total_trip = trip_cost * (1 + (contingency_pct / 100.0))
    eligible = [
        p for p in paychecks
        if today <= datetime.strptime(p["pay_date"], "%Y-%m-%d").date() <= trip_dt
    ]
    checks_count = len(eligible)
    per_check = (total_trip / checks_count) if checks_count else total_trip

    strategies = []

    def build_strategy(key, label, from_buffer=0.0, from_spending=0.0, from_efund=0.0):
        new_buffer = plan["alloc_buffer"] - from_buffer
        new_spending = plan["alloc_spending"] - from_spending
        new_efund = plan["alloc_efund"] - from_efund
        feasible = new_buffer >= 0 and new_spending >= 0 and new_efund >= 0
        risk = "Low" if feasible and new_buffer >= 50 else ("Medium" if feasible else "High")
        strategies.append({
            "key": key,
            "label": label,
            "feasible": feasible,
            "risk": risk,
            "from_buffer": round(from_buffer, 2),
            "from_spending": round(from_spending, 2),
            "from_efund": round(from_efund, 2),
            "new_buffer": round(new_buffer, 2),
            "new_spending": round(new_spending, 2),
            "new_efund": round(new_efund, 2),
        })

    build_strategy("buffer_only", "Buffer only", from_buffer=per_check)
    build_strategy("spending_only", "Spending only", from_spending=per_check)
    build_strategy(
        "balanced",
        "Balanced (60% buffer / 40% spending)",
        from_buffer=per_check * 0.6,
        from_spending=per_check * 0.4,
    )
    build_strategy(
        "protect_cashflow",
        "Protect cashflow (50% e-fund / 50% buffer)",
        from_buffer=per_check * 0.5,
        from_efund=per_check * 0.5,
    )

    return {
        "trip_cost": round(trip_cost, 2),
        "contingency_pct": contingency_pct,
        "trip_total": round(total_trip, 2),
        "trip_date": trip_date,
        "checks_count": checks_count,
        "per_check": round(per_check, 2),
        "eligible_checks": [
            {
                "date": p["pay_date"],
                "net_amount": p["net_amount"],
                "is_bonus": bool(p["is_bonus_check"]),
            }
            for p in eligible
        ],
        "strategies": strategies,
    }


def dashboard_chart_data(db, plan_id=1):
    """Return JSON-serializable data for Chart.js on the dashboard."""
    today = datetime.now()

    # Last 3 months of spending by category
    months = []
    for offset in range(2, -1, -1):
        m = today.month - offset
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        summary = get_monthly_summary(db, y, m)
        spending_cats = {}
        for cat in summary["by_category"]:
            label = cat["budget_category"] or "Uncategorized"
            if label in ("Transfer", "Income"):
                continue
            spending_cats[label] = cat["total"]
        months.append({
            "label": f"{y}-{m:02d}",
            "categories": spending_cats,
            "total_spending": summary["spending"],
            "income": summary["income"],
        })

    return {"months": months}
