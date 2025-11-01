-- ════════════════════════════════════════════════════════════════
-- Migration: إضافة حقول تتبع دفع أقساط السلف
-- التاريخ: 2025-10-31
-- الوصف: إضافة حقول paid_date و paid_in_salary_expense_id لتتبع دفع الأقساط
-- ════════════════════════════════════════════════════════════════

-- 1️⃣ إضافة حقل تاريخ دفع القسط
ALTER TABLE employee_advance_installments 
ADD COLUMN paid_date DATE DEFAULT NULL;

-- 2️⃣ إضافة حقل ربط القسط بالراتب الذي دُفع فيه
ALTER TABLE employee_advance_installments 
ADD COLUMN paid_in_salary_expense_id INTEGER DEFAULT NULL;

-- 3️⃣ إضافة فهرس للبحث السريع
CREATE INDEX idx_installment_paid_date 
ON employee_advance_installments(paid_date);

CREATE INDEX idx_installment_salary_link 
ON employee_advance_installments(paid_in_salary_expense_id);

-- 4️⃣ إضافة مفتاح خارجي للربط بجدول expenses
ALTER TABLE employee_advance_installments 
ADD CONSTRAINT fk_installment_salary_expense 
FOREIGN KEY (paid_in_salary_expense_id) 
REFERENCES expenses(id) 
ON DELETE SET NULL;

-- ════════════════════════════════════════════════════════════════
-- Notes:
-- - paid_date: تاريخ دفع القسط (يُحدث تلقائياً عند توليد الراتب)
-- - paid_in_salary_expense_id: معرف سجل الراتب الذي دُفع فيه القسط
-- - هذه الحقول تسمح بتتبع دقيق للأقساط المدفوعة ضمن الرواتب
-- ════════════════════════════════════════════════════════════════

COMMIT;

