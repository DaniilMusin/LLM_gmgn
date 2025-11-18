import os, pandas as pd, logging
from datetime import datetime, timezone
from ..config import settings

# BUG FIX #53: Add missing logger object
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
def _ensure_dir(path: str): os.makedirs(path, exist_ok=True)
def log_signal(record: dict, *, fname_csv: str = "signals.csv", fname_parquet: str = "signals.parquet"):
    out_dir = settings.logging.out_dir; _ensure_dir(out_dir)
    ts = datetime.now(timezone.utc).isoformat(); rec = {"ts": ts, **record}
    csv_path = os.path.join(out_dir, fname_csv); parquet_path = os.path.join(out_dir, fname_parquet)
    header = not os.path.exists(csv_path)
    import csv
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rec.keys()))
        if header: w.writeheader()
        w.writerow(rec)
    try:
        df = pd.DataFrame([rec])
        if os.path.exists(parquet_path):
            old = pd.read_parquet(parquet_path); df = pd.concat([old, df], ignore_index=True)
        df.to_parquet(parquet_path, index=False)
    except Exception: pass
