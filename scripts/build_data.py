"""Build the parquet cache from the raw Oanda CSVs.

Raw data: git clone (sparse) of https://github.com/FutureSharks/financial-data,
see scripts/fetch_data.sh.
"""
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from ictmodel.data import INSTRUMENTS, build_cache  # noqa: E402

for inst in (sys.argv[1:] or INSTRUMENTS):
    t = time.time()
    print(inst, "->", build_cache(inst), f"{time.time() - t:.1f}s", flush=True)
