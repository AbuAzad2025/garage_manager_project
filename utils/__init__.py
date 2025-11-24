import sys
import os
import importlib.util

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_utils_file = os.path.join(_parent_dir, 'utils.py')

if os.path.exists(_utils_file):
    spec = importlib.util.spec_from_file_location("_utils_legacy", _utils_file)
    _utils_legacy = importlib.util.module_from_spec(spec)
    sys.modules["_utils_legacy"] = _utils_legacy
    spec.loader.exec_module(_utils_legacy)
    
    _all_names = set(dir(_utils_legacy))
    _skip_names = {'__all__', '__doc__', '__file__', '__name__', '__package__', '__loader__', '__spec__', '__cached__', '__builtins__'}
    
    for attr_name in _all_names:
        if attr_name in _skip_names or attr_name.startswith('__') and attr_name.endswith('__'):
            continue
        try:
            attr_value = getattr(_utils_legacy, attr_name)
            setattr(sys.modules[__name__], attr_name, attr_value)
        except Exception:
            pass

