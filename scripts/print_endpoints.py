# scripts/print_endpoints.py
import os, sys, importlib

# أضف مجلد المشروع إلى PYTHONPATH (مجلد السكربت/..)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# جرّب أشهر أسماء الموديول اللي ممكن تحتوي create_app
CANDIDATES = ["app", "wsgi", "application", "garage_manager.app"]

create_app = None
last_err = None
for mod in CANDIDATES:
    try:
        m = importlib.import_module(mod)
        if hasattr(m, "create_app"):
            create_app = getattr(m, "create_app")
            break
    except Exception as e:
        last_err = e

if not create_app:
    raise RuntimeError(f"لم أجد create_app في أي من: {CANDIDATES}. آخر خطأ: {last_err!r}")

app = create_app()
with app.app_context():
    for r in sorted(app.url_map.iter_rules(), key=lambda r: r.endpoint):
        methods = ",".join(sorted(r.methods - {"HEAD","OPTIONS"}))
        print(f"{r.endpoint:40} {methods:10} {r.rule}")
