import csv
import os
import sys
import re
from datetime import datetime


def normalize(s):
    if s is None:
        return ""
    s = str(s).strip()
    return s.upper()


# اسم → ترجمة محاسبية عربية (للاسم)
NAME_TRANSLATIONS = {
    "CASH": "الصندوق",
    "BANK": "البنك",
    "CARD": "تسوية بطاقات",
    "CARD CLEARING": "تسوية بطاقات",
    "ACCOUNTS RECEIVABLE": "ذمم العملاء",
    "AR": "ذمم العملاء",
    "1100_AR": "ذمم العملاء",
    "ACCOUNTS PAYABLE": "ذمم الموردين",
    "AP": "ذمم الموردين",
    "2000_AP": "ذمم الموردين",
    "SALES": "إيرادات المبيعات",
    "SALES REVENUE": "إيرادات المبيعات",
    "SERVICE REVENUE": "إيرادات الخدمات",
    "VAT PAYABLE": "ضريبة قيمة مضافة مستحقة",
    "CHEQUES RECEIVABLE": "شيكات تحت التحصيل",
    "CHEQUES PAYABLE": "شيكات مستحقة الدفع",
    "ADVANCE PAYMENTS": "دفعات مقدمة/عربون",
    "ADVANCE": "دفعات مقدمة/عربون",
    "EXPENSES": "المصروفات",
    "INVENTORY": "المخزون",
    "RETAINED EARNINGS": "أرباح محتجزة",
    "CAPITAL": "رأس المال",
    "PURCHASES": "المشتريات",
    "SHIPPING": "الشحن",
    "HANDLING": "المناولة",
    "OTHER INCOME": "إيرادات أخرى",
}


# نوع/تصنيف → ترجمة محاسبية عربية (للنوع)
TYPE_TRANSLATIONS = {
    "ASSET": "أصل",
    "LIABILITY": "التزام",
    "EQUITY": "حقوق الملكية",
    "REVENUE": "إيراد",
    "EXPENSE": "مصروف",
}


EXAMPLE_BY_NAME = {
    "الصندوق": "قبض نقدي من عميل: مدين الصندوق; دائن ذمم العملاء",
    "البنك": "تحويل بنكي وارد: مدين البنك; دائن ذمم العملاء",
    "تسوية بطاقات": "قبض عبر بطاقة: مدين تسوية بطاقات; دائن ذمم العملاء",
    "ذمم العملاء": "سداد فاتورة من عميل: مدين الصندوق/البنك; دائن ذمم العملاء",
    "ذمم الموردين": "دفع لمورد: مدين ذمم الموردين; دائن الصندوق/البنك",
    "إيرادات المبيعات": "إلغاء فاتورة مبيعات (عكس): مدين إيرادات المبيعات; دائن ذمم العملاء",
    "إيرادات الخدمات": "إلغاء فاتورة خدمة (عكس): مدين إيرادات الخدمات; دائن ذمم العملاء",
    "المصروفات": "قيد مصروف نقدي: مدين المصروفات; دائن الصندوق/البنك",
    "ضريبة قيمة مضافة مستحقة": "قيد ضريبة مبيعات: مدين ذمم العملاء; دائن ضريبة قيمة مضافة مستحقة",
    "شيكات تحت التحصيل": "شيك وارد معلق: مدين شيكات تحت التحصيل; دائن ذمم العملاء",
    "شيكات مستحقة الدفع": "شيك صادر معلق: مدين ذمم الموردين; دائن شيكات مستحقة الدفع",
    "دفعات مقدمة/عربون": "قبض عربون حجز: مدين الصندوق/البنك; دائن دفعات مقدمة/عربون",
    "المخزون": "شراء مخزون: مدين المخزون; دائن ذمم الموردين/البنك",
    "رأس المال": "زيادة رأس المال: دائن رأس المال; مدين البنك/الصندوق",
    "أرباح محتجزة": "ترحيل أرباح: دائن الأرباح المحتجزة; مدين الأرباح",
    "المشتريات": "شراء بضاعة: مدين المشتريات; دائن ذمم الموردين",
    "الشحن": "تكلفة شحن: مدين الشحن; دائن البنك/الصندوق",
    "المناولة": "تكلفة مناولة: مدين المناولة; دائن البنك/الصندوق",
}


PHRASE_TRANSLATIONS = {
    "ACCOUNTS RECEIVABLE": "ذمم العملاء",
    "ACCOUNTS PAYABLE": "ذمم الموردين",
    "CARD CLEARING": "تسوية بطاقات",
    "RETAINED EARNINGS": "أرباح محتجزة",
    "OTHER INCOME": "إيرادات أخرى",
    "VAT PAYABLE": "ضريبة قيمة مضافة مستحقة",
}

TOKEN_TRANSLATIONS = {
    "CASH": "الصندوق",
    "BANK": "البنك",
    "CARD": "تسوية بطاقات",
    "AR": "ذمم العملاء",
    "AP": "ذمم الموردين",
    "VAT": "ضريبة قيمة مضافة",
    "CHEQUE": "شيكات",
    "CHECK": "شيكات",
    "CHEQUES": "شيكات",
    "RECEIVABLE": "تحت التحصيل",
    "PAYABLE": "مستحقة الدفع",
    "INVENTORY": "المخزون",
    "PURCHASES": "المشتريات",
    "SHIPPING": "الشحن",
    "HANDLING": "المناولة",
    "SERVICE": "الخدمات",
    "SALES": "المبيعات",
    "CAPITAL": "رأس المال",
    "EARNINGS": "الأرباح",
    "ADVANCE": "دفعات مقدمة",
    "SHORT": "قصير",
    "TERM": "الأجل",
    "TEMPORARY": "مؤقتة",
}

def translate_phrase(name_en):
    n = normalize(name_en)
    for k, v in PHRASE_TRANSLATIONS.items():
        if k in n:
            return v
    parts = re.split(r"[\s_\-/]+", n)
    translated = []
    for p in parts:
        translated.append(TOKEN_TRANSLATIONS.get(p, p))
    t = " ".join(translated).strip()
    if t and t != n:
        return t
    return ""

def guess_name_value(row):
    for key in ("name", "account", "account_name", "account_code", "code", "حساب", "اسم"):
        if key in row and row[key]:
            return row[key]
    return ""


def guess_type_value(row):
    for key in ("type", "category", "account_type", "نوع", "تصنيف"):
        if key in row and row[key]:
            return row[key]
    return ""


def translate_name(raw):
    n = normalize(raw)
    for token in (n, n.replace("_", " ")):
        if token in NAME_TRANSLATIONS:
            return NAME_TRANSLATIONS[token]
    t = translate_phrase(n)
    if t:
        return t
    if "1100" in n and "AR" in n:
        return NAME_TRANSLATIONS["AR"]
    if "2000" in n and "AP" in n:
        return NAME_TRANSLATIONS["AP"]
    if "BANK" in n:
        return NAME_TRANSLATIONS["BANK"]
    if "CASH" in n:
        return NAME_TRANSLATIONS["CASH"]
    if "CARD" in n:
        return NAME_TRANSLATIONS["CARD"]
    if "ADVANCE" in n:
        return NAME_TRANSLATIONS["ADVANCE PAYMENTS"]
    if "VAT" in n:
        return NAME_TRANSLATIONS["VAT PAYABLE"]
    if "CHEQUE" in n or "CHECK" in n:
        return NAME_TRANSLATIONS.get("CHEQUES RECEIVABLE", "شيكات")
    if "SALES" in n:
        return NAME_TRANSLATIONS["SALES"]
    if "SERVICE" in n:
        return NAME_TRANSLATIONS["SERVICE REVENUE"]
    if "EXPENSE" in n:
        return NAME_TRANSLATIONS["EXPENSES"]
    if "INVENTORY" in n:
        return NAME_TRANSLATIONS["INVENTORY"]
    return ""


def translate_type(raw):
    t = normalize(raw)
    return TYPE_TRANSLATIONS.get(t, "")


def example_for(translated_name, type_ar):
    ex = EXAMPLE_BY_NAME.get(translated_name, "")
    if ex:
        return ex
    if type_ar == "أصل":
        return f"زيادة أصل: مدين {translated_name or 'الحساب'}; دائن حساب مقابل"
    if type_ar == "التزام":
        return f"نشوء التزام: دائن {translated_name or 'الحساب'}; مدين حساب مقابل"
    if type_ar == "حقوق الملكية":
        return f"زيادة حقوق الملكية: دائن {translated_name or 'الحساب'}; مدين النقدية"
    if type_ar == "إيراد":
        return f"إثبات إيراد: دائن {translated_name or 'الحساب'}; مدين النقدية/المدين"
    if type_ar == "مصروف":
        return f"إثبات مصروف: مدين {translated_name or 'الحساب'}; دائن النقدية/الدائن"
    return ""


def enrich_csv(input_path):
    out_path = os.path.splitext(input_path)[0] + "_updated.csv"
    # محاولة أولى: القراءة كـ DictReader إذا كان هناك رؤوس أعمدة واضحة
    with open(input_path, "r", encoding="utf-8-sig", newline="") as f_in:
        try:
            dict_reader = csv.DictReader(f_in)
            fieldnames = list(dict_reader.fieldnames or [])
        except Exception:
            dict_reader = None
            fieldnames = []

    rows_dict = []
    empties = 0
    total = 0
    if fieldnames:
        with open(input_path, "r", encoding="utf-8-sig", newline="") as f_in:
            dict_reader = csv.DictReader(f_in)
            # الأعمدة الجديدة
            new_cols = ["مثال", "ترجمة محاسبية (الاسم)", "ترجمة محاسبية (النوع)"]
            for col in new_cols:
                if col not in fieldnames:
                    fieldnames.append(col)
            for row in dict_reader:
                total += 1
                name_val = guess_name_value(row)
                type_val = guess_type_value(row)
                name_ar = translate_name(name_val)
                type_ar = translate_type(type_val)
                ex = example_for(name_ar, type_ar)
                if not name_ar and not type_ar and not ex:
                    empties += 1
                row["مثال"] = ex
                row["ترجمة محاسبية (الاسم)"] = name_ar
                row["ترجمة محاسبية (النوع)"] = type_ar
                rows_dict.append(row)

    # إذا كانت معظم الصفوف فارغة بالمسار السابق، نستخدم مسار عام يعتمد على مواقع الأعمدة
    use_generic = (total == 0) or (empties / max(total, 1) > 0.7)

    if use_generic:
        with open(input_path, "r", encoding="utf-8-sig", newline="") as f_in:
            reader = csv.reader(f_in)
            all_rows = list(reader)
        # استنتاج وجود رأس أعمدة أم لا
        header = all_rows[0] if all_rows else []
        has_header = any(not re.match(r"^\s*\d+\s*$", str(c or "")) for c in header)
        start_idx = 1 if has_header else 0
        original_header = header if has_header else None
        output_rows = []
        # تجهيز رأس الإخراج
        if has_header:
            new_header = list(original_header) + ["مثال", "ترجمة محاسبية (الاسم)", "ترجمة محاسبية (النوع)"]
            output_rows.append(new_header)
        else:
            # رأس افتراضي إذا لم يوجد
            output_rows.append(["الحقل1", "الحقل2", "الحقل3"] + ["مثال", "ترجمة محاسبية (الاسم)", "ترجمة محاسبية (النوع)"])

        TYPE_KEYS = set(TYPE_TRANSLATIONS.keys())

        for row in all_rows[start_idx:]:
            cells = [str(c or "").strip() for c in row]
            # تحديد النوع: آخر خلية تطابق نوعاً معروفاً أو تحتويه
            type_en = ""
            for cell in reversed(cells):
                up = cell.upper()
                for tk in TYPE_KEYS:
                    if up == tk or tk in up:
                        type_en = tk
                        break
                if type_en:
                    break

            # تحديد الاسم: أول خلية نصية غير رقمية وغير النوع، أو خلية تتضمن مفتاح معروف للاسم
            name_en = ""
            NAME_KEYS = ["CASH", "BANK", "CARD", "AR", "AP", "VAT", "CHEQUE", "CHECK", "ADVANCE", "SALES", "SERVICE", "EXPENSE", "INVENTORY"]
            for cell in cells:
                up = cell.upper()
                if re.match(r"^\d+$", up):
                    continue
                if type_en and type_en in up:
                    continue
                if any(k in up for k in NAME_KEYS):
                    name_en = up
                    break
            if not name_en:
                # افتراضي: الخلية الثانية إن وجدت
                if len(cells) > 1:
                    name_en = cells[1].upper()
                elif cells:
                    name_en = cells[0].upper()

            name_ar = translate_name(name_en)
            type_ar = translate_type(type_en) or (
                "أصل" if code and 1000 <= code <= 1999 else (
                    "التزام" if code and 2000 <= code <= 2999 else (
                        "حقوق الملكية" if code and 3000 <= code <= 3999 else (
                            "إيراد" if code and 4000 <= code <= 4999 else (
                                "مصروف" if code and 5000 <= code <= 5999 else ""
                            )
                        )
                    )
                )
            )
            ex = example_for(name_ar, type_ar)
            output_rows.append(cells + [ex, name_ar, type_ar])

        # كتابة مع BOM ليتعرّف Excel على العربية مباشرة
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f_out:
            f_out.write("sep=,\n")
            writer = csv.writer(f_out)
            for r in output_rows:
                writer.writerow(r)
    else:
        # كتابة نسخة Dict مع BOM
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f_out:
            f_out.write("sep=,\n")
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows_dict:
                writer.writerow(r)

    return out_path


def main():
    if len(sys.argv) < 2:
        print("يرجى تمرير مسار ملف CSV كأول وسيط.")
        print("مثال: python scripts\\update_export.py \"C:\\Users\\AhmadGh\\Downloads\\export_2025-11-26 (1).csv\"")
        return
    input_path = sys.argv[1]
    if not os.path.isfile(input_path):
        print(f"الملف غير موجود: {input_path}")
        return
    out_path = enrich_csv(input_path)
    print(f"✅ تم إنشاء الملف المحدّث: {out_path}")

    # إنشاء نسخة XLSX لفتح مضمون بالعربية بدون مشاكل ترميز
    try:
        from openpyxl import Workbook
        import io
        # إعادة قراءة الناتج لكتابة نفس الحقول في XLSX
        with open(out_path, "r", encoding="utf-8-sig", newline="") as f_in:
            reader = csv.reader(f_in)
            rows = list(reader)
        wb = Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)
        xlsx_path = os.path.splitext(input_path)[0] + "_updated.xlsx"
        wb.save(xlsx_path)
        print(f"✅ تم إنشاء نسخة إكسل: {xlsx_path}")
    except Exception as e:
        # في حال عدم توفر openpyxl، إنشاء CSV بترميز UTF-16LE كبديل متوافق مع إكسل قديم
        try:
            utf16_path = os.path.splitext(input_path)[0] + "_updated_utf16.csv"
            with open(utf16_path, "w", encoding="utf-16", newline="") as f_out:
                f_out.write("sep=,\n")
                with open(out_path, "r", encoding="utf-8-sig", newline="") as f_in:
                    for line in f_in:
                        f_out.write(line)
            print(f"⚠️ openpyxl غير متاح، تم إنشاء بديل: {utf16_path}")
        except Exception as e2:
            print(f"❌ تعذر إنشاء بديل XLSX/UTF-16: {e2}")


if __name__ == "__main__":
    main()
