"""CSV import pipeline for bank transaction data."""

import csv
import io
import re


# Column name normalization: "parent category" → "parent_category"
COLUMN_MAP = {
    "date": "date",
    "name": "name",
    "amount": "amount",
    "status": "status",
    "category": "category",
    "parent category": "parent_category",
    "excluded": "excluded",
    "tags": "tags",
    "type": "type",
    "account": "account",
    "account mask": "account_mask",
    "note": "note",
    "recurring": "recurring",
}


def import_csv(db, file_stream, filename="upload.csv"):
    """Import transactions from a CSV file stream.

    Returns dict with: total, new, skipped, flagged, batch_id
    """
    # Read and decode
    if isinstance(file_stream, bytes):
        text = file_stream.decode("utf-8-sig")
    elif isinstance(file_stream, str):
        text = file_stream
    else:
        raw = file_stream.read()
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw

    reader = csv.DictReader(io.StringIO(text))

    # Load flag rules
    flag_rules = db.execute(
        "SELECT pattern, match_field, flag_reason FROM flag_rules WHERE is_active = 1"
    ).fetchall()

    # Load category map
    cat_map_rows = db.execute(
        "SELECT bank_category, bank_parent_category, plan_category FROM budget_category_map"
    ).fetchall()
    cat_map = {}
    for row in cat_map_rows:
        key = (row["bank_category"], row["bank_parent_category"])
        cat_map[key] = row["plan_category"]
        # Also index by category alone (parent=None match)
        if row["bank_parent_category"] is None:
            cat_map[(row["bank_category"], None)] = row["plan_category"]

    total = 0
    new = 0
    skipped = 0
    flagged = 0

    # Create batch record
    db.execute(
        "INSERT INTO import_batches (filename, row_count, new_count, skipped_count, flagged_count) VALUES (?, 0, 0, 0, 0)",
        (filename,),
    )
    batch_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    for raw_row in reader:
        total += 1

        # Normalize column names
        row = {}
        for raw_key, value in raw_row.items():
            normalized = COLUMN_MAP.get(raw_key.strip().lower(), raw_key.strip().lower().replace(" ", "_"))
            row[normalized] = value.strip() if value else None

        # Parse amount
        try:
            amount = float(row.get("amount", 0) or 0)
        except (ValueError, TypeError):
            amount = 0

        # Map budget category
        category = row.get("category") or ""
        parent_category = row.get("parent_category") or ""
        budget_cat = _map_category(cat_map, category, parent_category)

        # Check flag rules
        is_flagged = 0
        flag_reason = None
        for rule in flag_rules:
            field_val = row.get(rule["match_field"], "") or ""
            if rule["pattern"].lower() in field_val.lower():
                is_flagged = 1
                flag_reason = rule["flag_reason"]
                break

        # Insert with dedup
        try:
            db.execute(
                """INSERT OR IGNORE INTO transactions
                   (import_batch_id, date, name, amount, status, category, parent_category,
                    excluded, tags, type, account, account_mask, note, recurring,
                    budget_category, flagged, flag_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_id,
                    row.get("date"),
                    row.get("name"),
                    amount,
                    row.get("status"),
                    category or None,
                    parent_category or None,
                    row.get("excluded", "false"),
                    row.get("tags"),
                    row.get("type"),
                    row.get("account"),
                    row.get("account_mask"),
                    row.get("note"),
                    row.get("recurring"),
                    budget_cat,
                    is_flagged,
                    flag_reason,
                ),
            )
            if db.execute("SELECT changes()").fetchone()[0] > 0:
                new += 1
                if is_flagged:
                    flagged += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    # Update batch record
    db.execute(
        "UPDATE import_batches SET row_count=?, new_count=?, skipped_count=?, flagged_count=? WHERE id=?",
        (total, new, skipped, flagged, batch_id),
    )
    db.commit()

    return {
        "total": total,
        "new": new,
        "skipped": skipped,
        "flagged": flagged,
        "batch_id": batch_id,
    }


def _map_category(cat_map, category, parent_category):
    """Look up plan category from bank category. Falls back through several keys."""
    if not category:
        return None
    # Try exact match (category + parent)
    result = cat_map.get((category, parent_category))
    if result:
        return result
    # Try category with None parent
    result = cat_map.get((category, None))
    if result:
        return result
    # Try parent category alone
    if parent_category:
        result = cat_map.get((parent_category, None))
        if result:
            return result
    return None


def preview_csv(file_stream, max_rows=10):
    """Return first N rows for preview before import."""
    if isinstance(file_stream, bytes):
        text = file_stream.decode("utf-8-sig")
    elif isinstance(file_stream, str):
        text = file_stream
    else:
        raw = file_stream.read()
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw

    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for i, raw_row in enumerate(reader):
        if i >= max_rows:
            break
        row = {}
        for raw_key, value in raw_row.items():
            normalized = COLUMN_MAP.get(raw_key.strip().lower(), raw_key.strip().lower().replace(" ", "_"))
            row[normalized] = value.strip() if value else ""
        rows.append(row)

    # Count total
    total = sum(1 for _ in reader) + len(rows)
    return {"rows": rows, "total": total}
