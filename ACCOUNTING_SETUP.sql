-- ═══════════════════════════════════════════════════════════════════════
-- 📊 إنشاء دليل الحسابات المحاسبي (Chart of Accounts)
-- ═══════════════════════════════════════════════════════════════════════
-- 
-- استخدام: قم بتنفيذ هذا الملف على قاعدة البيانات (المحلي وPythonAnywhere)
-- 
-- على المحلي:
--   python -c "
--   from app import create_app
--   from extensions import db
--   app = create_app()
--   with app.app_context():
--       with open('ACCOUNTING_SETUP.sql', 'r', encoding='utf-8') as f:
--           sql = f.read()
--           for stmt in sql.split(';'):
--               if stmt.strip():
--                   db.session.execute(text(stmt))
--       db.session.commit()
--   "
--
-- على PythonAnywhere:
--   cd ~/garage_manager_project
--   python3.10 << 'EOF'
--   from app import create_app
--   from extensions import db
--   from sqlalchemy import text
--   app = create_app()
--   with app.app_context():
--       with open('ACCOUNTING_SETUP.sql', 'r', encoding='utf-8') as f:
--           sql = f.read()
--           for stmt in sql.split(';'):
--               if stmt.strip():
--                   db.session.execute(text(stmt))
--       db.session.commit()
--       print('✅ تم إنشاء دليل الحسابات!')
--   EOF
-- ═══════════════════════════════════════════════════════════════════════

-- حذف الحسابات القديمة (اختياري)
-- DELETE FROM accounts;

-- 1. الأصول (Assets) - 1000-1999
INSERT OR IGNORE INTO accounts (code, name, type, is_active, created_at, updated_at)
VALUES
('1000_CASH', 'النقدية - الصندوق', 'ASSET', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('1010_BANK', 'البنك - الحساب الجاري', 'ASSET', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('1020_CARD_CLEARING', 'مقاصة البطاقات', 'ASSET', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('1100_AR', 'حسابات العملاء - المدينون', 'ASSET', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('1200_INVENTORY', 'المخزون', 'ASSET', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('1205_INV_EXCHANGE', 'مخزون العهدة', 'ASSET', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 2. الالتزامات (Liabilities) - 2000-2999
INSERT OR IGNORE INTO accounts (code, name, type, is_active, created_at, updated_at)
VALUES
('2000_AP', 'حسابات الموردين - الدائنون', 'LIABILITY', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('2100_VAT_PAYABLE', 'ضريبة القيمة المضافة', 'LIABILITY', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 3. رأس المال (Equity) - 3000-3999
INSERT OR IGNORE INTO accounts (code, name, type, is_active, created_at, updated_at)
VALUES
('3000_EQUITY', 'رأس المال', 'EQUITY', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('3100_RETAINED_EARNINGS', 'الأرباح المحتجزة', 'EQUITY', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 4. الإيرادات (Revenue) - 4000-4999
INSERT OR IGNORE INTO accounts (code, name, type, is_active, created_at, updated_at)
VALUES
('4000_SALES', 'إيرادات المبيعات', 'REVENUE', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('4100_SERVICE_REVENUE', 'إيرادات الصيانة', 'REVENUE', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 5. المصروفات (Expenses) - 5000-5999
INSERT OR IGNORE INTO accounts (code, name, type, is_active, created_at, updated_at)
VALUES
('5000_EXPENSES', 'المصروفات العامة', 'EXPENSE', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('5100_COGS', 'تكلفة البضاعة المباعة', 'EXPENSE', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('5105_COGS_EXCHANGE', 'تكلفة بضاعة العهدة المباعة', 'EXPENSE', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- التحقق من النتيجة
SELECT '✅ تم إنشاء دليل الحسابات' AS status, COUNT(*) AS total_accounts FROM accounts WHERE is_active = 1;

