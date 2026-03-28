-- FinTracker Database Schema
-- SQLite, created on first run

CREATE TABLE IF NOT EXISTS plan_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    gross_salary REAL,
    net_paycheck_old REAL,
    net_paycheck_new REAL,
    raise_effective_date TEXT,
    pay_frequency TEXT DEFAULT 'biweekly',
    alloc_rent REAL,
    alloc_efund REAL,
    alloc_roth_ira REAL,
    alloc_spending REAL,
    alloc_buffer REAL,
    monthly_rent REAL,
    rent_account_start_balance REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fixed_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plan_periods(id),
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    frequency TEXT DEFAULT 'monthly',
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plan_periods(id),
    name TEXT NOT NULL,
    balance REAL,
    apr REAL,
    min_payment REAL,
    maturity_date TEXT,
    status TEXT DEFAULT 'active',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS planned_paychecks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plan_periods(id),
    pay_date TEXT NOT NULL,
    net_amount REAL NOT NULL,
    alloc_rent REAL,
    alloc_bills REAL,
    alloc_efund REAL,
    alloc_roth_ira REAL,
    alloc_spending REAL,
    alloc_buffer REAL,
    is_bonus_check INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS actual_paychecks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    planned_id INTEGER NOT NULL REFERENCES planned_paychecks(id),
    received_date TEXT,
    net_amount REAL,
    rent_done INTEGER DEFAULT 0,
    efund_done INTEGER DEFAULT 0,
    roth_done INTEGER DEFAULT 0,
    spending_done INTEGER DEFAULT 0,
    notes TEXT,
    logged_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id INTEGER REFERENCES import_batches(id),
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT,
    category TEXT,
    parent_category TEXT,
    excluded TEXT DEFAULT 'false',
    tags TEXT,
    type TEXT,
    account TEXT,
    account_mask TEXT,
    note TEXT,
    recurring TEXT,
    budget_category TEXT,
    flagged INTEGER DEFAULT 0,
    flag_reason TEXT,
    UNIQUE(date, name, amount, account)
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    imported_at TEXT DEFAULT (datetime('now')),
    row_count INTEGER,
    new_count INTEGER,
    skipped_count INTEGER,
    flagged_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS budget_category_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_category TEXT NOT NULL,
    bank_parent_category TEXT,
    plan_category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flag_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    match_field TEXT DEFAULT 'name',
    flag_reason TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);
