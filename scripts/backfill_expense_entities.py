import argparse
import os
import sys
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import create_app
from extensions import db
from models import Branch, Expense, ExpenseType
from routes.expenses import LegacyEntityResolver

AUTO_TAG = "[افتراضي]"


def _default_branch_id():
    branch = Branch.query.order_by(Branch.id.asc()).first()
    return branch.id if branch else None


def _default_type_id():
    preferred = ExpenseType.query.filter(ExpenseType.name == "أخرى").first()
    if preferred:
        return preferred.id
    fallback = ExpenseType.query.order_by(ExpenseType.id.asc()).first()
    return fallback.id if fallback else None


def _append_auto_note(expense, message):
    addition = f"{AUTO_TAG} {message}"
    notes = expense.notes or ""
    if notes:
        if AUTO_TAG in notes:
            expense.notes = notes + " | " + addition
        else:
            expense.notes = addition + " | " + notes
    else:
        expense.notes = addition


def apply_guess(expense, guess):
    field = guess["field"]
    entity_id = guess["id"]
    if field == "supplier_id":
        expense.supplier_id = entity_id
    elif field == "partner_id":
        expense.partner_id = entity_id
    elif field == "customer_id":
        expense.customer_id = entity_id
    elif field == "employee_id":
        expense.employee_id = entity_id
    allowed_types = {"SUPPLIER", "EMPLOYEE", "UTILITY", "CUSTOMER", "PARTNER", "OTHER"}
    if guess["type"] in allowed_types:
        expense.payee_type = guess["type"]
    elif not expense.payee_type:
        expense.payee_type = "OTHER"
    expense.payee_entity_id = entity_id
    expense.payee_name = guess["name"]
    return field


def run_backfill(min_length=3, limit=None, commit=False):
    resolver = LegacyEntityResolver(min_length=min_length)
    stats = defaultdict(int)
    misses = Counter()
    query = Expense.query.order_by(Expense.id.asc())
    if limit:
        query = query.limit(limit)
    updated = 0
    branch_id_cache = _default_branch_id()
    type_id_cache = _default_type_id()
    for expense in query.yield_per(200):
        change_fields = []
        has_entity = any(
            getattr(expense, field, None)
            for field in ("supplier_id", "partner_id", "customer_id", "employee_id")
        )
        guess = None
        if not has_entity:
            guess = resolver.guess(expense)
            if guess:
                field_changed = apply_guess(expense, guess)
                change_fields.append(field_changed)
                stats[field_changed] += 1
        if not has_entity and not guess:
            label = (
                expense.payee_name
                or expense.paid_to
                or expense.beneficiary_name
                or expense.disbursed_by
                or ""
            ).strip()
            token = label or ""
            if len(token) >= min_length:
                misses[label or "غير محدد"] += 1
        if not expense.payee_name:
            source_name = (
                expense.beneficiary_name
                or expense.paid_to
                or expense.disbursed_by
                or "جهة غير معروفة"
            )
            expense.payee_name = f"{AUTO_TAG} {source_name}"
            change_fields.append("payee_name")
        if not expense.branch_id and branch_id_cache:
            expense.branch_id = branch_id_cache
            change_fields.append("branch_id")
        if not expense.type_id and type_id_cache:
            expense.type_id = type_id_cache
            change_fields.append("type_id")
        if change_fields:
            updated += 1
            fields_summary = ", ".join(sorted(set(change_fields)))
            _append_auto_note(expense, f"تمت تعبئة الحقول: {fields_summary}")
    if commit:
        db.session.commit()
    else:
        db.session.rollback()
    return updated, stats, misses.most_common(20)


def parse_args():
    parser = argparse.ArgumentParser(description="Backfill expense entities from legacy names")
    parser.add_argument("--commit", action="store_true", help="Persist changes")
    parser.add_argument("--min-length", type=int, default=3, help="Minimum length for matching tokens")
    parser.add_argument("--limit", type=int, help="Limit processed expenses")
    return parser.parse_args()


def main():
    args = parse_args()
    app = create_app()
    with app.app_context():
        updated, stats, misses = run_backfill(
            min_length=args.min_length, limit=args.limit, commit=args.commit
        )
        print(f"Updated expenses: {updated}")
        for field, count in stats.items():
            print(f"{field}: {count}")
        print("Top unmatched names:")
        for name, count in misses:
            print(f"- {name}: {count}")
        if not args.commit:
            print("Dry run only. Use --commit to persist changes.")


if __name__ == "__main__":
    main()

