import sys
from pathlib import Path

PROD = Path(r"E:\MAX-FINANCE-TEST\prod-src\max-finance-stage")
if str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))
