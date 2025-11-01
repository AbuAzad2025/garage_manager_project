-- =====================================================
-- إضافة حقول تفاصيل الدفع لموديل Expense
-- =====================================================
-- تاريخ: 2025-10-31
-- الوصف: إضافة حقول check_payee, bank_name, account_number, account_holder
-- =====================================================

-- 1. إضافة حقول الشيكات
ALTER TABLE expenses ADD COLUMN check_payee VARCHAR(200);

-- 2. إضافة حقول التحويل البنكي
ALTER TABLE expenses ADD COLUMN bank_name VARCHAR(100);
ALTER TABLE expenses ADD COLUMN account_number VARCHAR(100);
ALTER TABLE expenses ADD COLUMN account_holder VARCHAR(200);

-- 3. تحديث السجلات الموجودة (اختياري - فقط إذا كان هناك بيانات قديمة)
-- UPDATE expenses 
-- SET check_payee = paid_to 
-- WHERE payment_method = 'CHEQUE' AND check_payee IS NULL AND paid_to IS NOT NULL;

-- UPDATE expenses 
-- SET account_holder = paid_to 
-- WHERE payment_method = 'BANK' AND account_holder IS NULL AND paid_to IS NOT NULL;

-- =====================================================
-- ملاحظات:
-- =====================================================
-- 1. check_payee: اسم المستفيد من الشيك
-- 2. bank_name: اسم البنك للتحويل البنكي
-- 3. account_number: رقم الحساب البنكي
-- 4. account_holder: صاحب الحساب البنكي
-- =====================================================

