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


def dashboard_chart_data(db, plan_id=1):
    """Return JSON-serializable data for Chart.js on the dashboard."""
    from datetime import datetime
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

    # Plan progress for gauges
    scorecard = plan_scorecard(db, plan_id)

    return {
        "months": months,
        "scorecard": {
            "efund_pct": scorecard["efund_pct"],
            "roth_pct": scorecard["roth_pct"],
            "pct_complete": scorecard["pct_complete"],
            "efund_current": scorecard["efund_current"],
            "efund_target": scorecard["efund_target"],
            "roth_deposits": scorecard["roth_deposits"],
            "roth_target": scorecard["roth_target"],
            "logged": scorecard["logged_paychecks"],
            "total": scorecard["total_paychecks"],
        },
    }
