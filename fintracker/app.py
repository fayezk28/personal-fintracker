"""FinTracker — Local financial tracker built on Flask + SQLite."""

import os
import sqlite3
from datetime import datetime

from flask import Flask, g, render_template, request, redirect, url_for, jsonify, flash

import models
import import_csv
import budget_engine
import plan_seed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "finance.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

app = Flask(__name__)
app.secret_key = os.urandom(24)


# ---------------------------------------------------------------------------
# Database lifecycle
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables and seed data on first run."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    with open(SCHEMA_PATH) as f:
        db.executescript(f.read())
    plan_seed.seed(db)
    db.close()


# ---------------------------------------------------------------------------
# Routes — Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    db = get_db()
    today = datetime.now()
    scorecard = budget_engine.plan_scorecard(db)
    monthly = budget_engine.monthly_scorecard(db, today.year, today.month)
    flagged = models.get_flagged_transactions(db, limit=10)
    waterfall = models.get_rent_waterfall(db)
    tracker = budget_engine.tracker_summary(db)
    return render_template(
        "dashboard.html",
        scorecard=scorecard,
        monthly=monthly,
        flagged=flagged,
        waterfall=waterfall,
        tracker=tracker,
        now=today,
    )


@app.route("/dashboard/data")
def dashboard_data():
    db = get_db()
    data = budget_engine.dashboard_chart_data(db)
    return jsonify(data)


# ---------------------------------------------------------------------------
# Routes — Tracker
# ---------------------------------------------------------------------------

@app.route("/tracker")
def tracker():
    db = get_db()
    data = budget_engine.tracker_summary(db)
    return render_template("tracker.html", t=data)


@app.route("/tracker/checklist", methods=["POST"])
def toggle_checklist():
    db = get_db()
    item_id = int(request.form["item_id"])
    is_done = request.form.get("is_done") == "1"
    models.toggle_checklist_item(db, item_id, is_done)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True})
    return redirect(url_for("tracker"))


# ---------------------------------------------------------------------------
# Routes — 90-Day Scorecard
# ---------------------------------------------------------------------------

@app.route("/scorecard")
def scorecard():
    db = get_db()
    plan = models.get_plan(db)
    paychecks = models.get_planned_paychecks(db)
    fixed_costs = models.get_fixed_costs(db)
    debts = models.get_debts(db)
    waterfall = models.get_rent_waterfall(db)
    progress = budget_engine.plan_scorecard(db)

    # Build monthly breakdown data
    months = []
    month_configs = [
        {"label": "April", "month": 4, "year": 2026, "star": False},
        {"label": "May", "month": 5, "year": 2026, "star": True},
        {"label": "June", "month": 6, "year": 2026, "star": False},
    ]
    for mc in month_configs:
        month_checks = [p for p in paychecks if p["pay_date"].startswith(f"{mc['year']}-{mc['month']:02d}")]
        net = sum(p["net_amount"] for p in month_checks)
        fixed_total = sum(fc["amount"] for fc in fixed_costs)
        available = net - fixed_total
        spending = sum(p["alloc_spending"] for p in month_checks)
        efund = sum(p["alloc_efund"] for p in month_checks)
        roth = sum(p["alloc_roth_ira"] for p in month_checks)
        buffer = sum(p["alloc_buffer"] for p in month_checks)
        months.append({
            "label": mc["label"],
            "star": mc["star"],
            "num_checks": len(month_checks),
            "net": net,
            "fixed": fixed_total,
            "available": available,
            "spending": spending,
            "efund": efund,
            "roth": roth,
            "buffer": buffer,
        })

    # Build running totals
    efund_start = 9561
    running = [{"idx": "—", "date": "Apr 1 (start)", "added": None, "efund": efund_start, "roth": 0}]
    cumulative_efund = efund_start
    cumulative_roth = 0
    for i, pc in enumerate(paychecks):
        cumulative_efund += pc["alloc_efund"]
        cumulative_roth += pc["alloc_roth_ira"]
        running.append({
            "idx": i + 1,
            "date": pc["pay_date"],
            "added": pc["alloc_efund"],
            "efund": cumulative_efund,
            "roth": cumulative_roth,
            "bonus": pc["is_bonus_check"],
            "logged": pc.get("actual_id") is not None,
        })

    return render_template(
        "scorecard.html",
        plan=plan,
        paychecks=paychecks,
        fixed_costs=fixed_costs,
        debts=debts,
        waterfall=waterfall,
        progress=progress,
        months=months,
        running=running,
    )


# ---------------------------------------------------------------------------
# Routes — Paychecks
# ---------------------------------------------------------------------------

@app.route("/paychecks")
def paychecks():
    db = get_db()
    checks = models.get_planned_paychecks(db)
    plan = models.get_plan(db)
    return render_template("paychecks.html", paychecks=checks, plan=plan)


@app.route("/paychecks/log", methods=["POST"])
def log_paycheck():
    db = get_db()
    planned_id = int(request.form["planned_id"])
    received_date = request.form.get("received_date", datetime.now().strftime("%Y-%m-%d"))
    net_amount = float(request.form.get("net_amount", 0))
    rent_done = 1 if request.form.get("rent_done") else 0
    efund_done = 1 if request.form.get("efund_done") else 0
    roth_done = 1 if request.form.get("roth_done") else 0
    spending_done = 1 if request.form.get("spending_done") else 0
    notes = request.form.get("notes", "")

    models.log_paycheck(db, planned_id, received_date, net_amount, rent_done, efund_done, roth_done, spending_done, notes)
    flash("Paycheck logged successfully.", "success")
    return redirect(url_for("paychecks"))


# ---------------------------------------------------------------------------
# Routes — Import
# ---------------------------------------------------------------------------

@app.route("/import", methods=["GET", "POST"])
def import_page():
    db = get_db()
    result = None
    batches = models.get_import_batches(db)

    if request.method == "POST":
        file = request.files.get("csv_file")
        if file and file.filename:
            result = import_csv.import_csv(db, file.stream, filename=file.filename)
            flash(
                f"Imported {result['new']} new transactions ({result['skipped']} duplicates skipped, {result['flagged']} flagged).",
                "success",
            )
            batches = models.get_import_batches(db)
        else:
            flash("Please select a CSV file.", "error")

    return render_template("import.html", result=result, batches=batches)


# ---------------------------------------------------------------------------
# Routes — Transactions
# ---------------------------------------------------------------------------

@app.route("/transactions")
def transactions():
    db = get_db()
    page = int(request.args.get("page", 1))
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    category = request.args.get("category")
    account = request.args.get("account")
    flagged_only = request.args.get("flagged_only") == "1"
    search = request.args.get("search")

    data = models.get_transactions(
        db, page=page, date_from=date_from, date_to=date_to,
        category=category, account=account, flagged_only=flagged_only, search=search,
    )
    categories = models.get_transaction_categories(db)
    accounts = models.get_transaction_accounts(db)

    return render_template(
        "transactions.html",
        data=data,
        categories=categories,
        accounts=accounts,
        filters={
            "date_from": date_from or "",
            "date_to": date_to or "",
            "category": category or "",
            "account": account or "",
            "flagged_only": flagged_only,
            "search": search or "",
        },
    )


# ---------------------------------------------------------------------------
# Routes — Settings
# ---------------------------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
def settings():
    db = get_db()
    plan = models.get_plan(db)
    fixed_costs = models.get_fixed_costs(db)
    debts = models.get_debts(db)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_allocations":
            models.update_plan(
                db, plan["id"],
                alloc_rent=float(request.form.get("alloc_rent", plan["alloc_rent"])),
                alloc_efund=float(request.form.get("alloc_efund", plan["alloc_efund"])),
                alloc_roth_ira=float(request.form.get("alloc_roth_ira", plan["alloc_roth_ira"])),
                alloc_spending=float(request.form.get("alloc_spending", plan["alloc_spending"])),
                monthly_rent=float(request.form.get("monthly_rent", plan["monthly_rent"])),
                net_paycheck_new=float(request.form.get("net_paycheck_new", plan["net_paycheck_new"])),
            )
            models.recalculate_paychecks(db, plan["id"])
            flash("Plan updated and paychecks recalculated.", "success")
            return redirect(url_for("settings"))

    return render_template("settings.html", plan=plan, fixed_costs=fixed_costs, debts=debts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("Creating database and seeding plan data...")
        init_db()
        print(f"Database created at {DB_PATH}")
    else:
        # Ensure schema is up to date
        init_db()

    print("Starting FinTracker at http://localhost:5050")
    app.run(debug=True, port=5050)
