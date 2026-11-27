import os
import sys
from pathlib import Path

os.environ["PATH"] = r"C:\Program Files\Tesseract-OCR;" + os.environ["PATH"]
sys.path.insert(0, r"E:\MAX-FINANCE-TEST\staging")

from maxfinance_test.line import detect_boundary_candidates, detect_boundary

for name in sys.argv[1:]:
    path = Path(r"E:\MAX-FINANCE-TEST\testdata") / name
    data = path.read_bytes()
    candidates = detect_boundary_candidates(data)
    print(name, "size", len(data), "candidates", [(round(a, 3), round(b, 3)) for a, b in candidates])
    print("  chosen", detect_boundary(data))
