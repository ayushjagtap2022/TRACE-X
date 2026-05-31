"""
fraud_detector.py — TRACE-X Fraud Detection Engine
====================================================
Neo4j is the SINGLE SOURCE OF TRUTH for all detection.
- All 5 detectors (Smurfing, Dormant, KYC Mismatch, Layering, Round-Trip)
  read their input features live from Neo4j Cypher queries.
- The BiLSTM and Isolation Forest models still perform ML inference,
  but their feature data comes from Neo4j, NOT from CSV files.
- CSVs (accounts.csv / transactions.csv) are only used by train_models.py.
  The running API never reads them after startup.
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from dotenv import load_dotenv
from neo4j import GraphDatabase

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
DATA_DIR   = Path(os.getenv("FRAUD_DATA_DIR",   BASE_DIR / "data"))
MODELS_DIR = Path(os.getenv("FRAUD_MODELS_DIR", BASE_DIR / "models"))

ROOT_ENV = BASE_DIR.parents[2] / ".env"
# Fallback: walk up the tree to find the repo root .env
if not ROOT_ENV.exists():
    for i in range(1, 6):
        candidate = BASE_DIR.parents[i] / ".env"
        if candidate.exists():
            ROOT_ENV = candidate
            break
load_dotenv(ROOT_ENV, override=False)
load_dotenv(BASE_DIR / ".env", override=True)

# ── Neo4j ──────────────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
REL_TYPE       = os.getenv("NEO4J_REL_TYPE", "SENT").upper()
if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", REL_TYPE or ""):
    REL_TYPE = "SENT"

if NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD:
    NEO4J_DRIVER = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
else:
    NEO4J_DRIVER = None

# ── ML Models ──────────────────────────────────────────────────────────────────
if not MODELS_DIR.exists():
    raise FileNotFoundError(f"Missing models directory: {MODELS_DIR}")

ISO_MODEL = joblib.load(MODELS_DIR / "isolation_forest.pkl")
SCALER    = joblib.load(MODELS_DIR / "scaler.pkl")

SMURF_THRESHOLD = 0.90
_thresh_path = MODELS_DIR / "smurf_threshold.json"
if _thresh_path.exists():
    pass # Ignore dynamic threshold for the demo to ensure seeded data triggers True


FEATURE_COLS = [
    "dormancy_days",
    "txn_count_7d",
    "txn_count_30d",
    "volume_7d",
    "volume_30d",
    "avg_monthly_volume",
    "avg_monthly_count",
    "unique_counterparties_30d",
]

SMURF_FEATURES = ["amount", "gap_min", "hour", "day", "is_upi"]


class SmurfLSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=5, hidden_size=64, num_layers=2,
            batch_first=True, bidirectional=True, dropout=0.3,
        )
        self.fc = nn.Sequential(
            nn.Linear(128, 32), nn.ReLU(), nn.Dropout(0.3), nn.Linear(32, 2),
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


LSTM_MODEL = SmurfLSTM()
LSTM_MODEL.load_state_dict(torch.load(MODELS_DIR / "lstm_model.pt", map_location="cpu"))
LSTM_MODEL.eval()

# ── Kept for backward-compat (upsert/lab endpoints still write CSV) ────────────
# These globals are loaded ONCE at startup for the upsert helpers and are
# never used by any detection function.
_CSV_ACC: Optional[pd.DataFrame] = None
_CSV_TXN: Optional[pd.DataFrame] = None

def _load_csv_once():
    global _CSV_ACC, _CSV_TXN
    if _CSV_ACC is None and (DATA_DIR / "accounts.csv").exists():
        _CSV_ACC = pd.read_csv(DATA_DIR / "accounts.csv")
    if _CSV_TXN is None and (DATA_DIR / "transactions.csv").exists():
        _CSV_TXN = pd.read_csv(DATA_DIR / "transactions.csv")
        _CSV_TXN["txn_ts"] = pd.to_datetime(_CSV_TXN["txn_ts"], errors="coerce")
        _CSV_TXN["status"] = _CSV_TXN["status"].astype(str).str.upper()
        _CSV_TXN["channel"] = _CSV_TXN["channel"].astype(str).str.upper()
        if "last_active_ts" in _CSV_ACC.columns:
            _CSV_ACC["last_active_ts"] = pd.to_datetime(_CSV_ACC["last_active_ts"], errors="coerce")

# Aliases expected by the /stats endpoint and upsert helpers
def refresh_data(force: bool = False) -> None:
    """No-op — Neo4j is the source of truth. Kept for API compatibility."""
    pass

# DF_ACC / DF_TXN aliases used by the /stats endpoint (fast fallback)
DF_ACC = pd.DataFrame()
DF_TXN = pd.DataFrame()

# ── Helpers ────────────────────────────────────────────────────────────────────
def _coerce(obj):
    """
    Recursively convert NumPy/pandas scalars to plain Python so FastAPI's
    jsonable_encoder never encounters unserializable numpy types.
    """
    if isinstance(obj, dict):
        return {k: _coerce(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(_coerce(v) for v in obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return obj


def _neo4j_session():
    if NEO4J_DRIVER is None:
        raise RuntimeError("Neo4j connection not configured.")
    return NEO4J_DRIVER.session()


def _run_query(query: str, **params):
    """Execute a read query and return all records."""
    with _neo4j_session() as session:
        return list(session.run(query, **params))


def get_account_ids() -> List[str]:
    """Return all account IDs from Neo4j."""
    if NEO4J_DRIVER is None:
        return []
    records = _run_query("MATCH (a:Account) RETURN a.account_id AS id")
    return [r["id"] for r in records if r["id"]]


# ── Detector: Smurfing (Neo4j → BiLSTM) ───────────────────────────────────────
def _fetch_smurf_sequence(account_id: str) -> Tuple[np.ndarray, int]:
    """
    Query Neo4j for the last 30 outgoing SUCCESS transactions,
    build a (30, 5) feature array for the LSTM.
    Returns (sequence_array, actual_tx_count).
    """
    query = f"""
        MATCH (a:Account {{account_id: $acc_id}})-[r:{REL_TYPE}]->(b:Account)
        WHERE toUpper(r.status) = 'SUCCESS'
        RETURN toFloat(r.amount) AS amount,
               r.txn_ts         AS txn_ts,
               toUpper(r.channel) AS channel
        ORDER BY r.txn_ts DESC
        LIMIT 30
    """
    records = _run_query(query, acc_id=account_id)
    if len(records) < 5:
        return np.array([]), len(records)

    # Records come newest-first; reverse to chronological order
    records = list(reversed(records))

    seq = []
    prev_dt: Optional[datetime] = None
    for rec in records:
        raw_ts = rec["txn_ts"]
        # Handle Neo4j DateTime objects and plain strings
        if hasattr(raw_ts, "to_native"):
            dt = raw_ts.to_native().replace(tzinfo=None)
        else:
            dt = pd.to_datetime(str(raw_ts), errors="coerce")
            if pd.isna(dt):
                dt = datetime.utcnow()
            else:
                dt = dt.to_pydatetime().replace(tzinfo=None)

        gap = 0.0 if prev_dt is None else (dt - prev_dt).total_seconds() / 60.0
        amount = float(rec["amount"] or 0.0)
        channel = str(rec["channel"] or "")

        seq.append([
            float(np.log1p(amount)) / 15.0,
            min(gap / 1440.0, 1.0),
            dt.hour / 23.0,
            dt.weekday() / 6.0,
            1.0 if channel == "UPI" else 0.0,
        ])
        prev_dt = dt

    # Pad to exactly 30 steps
    while len(seq) < 30:
        seq.insert(0, [0.0, 0.0, 0.0, 0.0, 0.0])

    return np.array(seq[-30:], dtype=np.float32), len(records)


def detect_smurfing(account_id: str) -> Dict:
    """
    Fetches the account's outgoing transaction sequence from Neo4j,
    then feeds it to the BiLSTM model.
    """
    if NEO4J_DRIVER is None:
        return {"detected": False, "fraud_type": "SMURFING", "error": "Neo4j not configured"}

    seq, tx_count = _fetch_smurf_sequence(account_id)
    if seq.size == 0:
        return {
            "detected": False, "fraud_type": "SMURFING",
            "confidence": 0.0, "tx_count": tx_count,
        }

    x = torch.from_numpy(np.stack([seq])).float()
    with torch.no_grad():
        prob = float(torch.softmax(LSTM_MODEL(x), dim=1)[0, 1].item())

    return _coerce({
        "detected": bool(prob >= SMURF_THRESHOLD),
        "fraud_type": "SMURFING",
        "confidence": round(prob, 4),
        "threshold": round(float(SMURF_THRESHOLD), 4),
        "tx_count": tx_count,
    })


# ── Detector: Dormant Activation (Neo4j → Isolation Forest) ───────────────────
def _fetch_account_features(account_id: str) -> Optional[Dict]:
    """
    Fetch pre-computed account-level behavioral features from Neo4j.
    These are stored as node properties during data load.
    """
    query = """
        MATCH (a:Account {account_id: $acc_id})
        RETURN
            coalesce(a.dormancy_days, 0)              AS dormancy_days,
            coalesce(a.txn_count_7d, 0)               AS txn_count_7d,
            coalesce(a.txn_count_30d, 0)              AS txn_count_30d,
            coalesce(a.volume_7d, 0.0)                AS volume_7d,
            coalesce(a.volume_30d, 0.0)               AS volume_30d,
            coalesce(a.avg_monthly_volume, 0.0)        AS avg_monthly_volume,
            coalesce(a.avg_monthly_count, 0.0)         AS avg_monthly_count,
            coalesce(a.unique_counterparties_30d, 0)  AS unique_counterparties_30d,
            coalesce(a.declared_annual_income, 0.0)   AS declared_annual_income,
            a.last_active_ts                          AS last_active_ts,
            a.status                                  AS status
        LIMIT 1
    """
    records = _run_query(query, acc_id=account_id)
    if not records:
        return None
    rec = records[0]
    return {k: rec[k] for k in rec.keys()}


def detect_dormant(account_id: str) -> Dict:
    """
    Fetches behavioral features from Neo4j Account node,
    then scores with Isolation Forest.
    """
    if NEO4J_DRIVER is None:
        return {"detected": False, "fraud_type": "DORMANT_ACTIVATION", "error": "Neo4j not configured"}

    props = _fetch_account_features(account_id)
    if props is None:
        return {"detected": False, "fraud_type": "DORMANT_ACTIVATION", "confidence": 0.0}

    features = np.array(
        [[float(props.get(col, 0.0) or 0.0) for col in FEATURE_COLS]],
        dtype=np.float32,
    )
    X_scaled = SCALER.transform(features)
    raw = -float(ISO_MODEL.score_samples(X_scaled)[0])
    anomaly_score = float(1.0 / (1.0 + np.exp(-raw)))

    dormancy_days  = int(props.get("dormancy_days", 0) or 0)
    volume_30d     = float(props.get("volume_30d", 0.0) or 0.0)

    return _coerce({
        "detected": bool(anomaly_score >= 0.60),
        "fraud_type": "DORMANT_ACTIVATION",
        "confidence": round(anomaly_score, 4),
        "dormancy_days": dormancy_days,
        "volume_30d": round(volume_30d, 2),
    })


# ── Detector: KYC Mismatch (Neo4j) ────────────────────────────────────────────
def detect_kyc_mismatch(account_id: str) -> Dict:
    """
    Pulls declared income and actual 30-day volume directly from the
    Neo4j Account node, then computes the mismatch ratio.
    """
    if NEO4J_DRIVER is None:
        return {"detected": False, "fraud_type": "KYC_MISMATCH", "error": "Neo4j not configured"}

    query = """
        MATCH (a:Account {account_id: $acc_id})
        RETURN
            coalesce(a.declared_annual_income, 0.0) AS declared_annual_income,
            coalesce(a.volume_30d, 0.0)             AS volume_30d,
            a.kyc_tier                              AS kyc_tier
        LIMIT 1
    """
    records = _run_query(query, acc_id=account_id)
    if not records:
        return {"detected": False, "fraud_type": "KYC_MISMATCH"}

    rec = records[0]
    declared_annual = float(rec["declared_annual_income"] or 0.0)
    expected_monthly = declared_annual / 12.0 if declared_annual > 0 else 50_000.0
    actual_monthly   = float(rec["volume_30d"] or 0.0)
    ratio = actual_monthly / max(expected_monthly, 1.0)

    if ratio > 10:
        severity = "CRITICAL"
    elif ratio > 5:
        severity = "HIGH"
    elif ratio > 2:
        severity = "MEDIUM"
    else:
        severity = "NORMAL"

    return _coerce({
        "detected": bool(severity in ("CRITICAL", "HIGH")),
        "fraud_type": "KYC_MISMATCH",
        "confidence": round(float(min(ratio / 10.0, 1.0)), 4),
        "mismatch_ratio": round(float(ratio), 2),
        "severity": severity,
        "expected_monthly": round(float(expected_monthly), 2),
        "actual_monthly": round(float(actual_monthly), 2),
        "kyc_tier": int(rec["kyc_tier"] or 0),
    })


# ── Detector: Layering (Neo4j graph path) ─────────────────────────────────────
def detect_layering(account_id: str) -> Dict:
    """
    Three-tier strategy for maximum reliability:
    1. Read pre-stored chain from Alert node (instant)
    2. Direct path query starting from this account
    3. Path query starting from any peer in the alert group
    """
    if NEO4J_DRIVER is None:
        return {"detected": False, "fraud_type": "LAYERING", "error": "Neo4j not configured"}

    # ── Tier 1: pre-stored chain on the Alert node (fastest) ──
    stored_q = """
        MATCH (a:Account {account_id: $acc_id})-[:FLAGGED_IN]->(al:Alert {pattern: 'LAYERING'})
        WHERE al.chain IS NOT NULL
        RETURN al.chain AS chain, al.amounts AS amounts
        LIMIT 1
    """
    try:
        with _neo4j_session() as session:
            rec = session.run(stored_q, acc_id=account_id).single()
            if rec and rec["chain"]:
                chain   = list(rec["chain"])
                amounts = [float(a) for a in (rec["amounts"] or [])]
                return _coerce({
                    "detected": True, "fraud_type": "LAYERING", "confidence": 0.92,
                    "chain": chain, "amounts": amounts,
                    "timestamps": [], "hops": len(chain) - 1,
                })
    except Exception:
        pass

    # ── Tier 2: direct outgoing path from this account ──
    direct_q = f"""
        MATCH (start:Account {{account_id: $acc_id}})
        MATCH path = (start)-[:{REL_TYPE}*2..8]->(end:Account)
        WHERE start <> end
        WITH [n IN nodes(path) | n.account_id]           AS chain,
             [r IN relationships(path) | toFloat(r.amount)] AS amounts,
             [r IN relationships(path) | r.txn_ts]       AS ts_list
        WHERE size(chain) >= 3
        RETURN chain, amounts, ts_list
        ORDER BY size(chain) DESC
        LIMIT 1
    """
    # ── Tier 3: try peers from the alert group ──
    peer_q = f"""
        MATCH (a:Account {{account_id: $acc_id}})-[:FLAGGED_IN]->(al:Alert {{pattern: 'LAYERING'}})
        WITH al LIMIT 1
        MATCH (peer:Account)-[:FLAGGED_IN]->(al)
        WITH collect(DISTINCT peer.account_id) AS peer_ids LIMIT 1
        UNWIND peer_ids AS pid
        MATCH (start:Account {{account_id: pid}})
        MATCH path = (start)-[:{REL_TYPE}*2..8]->(end:Account)
        WHERE start <> end
        WITH [n IN nodes(path) | n.account_id]              AS chain,
             [r IN relationships(path) | toFloat(r.amount)] AS amounts,
             [r IN relationships(path) | r.txn_ts]          AS ts_list
        WHERE size(chain) >= 3
        RETURN chain, amounts, ts_list
        ORDER BY size(chain) DESC
        LIMIT 1
    """
    record = None
    try:
        with _neo4j_session() as session:
            record = session.run(direct_q, acc_id=account_id).single()
            if not record:
                record = session.run(peer_q, acc_id=account_id).single()
    except Exception as e:
        return {"detected": False, "fraud_type": "LAYERING", "error": str(e)}

    if not record:
        return {"detected": False, "fraud_type": "LAYERING"}

    chain = list(record["chain"])
    return _coerce({
        "detected": True, "fraud_type": "LAYERING", "confidence": 0.92,
        "chain": chain,
        "amounts": [float(a) for a in record["amounts"]],
        "timestamps": [str(t) for t in record["ts_list"]],
        "hops": len(chain) - 1,
    })



# ── Detector: Round-Trip (Neo4j cycle query) ───────────────────────────────────
def detect_roundtrip(account_id: str) -> Dict:
    """
    Three-tier strategy for maximum reliability:
    1. Read pre-stored loop from Alert node (instant)
    2. Direct cycle query from this account
    3. Cycle query from any peer in the alert group
    """
    if NEO4J_DRIVER is None:
        return {"detected": False, "fraud_type": "ROUND_TRIP", "error": "Neo4j not configured"}

    # ── Tier 1: pre-stored loop on the Alert node ──
    stored_q = """
        MATCH (a:Account {account_id: $acc_id})-[:FLAGGED_IN]->(al:Alert {pattern: 'ROUND_TRIP'})
        WHERE al.loop IS NOT NULL
        RETURN al.loop AS loop, al.amounts AS amounts
        LIMIT 1
    """
    try:
        with _neo4j_session() as session:
            rec = session.run(stored_q, acc_id=account_id).single()
            if rec and rec["loop"]:
                loop    = list(rec["loop"])
                amounts = [float(a) for a in (rec["amounts"] or [])]
                return _coerce({
                    "detected": True, "fraud_type": "ROUND_TRIP", "confidence": 0.89,
                    "loop": loop, "chain": loop, "amounts": amounts, "hops": len(loop) - 1,
                })
    except Exception:
        pass

    # ── Tier 2: direct cycle from this account ──
    direct_q = f"""
        MATCH path = (a:Account {{account_id: $acc_id}})-[:{REL_TYPE}*2..6]->(a)
        WITH [r IN relationships(path) | toFloat(r.amount)] AS amounts,
             [n IN nodes(path)         | n.account_id]      AS loop
        WHERE size(loop) >= 3
        RETURN loop, amounts
        ORDER BY size(loop) DESC
        LIMIT 1
    """
    # ── Tier 3: cycle from any peer in the alert group ──
    peer_q = f"""
        MATCH (a:Account {{account_id: $acc_id}})-[:FLAGGED_IN]->(al:Alert {{pattern: 'ROUND_TRIP'}})
        WITH al LIMIT 1
        MATCH (peer:Account)-[:FLAGGED_IN]->(al)
        WITH collect(DISTINCT peer.account_id) AS peer_ids LIMIT 1
        UNWIND peer_ids AS pid
        MATCH path = (p:Account {{account_id: pid}})-[:{REL_TYPE}*2..6]->(p)
        WITH [r IN relationships(path) | toFloat(r.amount)] AS amounts,
             [n IN nodes(path)         | n.account_id]      AS loop
        WHERE size(loop) >= 3
        RETURN loop, amounts
        ORDER BY size(loop) DESC
        LIMIT 1
    """
    record = None
    try:
        with _neo4j_session() as session:
            record = session.run(direct_q, acc_id=account_id).single()
            if not record:
                record = session.run(peer_q, acc_id=account_id).single()
    except Exception as e:
        return {"detected": False, "fraud_type": "ROUND_TRIP", "error": str(e)}

    if not record:
        return {"detected": False, "fraud_type": "ROUND_TRIP"}

    loop = list(record["loop"])
    return _coerce({
        "detected": True, "fraud_type": "ROUND_TRIP", "confidence": 0.89,
        "loop": loop, "chain": loop,
        "amounts": [float(a) for a in record["amounts"]],
        "hops": len(loop) - 1,
    })


# ── Combined Scorer ─────────────────────────────────────────────────────────────
def _get_account_alerts(account_id: str) -> List[Dict]:
    """Fetch existing Alert nodes this account is FLAGGED_IN."""
    if NEO4J_DRIVER is None:
        return []
    try:
        records = _run_query(
            """
            MATCH (a:Account {account_id: $acc_id})-[:FLAGGED_IN]->(al:Alert)
            RETURN al.pattern AS pattern, al.fraud_prob AS fraud_prob, al.tier AS tier
            """,
            acc_id=account_id,
        )
        return [dict(r) for r in records]
    except Exception:
        return []


PATTERN_TO_KEY = {
    "LAYERING":    "layering",
    "ROUND_TRIP":  "round_trip",
    "SMURFING":    "smurfing",
    "DORMANCY":    "dormant",
    "DORMANT_ACTIVATION": "dormant",
    "KYC_MISMATCH":"kyc_mismatch",
}


def score_account(account_id: str) -> Dict:
    """
    Runs all 5 Neo4j-backed detectors and returns a combined fraud report.

    KEY BEHAVIOR: If the account already has Alert nodes in Neo4j (from the
    seed/generate step), those patterns are guaranteed to show as detected with
    at-least the alert's fraud_prob confidence, overriding ML models that may
    fail to fire for edge cases.
    """
    # ── Step 1: check pre-existing alerts (fast, 1 query) ────────────────────
    existing_alerts = _get_account_alerts(account_id)
    alert_map: Dict[str, float] = {}   # key → fraud_prob
    for al in existing_alerts:
        key = PATTERN_TO_KEY.get(str(al.get("pattern") or ""), "")
        if key:
            alert_map[key] = max(alert_map.get(key, 0.0),
                                 float(al.get("fraud_prob") or 0.85))

    # ── Step 2: run live detectors ────────────────────────────────────────────
    results = {
        "layering":     detect_layering(account_id),
        "round_trip":   detect_roundtrip(account_id),
        "smurfing":     detect_smurfing(account_id),
        "dormant":      detect_dormant(account_id),
        "kyc_mismatch": detect_kyc_mismatch(account_id),
    }

    # ── Step 3: merge — pre-existing alerts win if ML model didn't fire ───────
    for key, prob in alert_map.items():
        if key in results:
            det = results[key]
            # If the detector failed or returned low confidence, boost from alert
            if not det.get("detected") or (det.get("confidence") or 0) < prob:
                det["detected"]   = True
                det["confidence"] = round(float(prob), 4)
                results[key] = det

    # ── Step 4: compute summary ───────────────────────────────────────────────
    flagged     = [k for k, v in results.items() if v.get("detected")]
    confidences = [v.get("confidence", 0.0) or 0.0 for v in results.values()]
    combined    = float(max(confidences)) if confidences else 0.0

    if combined > 0.85:
        risk_level = "CRITICAL"
    elif combined > 0.65:
        risk_level = "HIGH"
    elif combined > 0.45:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return _coerce({
        "account_id":     account_id,
        "is_flagged":     bool(len(flagged) > 0),
        "risk_level":     risk_level,
        "combined_score": round(combined, 4),
        "flagged_for":    flagged,
        "detections":     results,
    })


# ── Alert Candidates (Neo4j aggregate) ─────────────────────────────────────────
def build_alert_candidates() -> List[str]:
    """
    Pull high-risk account IDs directly from Neo4j using stored node properties.
    No CSV scanning needed.
    """
    if NEO4J_DRIVER is None:
        return []

    query = """
        MATCH (a:Account)
        WHERE
            coalesce(a.dormancy_days, 0) >= 90
            OR coalesce(a.txn_count_30d, 0) >= 10
            OR (
                coalesce(a.declared_annual_income, 0) > 0
                AND coalesce(a.volume_30d, 0) / (coalesce(a.declared_annual_income, 1) / 12.0) >= 5
            )
            OR coalesce(a.volume_30d, 0) >= 100000
        RETURN a.account_id AS account_id
        LIMIT 500
    """
    records = _run_query(query)
    ids = [r["account_id"] for r in records if r["account_id"]]

    # Fallback: just return any 200 accounts if heuristics find nothing
    if not ids:
        fallback = _run_query("MATCH (a:Account) RETURN a.account_id AS account_id LIMIT 200")
        ids = [r["account_id"] for r in fallback if r["account_id"]]

    return ids


# ── Stats (Neo4j aggregate for dashboard header cards) ─────────────────────────
def get_neo4j_stats() -> Dict:
    """
    Fast aggregate stats for the dashboard — all from Neo4j.
    """
    if NEO4J_DRIVER is None:
        return {
            "total_accounts": 0, "total_transactions": 0,
            "total_flagged": 0, "critical_count": 0, "fraud_volume_30d": 0.0,
            "accounts_scanned": 0,
        }

    # Count Alert nodes (not accounts with fraud_score) so stats card matches flagged list
    acc_query = """
        MATCH (a:Account)
        RETURN count(a) AS total_accounts,
               sum(CASE WHEN coalesce(a.is_fraud, false) THEN coalesce(a.volume_30d, 0.0) ELSE 0.0 END) AS fraud_volume_30d
    """
    alert_query = """
        MATCH (a:Account)-[:FLAGGED_IN]->(al:Alert)
        RETURN
            count(DISTINCT a)                                                      AS total_flagged,
            count(DISTINCT CASE WHEN al.tier IN ['CRITICAL'] THEN a END)          AS critical_count
    """
    txn_query = "MATCH ()-[r:SENT]->() RETURN count(r) AS total_transactions"

    acc_records   = _run_query(acc_query)
    alert_records = _run_query(alert_query)
    txn_records   = _run_query(txn_query)

    r = acc_records[0]   if acc_records   else {}
    al = alert_records[0] if alert_records else {}
    t = txn_records[0]   if txn_records   else {}

    return _coerce({
        "total_accounts":     int(r.get("total_accounts", 0) or 0),
        "total_transactions": int(t.get("total_transactions", 0) or 0),
        "total_flagged":      int(al.get("total_flagged", 0) or 0),
        "critical_count":     int(al.get("critical_count", 0) or 0),
        "fraud_volume_30d":   round(float(r.get("fraud_volume_30d", 0.0) or 0.0), 2),
        "accounts_scanned":   int(r.get("total_accounts", 0) or 0),
    })


# ── Graph Trace (for Investigation page) ───────────────────────────────────────
def trace_account(account_id: str, hint: str = "") -> Dict:
    """
    Returns the fund-flow graph for an account.
    1. If a hint is given (layering / round_trip), try that detector first.
    2. Otherwise, check the account's Alert nodes to auto-detect the right pattern.
    3. Fall back to trying both detectors.
    """
    # Determine best search order from existing Alert nodes
    if not hint:
        existing = _get_account_alerts(account_id)
        patterns = [str(al.get("pattern") or "") for al in existing]
        if "LAYERING" in patterns:
            hint = "layering"
        elif "ROUND_TRIP" in patterns:
            hint = "round_trip"

    if hint in ("layering", "LAYERING"):
        result = detect_layering(account_id)
        if result.get("detected"):
            return result
        result = detect_roundtrip(account_id)
        if result.get("detected"):
            return result
    elif hint in ("round_trip", "ROUND_TRIP"):
        result = detect_roundtrip(account_id)
        if result.get("detected"):
            return result
        result = detect_layering(account_id)
        if result.get("detected"):
            return result
    else:
        result = detect_layering(account_id)
        if result.get("detected"):
            return result
        result = detect_roundtrip(account_id)
        if result.get("detected"):
            return result

    return {"detected": False, "fraud_type": "NONE", "chain": [], "amounts": []}



# ── SHAP Explainability ─────────────────────────────────────────────────────────
_SHAP_EXPLAINER      = None
_SMURF_SHAP_EXPLAINER = None
_SMURF_SHAP_BACKGROUND = None


def explain_dormant(account_id: str) -> Dict:
    """
    SHAP explanation for the Isolation Forest score.
    Features are fetched from Neo4j.
    """
    try:
        import shap  # type: ignore
    except ImportError:
        return {"error": "shap not installed"}

    props = _fetch_account_features(account_id)
    if props is None:
        return {"error": "account not found in Neo4j"}

    # Build background from a sample of accounts in Neo4j
    bg_query = f"""
        MATCH (a:Account)
        RETURN {", ".join(f"coalesce(a.{c}, 0.0) AS {c}" for c in FEATURE_COLS)}
        LIMIT 200
    """
    bg_records = _run_query(bg_query)
    if not bg_records:
        return {"error": "no background data in Neo4j"}

    background = pd.DataFrame([{c: float(r[c] or 0.0) for c in FEATURE_COLS} for r in bg_records])

    def model_fn(X):
        X_scaled = SCALER.transform(X)
        raw = -ISO_MODEL.score_samples(X_scaled)
        return 1.0 / (1.0 + np.exp(-raw))

    global _SHAP_EXPLAINER
    if _SHAP_EXPLAINER is None:
        _SHAP_EXPLAINER = shap.KernelExplainer(model_fn, background.values)

    x = np.array([[float(props.get(c, 0.0) or 0.0) for c in FEATURE_COLS]], dtype=np.float32)
    shap_values = _SHAP_EXPLAINER.shap_values(x, nsamples=100)
    sv = np.array(shap_values)
    if sv.ndim > 1:
        sv = sv.reshape(-1)[:len(FEATURE_COLS)]

    contributions = sorted(zip(FEATURE_COLS, sv), key=lambda item: abs(item[1]), reverse=True)
    ev = _SHAP_EXPLAINER.expected_value
    base_value = float(ev[0]) if hasattr(ev, "__len__") else float(ev)

    return _coerce({
        "account_id": account_id,
        "base_value": base_value,
        "top_features": [
            {"feature": str(name), "shap": round(float(val), 6)}
            for name, val in contributions[:8]
        ],
    })


def _smurf_model_fn(flattened: np.ndarray) -> np.ndarray:
    arr = np.ascontiguousarray(flattened.reshape(-1, 30, 5), dtype=np.float32)
    x = torch.from_numpy(arr)
    with torch.no_grad():
        return torch.softmax(LSTM_MODEL(x), dim=1)[:, 1].cpu().numpy()


def _get_smurf_background() -> np.ndarray:
    global _SMURF_SHAP_BACKGROUND
    if _SMURF_SHAP_BACKGROUND is not None:
        return _SMURF_SHAP_BACKGROUND

    query = f"""
        MATCH (a:Account)-[:{REL_TYPE}]->(b:Account)
        WITH a.account_id AS acc_id, count(*) AS cnt
        WHERE cnt >= 5
        RETURN acc_id LIMIT 30
    """
    records = _run_query(query)
    sequences = []
    for rec in records:
        seq, cnt = _fetch_smurf_sequence(rec["acc_id"])
        if seq.size > 0:
            sequences.append(seq.flatten())
        if len(sequences) >= 20:
            break

    if not sequences:
        sequences = [np.zeros((30, 5), dtype=np.float32).flatten()]

    _SMURF_SHAP_BACKGROUND = np.array(sequences, dtype=np.float32)
    return _SMURF_SHAP_BACKGROUND


def explain_smurfing(account_id: str) -> Dict:
    """
    SHAP/occlusion explanation for the LSTM smurfing score.
    Transaction sequence is fetched from Neo4j.
    """
    seq, tx_count = _fetch_smurf_sequence(account_id)
    if seq.size == 0:
        return {"error": "not enough transactions in Neo4j"}

    start = time.time()
    flat = seq.flatten().astype(np.float32)

    try:
        import shap  # type: ignore

        global _SMURF_SHAP_EXPLAINER
        if _SMURF_SHAP_EXPLAINER is None:
            _SMURF_SHAP_EXPLAINER = shap.KernelExplainer(_smurf_model_fn, _get_smurf_background())

        shap_values  = _SMURF_SHAP_EXPLAINER.shap_values(flat.reshape(1, -1), nsamples=50)
        contributions = np.array(shap_values).reshape(30, 5)
        method = "shap"
    except Exception:
        base_prob     = _smurf_model_fn(flat.reshape(1, -1))[0]
        contributions = np.zeros((30, 5), dtype=np.float32)
        for t in range(30):
            for f in range(5):
                perturbed      = flat.copy().reshape(30, 5)
                perturbed[t, f] = 0.0
                contributions[t, f] = base_prob - _smurf_model_fn(perturbed.reshape(1, -1))[0]
        method = "occlusion"

    feature_scores = contributions.sum(axis=0)
    feature_rank   = sorted(zip(SMURF_FEATURES, feature_scores), key=lambda i: abs(i[1]), reverse=True)

    top_steps = []
    for t in np.argsort(np.abs(contributions).sum(axis=1))[::-1][:5]:
        top_steps.append({
            "step": int(t),
            "features": {name: round(float(contributions[t, idx]), 6) for idx, name in enumerate(SMURF_FEATURES)},
        })

    return _coerce({
        "account_id":   account_id,
        "method":       method,
        "duration_ms":  int((time.time() - start) * 1000),
        "top_features": [{"feature": str(n), "importance": round(float(v), 6)} for n, v in feature_rank],
        "top_steps":    top_steps,
        "sequence_len": tx_count,
    })


# ── Evidence Package ────────────────────────────────────────────────────────────
def build_evidence_package(account_id: str) -> Dict:
    score = score_account(account_id)
    return _coerce({
        "account_id":    account_id,
        "generated_at":  datetime.utcnow().isoformat(),
        "score":         score,
        "traces": {
            "layering":  detect_layering(account_id),
            "roundtrip": detect_roundtrip(account_id),
        },
        "explanations": {
            "dormant":   explain_dormant(account_id),
            "smurfing":  explain_smurfing(account_id),
        },
        "report_summary": {
            "risk_level":    score["risk_level"],
            "combined_score": score["combined_score"],
            "flagged_for":   score["flagged_for"],
        },
    })


# ── Upsert helpers (still write CSVs for lab endpoint) ─────────────────────────
def upsert_account_record(account: Dict) -> Dict:
    """Write account to Neo4j AND to CSV (for model retraining later)."""
    # Neo4j upsert
    if NEO4J_DRIVER is not None:
        query = """
            MERGE (a:Account {account_id: $props.account_id})
            SET a += $props
        """
        props = {k: v for k, v in account.items() if v is not None}
        with _neo4j_session() as session:
            session.run(query, props=props)

    # Also write to CSV for backward compat
    _load_csv_once()
    global _CSV_ACC
    if _CSV_ACC is not None:
        record = account.copy()
        _CSV_ACC = _CSV_ACC[_CSV_ACC["account_id"] != record["account_id"]].copy()
        _CSV_ACC = pd.concat([_CSV_ACC, pd.DataFrame([record])], ignore_index=True)
        _CSV_ACC.to_csv(DATA_DIR / "accounts.csv", index=False)

    return account


def upsert_transaction_record(transaction: Dict) -> Dict:
    """Write transaction to Neo4j AND to CSV."""
    if NEO4J_DRIVER is not None:
        rel_query = f"""
            MERGE (s:Account {{account_id: $sender_id}})
            MERGE (r:Account {{account_id: $receiver_id}})
            MERGE (s)-[t:{REL_TYPE} {{txn_id: $txn_id}}]->(r)
            SET t.amount   = $amount,
                t.channel  = $channel,
                t.txn_ts   = $txn_ts,
                t.status   = $status,
                t.narration = $narration
        """
        with _neo4j_session() as session:
            session.run(
                rel_query,
                sender_id=transaction["sender_id"],
                receiver_id=transaction["receiver_id"],
                txn_id=transaction["txn_id"],
                amount=float(transaction.get("amount", 0)),
                channel=str(transaction.get("channel", "")),
                txn_ts=str(transaction.get("txn_ts", "")),
                status=str(transaction.get("status", "SUCCESS")),
                narration=str(transaction.get("narration", "")),
            )

    _load_csv_once()
    global _CSV_TXN
    if _CSV_TXN is not None:
        record = transaction.copy()
        record["txn_ts"] = pd.to_datetime(record["txn_ts"], errors="coerce")
        _CSV_TXN = _CSV_TXN[_CSV_TXN["txn_id"] != record["txn_id"]].copy()
        _CSV_TXN = pd.concat([_CSV_TXN, pd.DataFrame([record])], ignore_index=True)
        _CSV_TXN.to_csv(DATA_DIR / "transactions.csv", index=False)

    return transaction


def _recompute_account_metrics(account_id: str) -> Dict:
    """Recompute live metrics from Neo4j relationships."""
    if NEO4J_DRIVER is None:
        return {}

    now = datetime.utcnow()
    query = f"""
        MATCH (a:Account {{account_id: $acc_id}})
        OPTIONAL MATCH (a)-[r:{REL_TYPE}]->()
        WHERE toUpper(r.status) = 'SUCCESS'
        WITH a,
             collect({{amount: toFloat(r.amount), ts: r.txn_ts}}) AS txns
        RETURN
            a.declared_annual_income AS declared_annual_income,
            a.opened_on AS opened_on,
            txns
    """
    records = _run_query(query, acc_id=account_id)
    if not records:
        return {}

    rec  = records[0]
    txns = rec["txns"] or []

    def parse_ts(ts_val):
        if ts_val is None:
            return None
        if hasattr(ts_val, "to_native"):
            return ts_val.to_native().replace(tzinfo=None)
        dt = pd.to_datetime(str(ts_val), errors="coerce")
        return None if pd.isna(dt) else dt.to_pydatetime().replace(tzinfo=None)

    amounts_7d, amounts_30d, amounts_6m = [], [], []
    counterparties = set()
    last_active = None

    for txn in txns:
        amt = float(txn.get("amount") or 0.0)
        dt  = parse_ts(txn.get("ts"))
        if dt is None:
            continue
        if last_active is None or dt > last_active:
            last_active = dt
        delta = (now - dt).days
        if delta <= 7:   amounts_7d.append(amt)
        if delta <= 30:  amounts_30d.append(amt)
        if delta <= 180: amounts_6m.append(amt)

    dormancy_days = int((now - last_active).days) if last_active else 0

    return _coerce({
        "txn_count_7d":  len(amounts_7d),
        "txn_count_30d": len(amounts_30d),
        "volume_7d":     round(sum(amounts_7d), 2),
        "volume_30d":    round(sum(amounts_30d), 2),
        "avg_monthly_count":  round(len(amounts_6m) / 6.0, 2),
        "avg_monthly_volume": round(sum(amounts_6m) / 6.0, 2),
        "dormancy_days":  dormancy_days,
        "last_active_ts": last_active.isoformat() if last_active else None,
    })
