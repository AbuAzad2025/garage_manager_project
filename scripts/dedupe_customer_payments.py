import sys
import os
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

import sqlite3


@dataclass
class DuplicateGroup:
    check_number: str
    check_bank: str
    amount: float
    currency: str
    date_key: str
    payment_ids: List[int]


def _pick_keep_id(conn: sqlite3.Connection, payment_ids: List[int]) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM payments WHERE id IN (%s) AND UPPER(status)='COMPLETED' ORDER BY id ASC" % ",".join(str(i) for i in payment_ids)
    )
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute(
        "SELECT id FROM payments WHERE id IN (%s) AND COALESCE(receipt_number,'')<>'' ORDER BY id ASC" % ",".join(str(i) for i in payment_ids)
    )
    row = cur.fetchone()
    if row:
        return int(row[0])
    return sorted(payment_ids)[0]


def _group_duplicates(conn: sqlite3.Connection, customer_id: int) -> List[DuplicateGroup]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 
          COALESCE(check_number,''), COALESCE(check_bank,''), 
          CAST(total_amount AS REAL), UPPER(COALESCE(currency,'ILS')),
          DATE(payment_date), GROUP_CONCAT(id)
        FROM payments
        WHERE customer_id = ?
          AND UPPER(method) = 'CHEQUE'
          AND UPPER(direction) = 'IN'
          AND COALESCE(check_number,'') <> ''
        GROUP BY check_number, check_bank, total_amount, currency, DATE(payment_date)
        HAVING COUNT(*) > 1
        """,
        (customer_id,)
    )
    dups: List[DuplicateGroup] = []
    for cn, bank, amt, cur, dt, ids in cur.fetchall():
        id_list = [int(x) for x in str(ids).split(',') if x]
        dups.append(DuplicateGroup(str(cn), str(bank), float(amt or 0), str(cur), str(dt or ''), sorted(id_list)))
    return dups


def _reassign_or_delete_checks(conn: sqlite3.Connection, keep_id: int, delete_id: int):
    cur = conn.cursor()
    cur.execute("SELECT check_number, check_bank, CAST(amount AS REAL) FROM checks WHERE payment_id = ?", (keep_id,))
    keep_map = {(str(r[0] or ''), str(r[1] or ''), float(r[2] or 0)) for r in cur.fetchall()}

    cur.execute("SELECT id, check_number, check_bank, CAST(amount AS REAL) FROM checks WHERE payment_id = ?", (delete_id,))
    del_rows = cur.fetchall()
    moved, removed = 0, 0
    for cid, cn, bank, amt in del_rows:
        ident = (str(cn or ''), str(bank or ''), float(amt or 0))
        if ident in keep_map:
            cur.execute("DELETE FROM checks WHERE id = ?", (cid,))
            removed += 1
        else:
            cur.execute("UPDATE checks SET payment_id = ? WHERE id = ?", (keep_id, cid))
            moved += 1
    return moved, removed


def _delete_gl_for_payment(conn: sqlite3.Connection, payment_id: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id FROM gl_batches WHERE source_type = 'PAYMENT' AND source_id = ?", (payment_id,))
    batch_ids = [int(r[0]) for r in cur.fetchall()]
    for bid in batch_ids:
        cur.execute("DELETE FROM gl_entries WHERE batch_id = ?", (bid,))
        cur.execute("DELETE FROM gl_batches WHERE id = ?", (bid,))
    return len(batch_ids)


def dedupe_customer(customer_name: Optional[str] = None, customer_id: Optional[int] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])

        print(f"🔎 العميل المستهدف: #{customer_id}")

        dups = _group_duplicates(conn, customer_id)
        total_deleted = 0
        total_gl_deleted = 0
        total_checks_moved = 0
        total_checks_removed = 0

        if dups:
            print(f"⚠️ تم العثور على {len(dups)} مجموعة مكررة")
            for grp in dups:
                keep_id = _pick_keep_id(conn, grp.payment_ids)
                delete_ids = [pid for pid in grp.payment_ids if pid != keep_id]
                print(
                    f"→ شيك #{grp.check_number} - {grp.check_bank} - {grp.amount:.2f} {grp.currency} - تاريخ {grp.date_key}: إبقاء PMT-{keep_id}, حذف {delete_ids}"
                )

                for del_id in delete_ids:
                    moved, removed = _reassign_or_delete_checks(conn, keep_id, del_id)
                    total_checks_moved += moved
                    total_checks_removed += removed

                    gl_deleted = _delete_gl_for_payment(conn, del_id)
                    total_gl_deleted += gl_deleted

                    cur.execute("DELETE FROM payment_splits WHERE payment_id = ?", (del_id,))
                    cur.execute("DELETE FROM payments WHERE id = ?", (del_id,))
                    total_deleted += 1
        else:
            print("✅ لا يوجد مجموعات دفعات مكررة مبنية على رقم الشيك")

        # Secondary pass: remove independent checks that duplicate existing payment cheques for this customer
        cur.execute(
            """
            SELECT COALESCE(check_number,''), COALESCE(check_bank,''), CAST(total_amount AS REAL)
            FROM payments
            WHERE customer_id = ? AND UPPER(method)='CHEQUE' AND UPPER(direction)='IN' AND COALESCE(check_number,'')<>''
            """,
            (customer_id,)
        )
        pay_keys = {(str(r[0]), str(r[1]), float(r[2] or 0)) for r in cur.fetchall()}
        if pay_keys:
            placeholders = ",".join(["?"] * len({k[0] for k in pay_keys}))
            check_numbers = list({k[0] for k in pay_keys})
            # Fetch independent checks for the customer that share check_number; then filter by bank/amount/currency/date
            cur.execute(
                f"SELECT id, COALESCE(check_number,''), COALESCE(check_bank,''), CAST(amount AS REAL) FROM checks WHERE direction='IN' AND customer_id = ? AND COALESCE(check_number,'') IN ({placeholders})",
                (customer_id, *check_numbers)
            )
            candidates = cur.fetchall()
            to_delete_checks = []
            for cid, cn, bank, amt in candidates:
                key = (str(cn), str(bank), float(amt or 0))
                if key in pay_keys:
                    to_delete_checks.append(int(cid))
            for cid in to_delete_checks:
                cur.execute("DELETE FROM checks WHERE id = ?", (cid,))
            total_checks_removed += len(to_delete_checks)

        conn.commit()

        print("=== الملخص ===")
        print(f"🧾 دفعات محذوفة: {total_deleted}")
        print(f"📘 قيود دفتر محذوفة (GLBatch): {total_gl_deleted}")
        print(f"🔁 شيكات نُقلت: {total_checks_moved}")
        print(f"🗑️ شيكات مُزالة لكونها مكررة: {total_checks_removed}")
        print("✅ اكتمل التنظيف بأمان")
        return 0
    finally:
        conn.close()


def dedupe_by_checks(customer_name: Optional[str] = None, customer_id: Optional[int] = None, check_numbers: Optional[List[str]] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])

        print(f"🔎 العميل المستهدف: #{customer_id} — تنفيذ تنظيف موجه برقم الشيك")

        total_deleted = 0
        total_gl_deleted = 0
        total_checks_moved = 0
        total_checks_removed = 0

        for cn in (check_numbers or []):
            cur.execute(
                """
                SELECT id FROM payments
                WHERE customer_id = ? AND UPPER(method)='CHEQUE' AND UPPER(direction)='IN' AND COALESCE(check_number,'') = ?
                ORDER BY id ASC
                """,
                (customer_id, cn)
            )
            ids = [int(r[0]) for r in cur.fetchall()]
            if len(ids) <= 1:
                continue
            keep_id = _pick_keep_id(conn, ids)
            delete_ids = [pid for pid in ids if pid != keep_id]
            print(f"→ شيك #{cn}: إبقاء PMT-{keep_id}, حذف {delete_ids}")
            for del_id in delete_ids:
                moved, removed = _reassign_or_delete_checks(conn, keep_id, del_id)
                total_checks_moved += moved
                total_checks_removed += removed
                gl_deleted = _delete_gl_for_payment(conn, del_id)
                total_gl_deleted += gl_deleted
                cur.execute("DELETE FROM payment_splits WHERE payment_id = ?", (del_id,))
                cur.execute("DELETE FROM payments WHERE id = ?", (del_id,))
                total_deleted += 1

            # Remove independent checks matching this number for the same customer if duplicating
            cur.execute(
                "SELECT id, COALESCE(check_bank,''), CAST(amount AS REAL) FROM checks WHERE direction='IN' AND customer_id = ? AND COALESCE(check_number,'') = ?",
                (customer_id, cn)
            )
            indep = cur.fetchall()
            # Get the kept payment's bank/amount
            cur.execute("SELECT COALESCE(check_bank,''), CAST(total_amount AS REAL) FROM payments WHERE id = ?", (keep_id,))
            kp = cur.fetchone()
            if kp:
                k_bank, k_amt = str(kp[0]), float(kp[1] or 0)
                for cid, bank, amt in indep:
                    if str(bank) == k_bank and float(amt or 0) == k_amt:
                        cur.execute("DELETE FROM checks WHERE id = ?", (int(cid),))
                        total_checks_removed += 1

        conn.commit()
        print("=== الملخص (by-checks) ===")
        print(f"🧾 دفعات محذوفة: {total_deleted}")
        print(f"📘 قيود دفتر محذوفة (GLBatch): {total_gl_deleted}")
        print(f"🔁 شيكات نُقلت: {total_checks_moved}")
        print(f"🗑️ شيكات مُزالة لكونها مكررة: {total_checks_removed}")
        print("✅ اكتمل التنظيف بأمان")
        return 0
    finally:
        conn.close()


def dedupe_by_date_amount(customer_name: Optional[str] = None, customer_id: Optional[int] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])

        print(f"🔎 العميل المستهدف: #{customer_id} — تنظيف حسب التاريخ والمبلغ")

        cur.execute(
            """
            SELECT DATE(payment_date), CAST(total_amount AS REAL), GROUP_CONCAT(id)
            FROM payments
            WHERE customer_id = ? AND UPPER(direction)='IN'
            GROUP BY DATE(payment_date), CAST(total_amount AS REAL)
            HAVING COUNT(*) > 1
            """,
            (customer_id,)
        )
        groups = cur.fetchall()

        total_deleted = 0
        total_gl_deleted = 0
        total_checks_moved = 0
        total_checks_removed = 0

        for dp, amt, ids_csv in groups:
            ids = [int(x) for x in str(ids_csv).split(',') if x]
            if len(ids) <= 1:
                continue
            keep_id = _pick_keep_id(conn, ids)
            delete_ids = [pid for pid in ids if pid != keep_id]
            print(f"→ تاريخ {dp} — مبلغ {float(amt or 0):.2f}: إبقاء PMT-{keep_id}, حذف {delete_ids}")
            for del_id in delete_ids:
                moved, removed = _reassign_or_delete_checks(conn, keep_id, del_id)
                total_checks_moved += moved
                total_checks_removed += removed
                gl_deleted = _delete_gl_for_payment(conn, del_id)
                total_gl_deleted += gl_deleted
                cur.execute("DELETE FROM payment_splits WHERE payment_id = ?", (del_id,))
                cur.execute("DELETE FROM payments WHERE id = ?", (del_id,))
                total_deleted += 1

            # حذف شيكات مستقلة بنفس التاريخ والمبلغ لتفادي التكرار في الكشف
            cur.execute(
                "SELECT id FROM checks WHERE direction='IN' AND customer_id = ? AND DATE(check_date) = ? AND CAST(amount AS REAL) = ?",
                (customer_id, dp, float(amt or 0))
            )
            indep_ids = [int(r[0]) for r in cur.fetchall()]
            for cid in indep_ids:
                cur.execute("DELETE FROM checks WHERE id = ?", (cid,))
            total_checks_removed += len(indep_ids)

        conn.commit()
        print("=== الملخص (by-date-amount) ===")
        print(f"🧾 دفعات محذوفة: {total_deleted}")
        print(f"📘 قيود دفتر محذوفة (GLBatch): {total_gl_deleted}")
        print(f"🔁 شيكات نُقلت: {total_checks_moved}")
        print(f"🗑️ شيكات مُزالة لكونها مكررة: {total_checks_removed}")
        print("✅ اكتمل التنظيف بأمان")
        return 0
    finally:
        conn.close()

def scan_all_duplicates():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.customer_id, COALESCE(c.name,''), COALESCE(p.check_number,''), COALESCE(p.check_bank,''),
                   CAST(p.total_amount AS REAL), UPPER(COALESCE(p.currency,'ILS')), DATE(p.payment_date),
                   GROUP_CONCAT(p.id), COUNT(*)
            FROM payments p
            LEFT JOIN customers c ON c.id = p.customer_id
            WHERE UPPER(p.method)='CHEQUE' AND UPPER(p.direction)='IN' AND COALESCE(p.check_number,'')<>''
            GROUP BY p.customer_id, c.name, p.check_number, p.check_bank, p.total_amount, p.currency, DATE(p.payment_date)
            HAVING COUNT(*)>1
            ORDER BY c.name, p.check_number
            """
        )
        rows = cur.fetchall()
        if not rows:
            print("✅ لا يوجد مجموعات دفعات شيكات مكررة في قاعدة البيانات الحالية")
            return 0
        print(f"⚠️ تم العثور على {len(rows)} مجموعة مكررة عبر النظام:")
        for cid, cname, cn, bank, amt, curcy, dt, ids_csv, cnt in rows:
            print(f" - عميل: {cname} (#{cid}) | شيك #{cn} - {bank} - {amt:.2f} {curcy} | تاريخ {dt} | عدد: {cnt} | دفعات: {ids_csv}")
        return len(rows)
    finally:
        conn.close()


def list_customer_payments(customer_name: Optional[str] = None, customer_id: Optional[int] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])
        print(f"📄 قائمة دفعات العميل #{customer_id}")
        cur.execute(
            """
            SELECT p.id, DATE(p.payment_date), CAST(p.total_amount AS REAL), UPPER(COALESCE(p.method,'UNKNOWN')),
                   UPPER(COALESCE(p.status,'UNKNOWN')),
                   COALESCE(p.check_number,''), COALESCE(p.check_bank,''),
                   COALESCE(c.check_number,''), COALESCE(c.check_bank,''), CAST(c.amount AS REAL)
            FROM payments p
            LEFT JOIN checks c ON c.payment_id = p.id
            WHERE p.customer_id = ? AND UPPER(p.direction)='IN'
            ORDER BY p.payment_date ASC, p.id ASC
            """,
            (customer_id,)
        )
        rows = cur.fetchall()
        for r in rows:
            pid, dt, amt, method, status, p_cn, p_bank, c_cn, c_bank, c_amt = r
            cn = c_cn or p_cn
            bank = c_bank or p_bank
            camt = c_amt if c_amt is not None else None
            print(f" - [{dt}] PMT-{pid} | amount={amt:.2f} | method={method} | status={status} | check={cn or '-'} | bank={bank or '-'} | check_amount={camt if camt is not None else '-'}")
        return 0
    finally:
        conn.close()


def list_customer_checks(customer_name: Optional[str] = None, customer_id: Optional[int] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])
        print(f"📄 قائمة شيكات العميل #{customer_id}")
        cur.execute(
            """
            SELECT id, DATE(check_date), DATE(check_due_date), COALESCE(check_number,''), COALESCE(check_bank,''),
                   CAST(amount AS REAL), UPPER(COALESCE(status,'PENDING')),
                   COALESCE(payment_id,''), COALESCE(currency,'ILS')
            FROM checks
            WHERE direction='IN' AND (customer_id = ? OR payment_id IN (SELECT id FROM payments WHERE customer_id = ?))
            ORDER BY check_date ASC, id ASC
            """,
            (customer_id, customer_id)
        )
        rows = cur.fetchall()
        for r in rows:
            cid, cdate, due, cn, bank, amt, status, pid, curcy = r
            print(f" - [{cdate}] CHK-{cid} | due={due or '-'} | {cn} - {bank} | amount={amt:.2f} {curcy} | status={status} | payment_id={pid or '-'}")
        return 0
    finally:
        conn.close()

def dedupe_by_joined_checks(customer_name: Optional[str] = None, customer_id: Optional[int] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])

        print(f"🔎 العميل المستهدف: #{customer_id} — تنظيف دفعات مكررة عبر join للشيكات")

        cur.execute(
            """
            SELECT DATE(p.payment_date), CAST(p.total_amount AS REAL), COALESCE(c.check_number, p.check_number, ''), COALESCE(c.check_bank, p.check_bank, ''), GROUP_CONCAT(p.id)
            FROM payments p
            LEFT JOIN checks c ON c.payment_id = p.id
            WHERE p.customer_id = ? AND UPPER(p.direction)='IN'
            GROUP BY DATE(p.payment_date), CAST(p.total_amount AS REAL), COALESCE(c.check_number, p.check_number, ''), COALESCE(c.check_bank, p.check_bank, '')
            HAVING COUNT(*) > 1
            """,
            (customer_id,)
        )
        groups = cur.fetchall()
        total_deleted = 0
        total_gl_deleted = 0
        total_checks_moved = 0
        total_checks_removed = 0

        for dt, amt, cn, bank, ids_csv in groups:
            ids = [int(x) for x in str(ids_csv).split(',') if x]
            keep_id = _pick_keep_id(conn, ids)
            delete_ids = [pid for pid in ids if pid != keep_id]
            print(f"→ [{dt}] amount={float(amt or 0):.2f} check={cn or '-'} bank={bank or '-'}: إبقاء PMT-{keep_id}, حذف {delete_ids}")
            for del_id in delete_ids:
                moved, removed = _reassign_or_delete_checks(conn, keep_id, del_id)
                total_checks_moved += moved
                total_checks_removed += removed
                gl_deleted = _delete_gl_for_payment(conn, del_id)
                total_gl_deleted += gl_deleted
                cur.execute("DELETE FROM payment_splits WHERE payment_id = ?", (del_id,))
                cur.execute("DELETE FROM payments WHERE id = ?", (del_id,))
                total_deleted += 1

        conn.commit()
        print("=== الملخص (joined-checks) ===")
        print(f"🧾 دفعات محذوفة: {total_deleted}")
        print(f"📘 قيود دفتر محذوفة (GLBatch): {total_gl_deleted}")
        print(f"🔁 شيكات نُقلت: {total_checks_moved}")
        print(f"🗑️ شيكات مُزالة لكونها مكررة: {total_checks_removed}")
        print("✅ اكتمل التنظيف بأمان")
        return 0
    finally:
        conn.close()


def delete_independent_checks(customer_name: Optional[str] = None, customer_id: Optional[int] = None, check_numbers: Optional[List[str]] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])
        print(f"🗑️ حذف شيكات مستقلة (غير مرتبطة بمدفوعات) للعميل #{customer_id}")
        if check_numbers:
            placeholders = ",".join(["?"] * len(check_numbers))
            cur.execute(
                f"SELECT id FROM checks WHERE direction='IN' AND customer_id = ? AND payment_id IS NULL AND COALESCE(check_number,'') IN ({placeholders})",
                (customer_id, *check_numbers)
            )
        else:
            cur.execute(
                "SELECT id FROM checks WHERE direction='IN' AND customer_id = ? AND payment_id IS NULL",
                (customer_id,)
            )
        ids = [int(r[0]) for r in cur.fetchall()]
        for cid in ids:
            cur.execute("DELETE FROM checks WHERE id = ?", (cid,))
        conn.commit()
        print(f"✅ تم حذف {len(ids)} شيك مستقل")
        return 0
    finally:
        conn.close()

def dedupe_cash_keep_latest(customer_name: Optional[str] = None, customer_id: Optional[int] = None, amount: Optional[float] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])
        params = [customer_id]
        q = "SELECT id, DATE(payment_date) AS d, CAST(total_amount AS REAL) AS a FROM payments WHERE customer_id = ? AND UPPER(direction)='IN' AND UPPER(method)='CASH'"
        if amount is not None:
            q += " AND CAST(total_amount AS REAL) = ?"
            params.append(float(amount))
        q += " ORDER BY payment_date DESC, id DESC"
        cur.execute(q, tuple(params))
        rows = cur.fetchall()
        by_key = {}
        for pid, dt, amt in rows:
            key = (str(dt), float(amt or 0))
            by_key.setdefault(key, []).append(int(pid))
        total_deleted = 0
        total_gl_deleted = 0
        for key, ids in by_key.items():
            if len(ids) <= 1:
                continue
            keep_id = ids[0]
            del_ids = ids[1:]
            print(f"→ [{key[0]}] amount={key[1]:.2f}: إبقاء PMT-{keep_id}, حذف {del_ids}")
            for did in del_ids:
                cur.execute("DELETE FROM payment_splits WHERE payment_id = ?", (did,))
                cur.execute("SELECT id FROM gl_batches WHERE source_type = 'PAYMENT' AND source_id = ?", (did,))
                bids = [int(r[0]) for r in cur.fetchall()]
                for bid in bids:
                    cur.execute("DELETE FROM gl_entries WHERE batch_id = ?", (bid,))
                    cur.execute("DELETE FROM gl_batches WHERE id = ?", (bid,))
                total_gl_deleted += len(bids)
                cur.execute("DELETE FROM payments WHERE id = ?", (did,))
                total_deleted += 1
        conn.commit()
        print("=== الملخص (cash-keep-latest) ===")
        print(f"🧾 دفعات محذوفة: {total_deleted}")
        print(f"📘 قيود دفتر محذوفة (GLBatch): {total_gl_deleted}")
        print("✅ اكتمل التنظيف بأمان")
        return 0
    finally:
        conn.close()

def delete_payment_id(payment_id: int):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM payments WHERE id = ?", (payment_id,))
        row = cur.fetchone()
        if not row:
            print(f"لا يوجد دفعة برقم {payment_id}")
            return 1
        cur.execute("DELETE FROM payment_splits WHERE payment_id = ?", (payment_id,))
        cur.execute("SELECT id FROM gl_batches WHERE source_type = 'PAYMENT' AND source_id = ?", (payment_id,))
        bids = [int(r[0]) for r in cur.fetchall()]
        for bid in bids:
            cur.execute("DELETE FROM gl_entries WHERE batch_id = ?", (bid,))
            cur.execute("DELETE FROM gl_batches WHERE id = ?", (bid,))
        cur.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
        conn.commit()
        print(f"تم حذف الدفعة {payment_id} وإزالة {len(bids)} قيود دفتر مرتبطة")
        return 0
    finally:
        conn.close()

def add_cheque_payment(customer_name: str, amount: float, payment_date: str, check_number: str, check_bank: str, currency: str = 'ILS', status: str = 'COMPLETED'):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
        row = cur.fetchone()
        if not row:
            print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
            return 2
        customer_id = int(row[0])

        cols = [r[1] for r in cur.execute("PRAGMA table_info(payments)").fetchall()]
        data = {
            'customer_id': customer_id,
            'payment_date': payment_date,
            'total_amount': float(amount),
            'method': 'CHEQUE',
            'status': status,
            'direction': 'IN',
            'check_number': check_number,
            'check_bank': check_bank,
            'currency': currency,
        }
        # supply common timestamps if present
        if 'created_at' in cols:
            data['created_at'] = sqlite3.Timestamp.fromisoformat(payment_date + " 00:00:00") if hasattr(sqlite3, 'Timestamp') else payment_date + " 00:00:00"
        if 'updated_at' in cols:
            data['updated_at'] = data.get('created_at', payment_date + " 00:00:00")

        insert_cols = [k for k in data.keys() if k in cols]
        placeholders = ",".join(["?"] * len(insert_cols))
        sql = f"INSERT INTO payments ({','.join(insert_cols)}) VALUES ({placeholders})"
        cur.execute(sql, tuple(data[c] for c in insert_cols))
        new_id = cur.lastrowid
        conn.commit()
        print(f"✅ تمت إضافة دفعة شيك جديدة ID={new_id} للعميل #{customer_id} بتاريخ {payment_date} بمبلغ {amount:.2f}")
        return 0
    finally:
        conn.close()

def normalize_payment_methods():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        allowed = {"cash","bank","card","cheque","online"}
        cur.execute("SELECT id, method FROM payments WHERE method IS NOT NULL")
        rows = cur.fetchall()
        updated = 0
        for pid, m in rows:
            mm = (m or "").strip()
            if not mm:
                continue
            low = mm.lower()
            if low == "check":
                low = "cheque"
            if low not in allowed:
                # try mapping common variants
                if mm.upper() in ("CHEQUE","CHECK"): low = "cheque"
                elif mm.upper() in ("CASH"): low = "cash"
                elif mm.upper() in ("BANK","TRANSFER","WIRE"): low = "bank"
                elif mm.upper() in ("CARD","CREDIT","DEBIT"): low = "card"
                elif mm.upper() in ("ONLINE","WEB","PAYMENT"): low = "online"
                else:
                    continue
            if mm != low:
                cur.execute("UPDATE payments SET method = ? WHERE id = ?", (low, int(pid)))
                updated += 1
        conn.commit()
        print(f"✅ تم تطبيع طرق الدفع: {updated} صف محدث")
        return 0
    finally:
        conn.close()

def list_customer_sales(customer_name: Optional[str] = None, customer_id: Optional[int] = None, on_date: Optional[str] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])
        params = [customer_id]
        sql = "SELECT id, DATETIME(sale_date), CAST(total_amount AS REAL), currency FROM sales WHERE customer_id = ?"
        if on_date:
            sql += " AND DATE(sale_date) = ?"
            params.append(on_date)
        sql += " ORDER BY sale_date ASC, id ASC"
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        print(f"📄 قائمة مبيعات العميل #{customer_id}{(' بتاريخ '+on_date) if on_date else ''}")
        for sid, sdt, total, curr in rows:
            cur.execute("SELECT SUM(CAST(quantity AS REAL) * CAST(unit_price AS REAL)) FROM sale_lines WHERE sale_id = ?", (sid,))
            lines_sum = float(cur.fetchone()[0] or 0)
            print(f" - [{sdt}] SALE-{sid} | total={float(total or 0):.2f} {curr} | lines_sum={lines_sum:.2f}")
        return 0
    finally:
        conn.close()

def reconcile_sales_by_date(customer_name: Optional[str] = None, customer_id: Optional[int] = None, on_date: Optional[str] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])
        params = [customer_id]
        sql = "SELECT id, DATE(sale_date), CAST(total_amount AS REAL), currency FROM sales WHERE customer_id = ?"
        if on_date:
            sql += " AND DATE(sale_date) = ?"
            params.append(on_date)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        total_adjusted = 0.0
        count = 0
        for sid, sdate, total, curr in rows:
            cur.execute("SELECT SUM(CAST(quantity AS REAL) * CAST(unit_price AS REAL)) FROM sale_lines WHERE sale_id = ?", (sid,))
            lines_sum = float(cur.fetchone()[0] or 0)
            prev = float(total or 0)
            if abs(lines_sum - prev) > 0.0001:
                cur.execute("UPDATE sales SET total_amount = ? WHERE id = ?", (lines_sum, sid))
                total_adjusted += (lines_sum - prev)
                count += 1
                print(f"→ [{sdate}] SALE-{sid}: total {prev:.2f} -> {lines_sum:.2f} ({curr})")
        conn.commit()
        print(f"✅ تمت مطابقة الإجماليات مع البنود: {count} فاتورة تم تعديلها | الفرق الإجمالي = {total_adjusted:.2f}")
        return 0
    finally:
        conn.close()

def reconcile_all_sales():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM sales")
        sale_ids = [int(r[0]) for r in cur.fetchall()]
        total_adjusted = 0.0
        count = 0
        for sid in sale_ids:
            cur.execute("SELECT tax_rate, shipping_cost, discount_total FROM sales WHERE id = ?", (sid,))
            row = cur.fetchone()
            tr = float(row[0] or 0)
            shipping = float(row[1] or 0)
            disc = float(row[2] or 0)
            cur.execute(
                """
                SELECT COALESCE(SUM((quantity * unit_price) * (1 - (COALESCE(discount_rate,0)/100.0))), 0.0)
                FROM sale_lines WHERE sale_id = ?
                """,
                (sid,)
            )
            subtotal = float(cur.fetchone()[0] or 0)
            base = subtotal - disc
            if base < 0:
                base = 0.0
            tax = (base + shipping) * (tr / 100.0)
            new_total = base + shipping + tax
            if new_total < 0:
                new_total = 0.0
            cur.execute("SELECT CAST(total_amount AS REAL) FROM sales WHERE id = ?", (sid,))
            prev_total = float(cur.fetchone()[0] or 0)
            if abs(new_total - prev_total) > 0.0001:
                cur.execute("UPDATE sales SET total_amount = ?, balance_due = (CAST(? AS REAL) - CAST(COALESCE(total_paid,0) AS REAL)) WHERE id = ?", (new_total, new_total, sid))
                total_adjusted += (new_total - prev_total)
                count += 1
        conn.commit()
        print(f"✅ تمت مطابقة كل المبيعات مع الخصومات والضرائب والشحن: {count} صف معدل | الفرق الإجمالي = {total_adjusted:.2f}")
        return 0
    finally:
        conn.close()

def reconcile_all_payments():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM payments")
        ids = [int(r[0]) for r in cur.fetchall()]
        count = 0
        total_adjusted = 0.0
        for pid in ids:
            cur.execute("SELECT COALESCE(SUM(CAST(amount AS REAL)), 0.0) FROM payment_splits WHERE payment_id = ?", (pid,))
            splits_sum = float(cur.fetchone()[0] or 0)
            if splits_sum > 0:
                cur.execute("SELECT CAST(total_amount AS REAL) FROM payments WHERE id = ?", (pid,))
                prev = float(cur.fetchone()[0] or 0)
                if abs(prev - splits_sum) > 0.0001:
                    cur.execute("UPDATE payments SET total_amount = ? WHERE id = ?", (splits_sum, pid))
                    total_adjusted += (splits_sum - prev)
                    count += 1
        conn.commit()
        print(f"✅ تمت مطابقة كل الدفعات مع تفاصيلها: {count} دفعة معدّلة | الفرق الإجمالي = {total_adjusted:.2f}")
        return 0
    finally:
        conn.close()

def reconcile_sales_for_customer(customer_name: Optional[str] = None, customer_id: Optional[int] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])
        cur.execute("SELECT id, CAST(tax_rate AS REAL), CAST(shipping_cost AS REAL), CAST(discount_total AS REAL) FROM sales WHERE customer_id = ?", (customer_id,))
        sale_rows = cur.fetchall()
        total_adjusted = 0.0
        count = 0
        for sid, tr, shipping, disc in sale_rows:
            cur.execute(
                """
                SELECT COALESCE(SUM((quantity * unit_price) * (1 - (COALESCE(discount_rate,0)/100.0))), 0.0)
                FROM sale_lines WHERE sale_id = ?
                """,
                (sid,)
            )
            subtotal = float(cur.fetchone()[0] or 0)
            base = subtotal - float(disc or 0)
            if base < 0:
                base = 0.0
            tax = (base + float(shipping or 0)) * (float(tr or 0) / 100.0)
            new_total = base + float(shipping or 0) + tax
            if new_total < 0:
                new_total = 0.0
            cur.execute("SELECT CAST(total_amount AS REAL) FROM sales WHERE id = ?", (sid,))
            prev_total = float(cur.fetchone()[0] or 0)
            if abs(new_total - prev_total) > 0.0001:
                cur.execute("UPDATE sales SET total_amount = ?, balance_due = (CAST(? AS REAL) - CAST(COALESCE(total_paid,0) AS REAL)) WHERE id = ?", (new_total, new_total, sid))
                total_adjusted += (new_total - prev_total)
                count += 1
        conn.commit()
        print(f"✅ تمت مطابقة مبيعات العميل #{customer_id}: {count} صف معدل | الفرق الإجمالي = {total_adjusted:.2f}")
        return 0
    finally:
        conn.close()

def reconcile_payments_for_customer(customer_name: Optional[str] = None, customer_id: Optional[int] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        if customer_id is None:
            cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
            row = cur.fetchone()
            if not row:
                print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
                return 2
            customer_id = int(row[0])
        cur.execute("SELECT id FROM payments WHERE customer_id = ?", (customer_id,))
        ids = [int(r[0]) for r in cur.fetchall()]
        count = 0
        total_adjusted = 0.0
        for pid in ids:
            cur.execute("SELECT COALESCE(SUM(CAST(amount AS REAL)), 0.0) FROM payment_splits WHERE payment_id = ?", (pid,))
            splits_sum = float(cur.fetchone()[0] or 0)
            if splits_sum > 0:
                cur.execute("SELECT CAST(total_amount AS REAL) FROM payments WHERE id = ?", (pid,))
                prev = float(cur.fetchone()[0] or 0)
                if abs(prev - splits_sum) > 0.0001:
                    cur.execute("UPDATE payments SET total_amount = ? WHERE id = ?", (splits_sum, pid))
                    total_adjusted += (splits_sum - prev)
                    count += 1
        conn.commit()
        print(f"✅ تمت مطابقة دفعات العميل #{customer_id}: {count} دفعة معدّلة | الفرق الإجمالي = {total_adjusted:.2f}")
        return 0
    finally:
        conn.close()

def remove_bounced_check_payment(customer_name: str, amount: float, payment_date: str, check_number: Optional[str] = None):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM customers WHERE name = ? COLLATE NOCASE LIMIT 1", (customer_name.strip(),))
        row = cur.fetchone()
        if not row:
            print(f"❌ لم يتم العثور على عميل بالاسم: {customer_name}")
            return 2
        customer_id = int(row[0])

        print(f"🔎 إزالة دفعة شيك للعميل #{customer_id} بتاريخ {payment_date} بمبلغ {float(amount):.2f}")

        params = [customer_id, float(amount), payment_date]
        cur.execute(
            """
            SELECT p.id
            FROM payments p
            WHERE p.customer_id = ?
              AND UPPER(p.direction) = 'IN'
              AND DATE(p.payment_date) = ?
              AND CAST(p.total_amount AS REAL) = ?
              AND (
                    UPPER(COALESCE(p.method,'')) = 'CHEQUE'
                 OR EXISTS (SELECT 1 FROM payment_splits s WHERE s.payment_id = p.id AND UPPER(COALESCE(s.method,'')) = 'CHEQUE')
              )
            ORDER BY p.id ASC
            """,
            (customer_id, payment_date, float(amount))
        )
        p_rows = [int(r[0]) for r in cur.fetchall()]
        if not p_rows:
            # حاول إيجاد split بالشيك وفق التاريخ والمبلغ
            cur.execute(
                """
                SELECT s.id, p.id
                FROM payment_splits s
                JOIN payments p ON p.id = s.payment_id
                WHERE p.customer_id = ?
                  AND DATE(p.payment_date) = ?
                  AND UPPER(COALESCE(s.method,'')) = 'CHEQUE'
                  AND (
                       CAST(s.amount AS REAL) = ?
                    OR CAST(s.converted_amount AS REAL) = ?
                  )
                ORDER BY s.id ASC
                """,
                (customer_id, payment_date, float(amount), float(amount))
            )
            split_rows = cur.fetchall()
            if not split_rows:
                print("⚠️ لم يتم العثور على دفعة شيك مطابقة للمبلغ والتاريخ")
                return 3
            # احذف الشيكات المرتبطة بالـ split ثم احذف الـ split وعدّل مبلغ الدفعة
            total_checks_deleted = 0
            total_splits_deleted = 0
            total_gl_deleted = 0
            total_payments_deleted = 0
            affected_payments = set()
            for sid, pid in split_rows:
                cur.execute("DELETE FROM checks WHERE reference_number = ? OR reference_number LIKE ?", (f"PMT-SPLIT-{sid}", f"PMT-SPLIT-{sid}-%"))
                total_checks_deleted += cur.rowcount if hasattr(cur, 'rowcount') else 0
                cur.execute("DELETE FROM payment_splits WHERE id = ?", (int(sid),))
                total_splits_deleted += 1
                affected_payments.add(int(pid))
            for pid in affected_payments:
                cur.execute("SELECT COALESCE(SUM(CAST(amount AS REAL)), 0.0) FROM payment_splits WHERE payment_id = ?", (pid,))
                new_total = float(cur.fetchone()[0] or 0)
                cur.execute("UPDATE payments SET total_amount = ? WHERE id = ?", (new_total, pid))
            if check_number:
                cur.execute("DELETE FROM checks WHERE COALESCE(check_number,'') = ? AND (customer_id = ? OR payment_id IN (SELECT id FROM payments WHERE customer_id = ?))", (check_number, customer_id, customer_id))
            conn.commit()
            print("=== الملخص (remove-bounced-check-split) ===")
            print(f"🗑️ شيكات محذوفة: {total_checks_deleted}")
            print(f"🗂️ Splits محذوفة: {total_splits_deleted}")
            print("✅ تم الإزالة من الـ split بنجاح")
            return 0

        target_pids = []
        for pid in p_rows:
            if check_number:
                cur.execute("SELECT 1 FROM checks WHERE payment_id = ? AND COALESCE(check_number,'') = ?", (pid, check_number))
                if cur.fetchone():
                    target_pids.append(pid)
                    continue
                cur.execute("SELECT 1 FROM payments WHERE id = ? AND COALESCE(check_number,'') = ?", (pid, check_number))
                if cur.fetchone():
                    target_pids.append(pid)
            else:
                target_pids.append(pid)

        if not target_pids:
            print("⚠️ لم يتم تحديد دفعة مطابقة برقم الشيك المحدد")
            return 4

        total_checks_deleted = 0
        total_splits_deleted = 0
        total_gl_deleted = 0
        total_payments_deleted = 0

        for pid in target_pids:
            cur.execute("SELECT id FROM payment_splits WHERE payment_id = ?", (pid,))
            split_ids = [int(r[0]) for r in cur.fetchall()]
            for sid in split_ids:
                cur.execute("DELETE FROM checks WHERE reference_number = ? OR reference_number LIKE ?", (f"PMT-SPLIT-{sid}", f"PMT-SPLIT-{sid}-%"))
            cur.execute("DELETE FROM payment_splits WHERE payment_id = ?", (pid,))
            total_splits_deleted += len(split_ids)

            cur.execute("SELECT id FROM checks WHERE payment_id = ?", (pid,))
            chk_ids = [int(r[0]) for r in cur.fetchall()]
            for cid in chk_ids:
                cur.execute("DELETE FROM checks WHERE id = ?", (cid,))
            total_checks_deleted += len(chk_ids)

            if check_number:
                cur.execute("DELETE FROM checks WHERE COALESCE(check_number,'') = ? AND (customer_id = ? OR payment_id IN (SELECT id FROM payments WHERE customer_id = ?))", (check_number, customer_id, customer_id))

            total_gl_deleted += _delete_gl_for_payment(conn, pid)

            cur.execute("DELETE FROM payments WHERE id = ?", (pid,))
            total_payments_deleted += 1

        conn.commit()
        print("=== الملخص (remove-bounced-check-payment) ===")
        print(f"🧾 دفعات محذوفة: {total_payments_deleted}")
        print(f"🗂️ Splits محذوفة: {total_splits_deleted}")
        print(f"🗑️ شيكات محذوفة: {total_checks_deleted}")
        print(f"📘 قيود دفتر محذوفة (GLBatch): {total_gl_deleted}")
        print("✅ تم الإزالة بنجاح")
        return 0
    finally:
        conn.close()
if __name__ == "__main__":
    # Usage:
    # python scripts/dedupe_customer_payments.py "اسم العميل"
    # python scripts/dedupe_customer_payments.py --scan-all
    # python scripts/dedupe_customer_payments.py --by-checks "اسم العميل" 30000107,30000007,30001609,0008
    # python scripts/dedupe_customer_payments.py --by-date-amount "اسم العميل"
    # python scripts/dedupe_customer_payments.py --list "اسم العميل"
    # python scripts/dedupe_customer_payments.py --list-checks "اسم العميل"
    # python scripts/dedupe_customer_payments.py --joined-checks "اسم العميل"
    # python scripts/dedupe_customer_payments.py --delete-independent-checks "اسم العميل" 30000107,30000007,30001609,0008
    # python scripts/dedupe_customer_payments.py --cash-keep-latest "اسم العميل" 2000
    # python scripts/dedupe_customer_payments.py --delete-payment-id 3
    # python scripts/dedupe_customer_payments.py --add-cheque-payment "اسم العميل" 5000 2025-10-26 30000449 "الاستثمار الفلسطيني"
    # python scripts/dedupe_customer_payments.py --normalize-payment-methods
    # python scripts/dedupe_customer_payments.py --list-sales "اسم العميل" [YYYY-MM-DD]
    # python scripts/dedupe_customer_payments.py --reconcile-sales-by-date "اسم العميل" YYYY-MM-DD
    # python scripts/dedupe_customer_payments.py --reconcile-all-sales
    # python scripts/dedupe_customer_payments.py --reconcile-all-payments
    # python scripts/dedupe_customer_payments.py --reconcile-sales-customer "اسم العميل"
    # python scripts/dedupe_customer_payments.py --reconcile-payments-customer "اسم العميل"
    if len(sys.argv) < 2:
        print("استخدم: python scripts/dedupe_customer_payments.py \"اسم العميل\" أو --scan-all أو --by-checks \"اسم العميل\" numbers")
        sys.exit(1)
    if sys.argv[1] == "--scan-all":
        code = scan_all_duplicates()
        sys.exit(0 if isinstance(code, int) and code >= 0 else 1)
    if sys.argv[1] == "--by-checks":
        if len(sys.argv) < 4:
            print("استخدم: --by-checks \"اسم العميل\" رقم1,رقم2,رقم3")
            sys.exit(1)
        name = sys.argv[2]
        raw = sys.argv[3]
        checks = [s.strip() for s in raw.split(',') if s.strip()]
        code = dedupe_by_checks(customer_name=name, check_numbers=checks)
        sys.exit(code)
    if sys.argv[1] == "--by-date-amount":
        if len(sys.argv) < 3:
            print("استخدم: --by-date-amount \"اسم العميل\"")
            sys.exit(1)
        name = sys.argv[2]
        code = dedupe_by_date_amount(customer_name=name)
        sys.exit(code)
    if sys.argv[1] == "--list":
        if len(sys.argv) < 3:
            print("استخدم: --list \"اسم العميل\"")
            sys.exit(1)
        name = sys.argv[2]
        code = list_customer_payments(customer_name=name)
        sys.exit(code)
    if sys.argv[1] == "--list-checks":
        if len(sys.argv) < 3:
            print("استخدم: --list-checks \"اسم العميل\"")
            sys.exit(1)
        name = sys.argv[2]
        code = list_customer_checks(customer_name=name)
        sys.exit(code)
    if sys.argv[1] == "--joined-checks":
        if len(sys.argv) < 3:
            print("استخدم: --joined-checks \"اسم العميل\"")
            sys.exit(1)
        name = sys.argv[2]
        code = dedupe_by_joined_checks(customer_name=name)
        sys.exit(code)
    if sys.argv[1] == "--delete-independent-checks":
        if len(sys.argv) < 3:
            print("استخدم: --delete-independent-checks \"اسم العميل\" [أرقام شيكات مفصولة بفواصل]")
            sys.exit(1)
        name = sys.argv[2]
        checks = []
        if len(sys.argv) >= 4:
            raw = sys.argv[3]
            checks = [s.strip() for s in raw.split(',') if s.strip()]
        code = delete_independent_checks(customer_name=name, check_numbers=checks)
        sys.exit(code)
    if sys.argv[1] == "--cash-keep-latest":
        if len(sys.argv) < 4:
            print("استخدم: --cash-keep-latest \"اسم العميل\" المبلغ")
            sys.exit(1)
        name = sys.argv[2]
        amt = float(sys.argv[3])
        code = dedupe_cash_keep_latest(customer_name=name, amount=amt)
        sys.exit(code)
    if sys.argv[1] == "--delete-payment-id":
        if len(sys.argv) < 3:
            print("استخدم: --delete-payment-id payment_id")
            sys.exit(1)
        pid = int(sys.argv[2])
        code = delete_payment_id(payment_id=pid)
        sys.exit(code)
    if sys.argv[1] == "--add-cheque-payment":
        if len(sys.argv) < 7:
            print("استخدم: --add-cheque-payment \"اسم العميل\" المبلغ التاريخ رقم_الشيك البنك")
            sys.exit(1)
        name = sys.argv[2]
        amt = float(sys.argv[3])
        dt = sys.argv[4]
        cn = sys.argv[5]
        bank = sys.argv[6]
        code = add_cheque_payment(customer_name=name, amount=amt, payment_date=dt, check_number=cn, check_bank=bank)
        sys.exit(code)
    if sys.argv[1] == "--normalize-payment-methods":
        code = normalize_payment_methods()
        sys.exit(code)
    if sys.argv[1] == "--list-sales":
        if len(sys.argv) < 3:
            print("استخدم: --list-sales \"اسم العميل\" [تاريخ]")
            sys.exit(1)
        name = sys.argv[2]
        dt = sys.argv[3] if len(sys.argv) >= 4 else None
        code = list_customer_sales(customer_name=name, on_date=dt)
        sys.exit(code)
    if sys.argv[1] == "--reconcile-sales-by-date":
        if len(sys.argv) < 4:
            print("استخدم: --reconcile-sales-by-date \"اسم العميل\" التاريخ")
            sys.exit(1)
        name = sys.argv[2]
        dt = sys.argv[3]
        code = reconcile_sales_by_date(customer_name=name, on_date=dt)
        sys.exit(code)
    if sys.argv[1] == "--reconcile-all-sales":
        code = reconcile_all_sales()
        sys.exit(code)
    if sys.argv[1] == "--reconcile-all-payments":
        code = reconcile_all_payments()
        sys.exit(code)
    if sys.argv[1] == "--reconcile-sales-customer":
        if len(sys.argv) < 3:
            print("استخدم: --reconcile-sales-customer \"اسم العميل\"")
            sys.exit(1)
        name = sys.argv[2]
        code = reconcile_sales_for_customer(customer_name=name)
        sys.exit(code)
    if sys.argv[1] == "--reconcile-payments-customer":
        if len(sys.argv) < 3:
            print("استخدم: --reconcile-payments-customer \"اسم العميل\"")
            sys.exit(1)
        name = sys.argv[2]
        code = reconcile_payments_for_customer(customer_name=name)
        sys.exit(code)
    if sys.argv[1] == "--remove-bounced-check-payment":
        if len(sys.argv) < 5:
            print("استخدم: --remove-bounced-check-payment \"اسم العميل\" المبلغ التاريخ [رقم_الشيك]")
            sys.exit(1)
        name = sys.argv[2]
        amt = float(sys.argv[3])
        dt = sys.argv[4]
        cn = sys.argv[5] if len(sys.argv) >= 6 else None
        code = remove_bounced_check_payment(customer_name=name, amount=amt, payment_date=dt, check_number=cn)
        sys.exit(code)
    name = sys.argv[1]
    code = dedupe_customer(customer_name=name)
    sys.exit(code)

