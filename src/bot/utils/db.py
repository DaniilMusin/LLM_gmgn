import os, sqlite3, json, threading
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from ..config import settings

_LOCK = threading.Lock()

def _db_path():
    out = settings.logging.out_dir; os.makedirs(out, exist_ok=True); return os.path.join(out, "trader.db")

def _conn():
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    with _LOCK:
        conn = _conn()
        conn.execute("""
CREATE TABLE IF NOT EXISTS quotes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT,
  symbol TEXT,
  contract TEXT,
  in_token TEXT,
  out_token TEXT,
  in_amount TEXT,
  slippage REAL,
  anti_mev INTEGER,
  priority_fee REAL,
  quote_json TEXT,
  price_impact REAL,
  expected_out REAL,
  route_json TEXT
);
""")
        conn.execute("""
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT,
  quote_id INTEGER,
  tx TEXT,
  split INTEGER,
  status_json TEXT,
  realized_out REAL,
  slippage_pct REAL,
  amm_pi_pct REAL,
  side TEXT,
  contract TEXT
);
""")
        conn.execute("""
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT,
  contract TEXT,
  side TEXT,
  qty REAL,
  invested_wsol REAL,
  avg_entry_wsol REAL,
  opened_at TEXT,
  max_hold_sec INTEGER,
  hwm_wsol REAL,
  hwm_return REAL,
  tp1_done INTEGER,
  tp2_done INTEGER,
  decimals INTEGER,
  entry_txns_h1 INTEGER,
  owner_address TEXT,
  meta_json TEXT,
  state TEXT,
  last_check_ts TEXT
);
""")
        conn.execute("""
CREATE TABLE IF NOT EXISTS exits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  position_id INTEGER,
  ts TEXT,
  reason TEXT,
  pct REAL,
  qty_sold REAL,
  expected_out REAL,
  realized_out REAL,
  slippage_pct REAL,
  amm_pi_pct REAL,
  tx TEXT
);
"""
)
        conn.commit(); conn.close()

def save_quote(symbol: str, contract: str, in_token: str, out_token: str, in_amount: str,
               slippage: float | None, anti_mev: bool, priority_fee: float | None,
               quote: dict, price_impact: float | None, expected_out: float | None, route_json: dict) -> int:
    with _LOCK:
        init_db(); conn = _conn()
        ts = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("""
INSERT INTO quotes(ts,symbol,contract,in_token,out_token,in_amount,slippage,anti_mev,priority_fee,quote_json,price_impact,expected_out,route_json)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
""", (ts,symbol,contract,in_token,out_token,in_amount,slippage,1 if anti_mev else 0,priority_fee,json.dumps(quote),price_impact,expected_out,json.dumps(route_json)))
        conn.commit(); qid = cur.lastrowid; conn.close(); return qid

def save_trade(quote_id: int, tx: str | None, split: int, status: dict | None,
               realized_out: float | None, slippage_pct: float | None, amm_pi_pct: float | None,
               side: str, contract: str) -> int:
    with _LOCK:
        init_db(); conn = _conn()
        ts = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("""
INSERT INTO trades(ts,quote_id,tx,split,status_json,realized_out,slippage_pct,amm_pi_pct,side,contract)
VALUES (?,?,?,?,?,?,?,?,?,?)
""", (ts,quote_id,tx,split,json.dumps(status or {}),realized_out,slippage_pct,amm_pi_pct,side,contract))
        conn.commit(); tid = cur.lastrowid; conn.close(); return tid

def get_open_position_by_contract(contract: str) -> sqlite3.Row | None:
    with _LOCK:
        init_db(); conn = _conn()
        row = conn.execute("SELECT * FROM positions WHERE contract=? AND state='open'", (contract,)).fetchone()
        conn.close(); return row

def upsert_position_on_buy(symbol: str, contract: str, qty_added: float, cost_wsol_added: float,
                           max_hold_sec: int | None, decimals: int | None,
                           entry_txns_h1: int | None, owner_address: str | None, kill_switch: list[str] | None) -> int:
    with _LOCK:
        init_db(); conn = _conn()
        # BUG FIX #14: Ensure connection is closed even if exception occurs
        try:
            row = conn.execute("SELECT * FROM positions WHERE contract=? AND state='open'", (contract,)).fetchone()
            ts = datetime.now(timezone.utc).isoformat()
            meta = {"kill_switch": kill_switch or []}
            if row is None:
                avg = cost_wsol_added / max(1e-12, qty_added)
                cur = conn.execute("""
INSERT INTO positions(symbol,contract,side,qty,invested_wsol,avg_entry_wsol,opened_at,max_hold_sec,hwm_wsol,hwm_return,tp1_done,tp2_done,decimals,entry_txns_h1,owner_address,meta_json,state,last_check_ts)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", (symbol,contract,'long',qty_added,cost_wsol_added,avg,ts,max_hold_sec,0.0,0.0,0,0,decimals or 0,entry_txns_h1 or 0,owner_address or '',json.dumps(meta),'open',ts))
                conn.commit(); pid = cur.lastrowid
            else:
                pid = row['id']; qty = float(row['qty'] or 0) + float(qty_added or 0); inv = float(row['invested_wsol'] or 0) + float(cost_wsol_added or 0)
                avg = inv / max(1e-12, qty)
                conn.execute("UPDATE positions SET qty=?, invested_wsol=?, avg_entry_wsol=?, max_hold_sec=COALESCE(?,max_hold_sec), last_check_ts=? WHERE id=?",
                             (qty, inv, avg, max_hold_sec, ts, pid))
                conn.commit()
            return int(pid)
        finally:
            conn.close()

def reduce_position(pid: int, qty_sold: float, expected_out_wsol: float | None, realized_out_wsol: float | None,
                    slippage_pct: float | None, amm_pi_pct: float | None, tx: str | None, reason: str):
    with _LOCK:
        init_db(); conn=_conn()
        row = conn.execute("SELECT * FROM positions WHERE id=?", (pid,)).fetchone()
        if not row: conn.close(); return
        qty = float(row['qty'] or 0); inv = float(row['invested_wsol'] or 0)
        sell_qty = min(qty, qty_sold)
        new_qty = max(0.0, qty - sell_qty)
        inv_reduced = inv * (sell_qty / max(1e-12, qty))
        new_inv = inv - inv_reduced
        avg = new_inv / max(1e-12, new_qty) if new_qty>0 else 0.0
        ts = datetime.now(timezone.utc).isoformat()
        pct = sell_qty / max(1e-12, qty)
        conn.execute("INSERT INTO exits(position_id,ts,reason,pct,qty_sold,expected_out,realized_out,slippage_pct,amm_pi_pct,tx) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (pid,ts,reason,pct,sell_qty,expected_out_wsol,realized_out_wsol,slippage_pct,amm_pi_pct,tx))
        if new_qty <= 1e-12:
            conn.execute("UPDATE positions SET qty=?, invested_wsol=?, avg_entry_wsol=?, state='closed', last_check_ts=? WHERE id=?",
                         (0.0, 0.0, 0.0, ts, pid))
        else:
            conn.execute("UPDATE positions SET qty=?, invested_wsol=?, avg_entry_wsol=?, last_check_ts=? WHERE id=?",
                         (new_qty, new_inv, avg, ts, pid))
        conn.commit(); conn.close()

def mark_position_check(pid: int, hwm_wsol: float | None, hwm_return: float | None, tp1_done: bool | None, tp2_done: bool | None):
    with _LOCK:
        init_db(); conn=_conn(); ts = datetime.now(timezone.utc).isoformat()
        sets=[]; vals=[]
        if hwm_wsol is not None: sets.append("hwm_wsol=?"); vals.append(hwm_wsol)
        if hwm_return is not None: sets.append("hwm_return=?"); vals.append(hwm_return)
        if tp1_done is not None: sets.append("tp1_done=?"); vals.append(1 if tp1_done else 0)
        if tp2_done is not None: sets.append("tp2_done=?"); vals.append(1 if tp2_done else 0)
        sets.append("last_check_ts=?"); vals.append(ts); vals.append(pid)
        conn.execute("UPDATE positions SET "+",".join(sets)+" WHERE id=?", vals)
        conn.commit(); conn.close()

def get_open_positions() -> List[sqlite3.Row]:
    with _LOCK:
        init_db(); conn=_conn()
        rows = conn.execute("SELECT * FROM positions WHERE state='open' ORDER BY opened_at").fetchall()
        conn.close(); return rows

def get_recent_amm_pi(contract: str, minutes: int = 60) -> float | None:
    with _LOCK:
        init_db(); conn=_conn()
        # BUG FIX #5: Use UTC timezone instead of local time
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        row = conn.execute("SELECT MIN(amm_pi_pct) AS min_pi FROM trades WHERE contract=? AND ts >= ?", (contract, cutoff)).fetchone()
        conn.close()
        if row and row["min_pi"] is not None:
            try: return float(row["min_pi"])
            except Exception: return None
        return None
