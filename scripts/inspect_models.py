# scripts/inspect_models.py
import os, sys, json, enum, inspect, importlib

# أضف جذر المشروع للمسار
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

def _impc(cands):
    last = None
    for name in cands:
        try:
            return importlib.import_module(name)
        except Exception as e:
            last = e
    raise RuntimeError(f"Import failed for {cands}: {last!r}")

# جرّب موديولات شائعة فيها create_app/db/models
app_mod     = _impc(["app","wsgi","application","garage_manager.app"])
create_app  = getattr(app_mod, "create_app")

ext_mod     = _impc(["extensions","garage_manager.extensions"])
db          = getattr(ext_mod, "db")

models_mod  = _impc(["models","garage_manager.models"])

def enum_dump():
    out = {}
    for name, obj in inspect.getmembers(models_mod):
        if inspect.isclass(obj) and issubclass(obj, enum.Enum):
            out[name] = [m.value for m in obj]
    return out

def tables_dump():
    md = db.Model.metadata
    res = []
    for t in md.sorted_tables:
        cols = []
        for c in t.columns:
            col = {
                "name": c.name,
                "type": str(c.type),
                "nullable": c.nullable,
                "primary_key": c.primary_key,
                "unique": any(getattr(cons, "columns", None) and c.name in [cc.name for cc in cons.columns] for cons in t.constraints),
                "fk": [f"{fk.column.table.name}.{fk.column.name}" for fk in c.foreign_keys],
                "default": str(getattr(c.default, 'arg', None)) if c.default is not None else None,
                "server_default": str(c.server_default.arg.text) if c.server_default is not None else None,
            }
            for attr in ("enums","_enums","possible_values"):
                if hasattr(c.type, attr):
                    col["enum_values"] = list(getattr(c.type, attr))
                    break
            cols.append(col)
        uniques, checks = [], []
        for cons in t.constraints:
            cname = cons.name or ""
            if cons.__class__.__name__ == "UniqueConstraint":
                uniques.append({"name": cname, "cols": [c.name for c in cons.columns]})
            if cons.__class__.__name__ == "CheckConstraint":
                checks.append({"name": cname, "sqltext": str(cons.sqltext)})
        res.append({"table": t.name, "columns": cols, "uniques": uniques, "checks": checks})
    return res

def main():
    os.makedirs("artifacts", exist_ok=True)
    app = create_app()
    with app.app_context():
        payload = {"enums": enum_dump(), "tables": tables_dump()}
        with open("artifacts/models_snapshot.json","w",encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
