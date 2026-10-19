"""Compatibility entry point; implementation lives in one application directory."""
from pathlib import Path
import importlib.util
import runpy
import sys

APP = Path(__file__).resolve().parent / "PAIPU_SELECT_Mobile_Web_FullStack_v2"
sys.path.insert(0, str(APP))
if __name__ == "__main__":
    runpy.run_path(str(APP / "server.py"), run_name="__main__")
else:
    spec = importlib.util.spec_from_file_location(__name__, APP / "server.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[__name__] = module
    spec.loader.exec_module(module)
