# scripts/inspect_domain.py
import os, sys, json, inspect, importlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

MODULES = [
    "utils", "reports",
    "routes.payments", "routes.warehouses", "routes.shipments",
    "routes.service", "routes.sales"
]

def dump_module(modname):
    out = {"functions": [], "classes": []}
    try:
        m = importlib.import_module(modname)
    except Exception as e:
        out["import_error"] = repr(e)
        return out
    for name, obj in inspect.getmembers(m, inspect.isfunction):
        if obj.__module__ == m.__name__:
            sig = str(inspect.signature(obj))
            doc = (inspect.getdoc(obj) or "").splitlines()[0:1]
            out["functions"].append({"name": name, "signature": sig, "doc": " ".join(doc)})
    for name, obj in inspect.getmembers(m, inspect.isclass):
        if obj.__module__ == m.__name__:
            methods = []
            for mn, mo in inspect.getmembers(obj, inspect.isfunction):
                if mo.__qualname__.startswith(obj.__name__ + "."):
                    methods.append({"name": mn, "signature": str(inspect.signature(mo))})
            out["classes"].append({"name": name, "methods": methods})
    return out

def main():
    os.makedirs("artifacts", exist_ok=True)
    payload = {mod: dump_module(mod) for mod in MODULES}
    with open("artifacts/domain_signatures.json","w",encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
