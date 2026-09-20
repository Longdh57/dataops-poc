"""Nap hai job duoi hai ten khac nhau.

Ca jobs/export/main.py lan jobs/qc/main.py deu ten module la `main`, nen
`import main` se lay nham cai nao nap truoc. Nap thang tu duong dan file
va dat ten rieng cho tung cai.
"""

import importlib.util
import sys
from pathlib import Path

JOBS = Path(__file__).resolve().parents[1]


def _load(ten: str, duong_dan: Path):
    spec = importlib.util.spec_from_file_location(ten, duong_dan)
    module = importlib.util.module_from_spec(spec)
    sys.modules[ten] = module
    spec.loader.exec_module(module)
    return module


export_main = _load("export_main", JOBS / "export" / "main.py")
qc_main = _load("qc_main", JOBS / "qc" / "main.py")
