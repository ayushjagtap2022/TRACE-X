import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

ROOT_DIR = Path(__file__).resolve().parents[4]
PY_SCHEMAS_DIR = ROOT_DIR / "packages" / "py-schemas"
AI_ML_DIR      = ROOT_DIR / "apps" / "ai-ml"

for path in (PY_SCHEMAS_DIR, AI_ML_DIR):
    if str(path) not in sys.path:
        sys.path.append(str(path))

from app.db.session import get_db
from fraud_detector import (  # type: ignore[import-not-found]
    REL_TYPE,
    NEO4J_DRIVER,
    _coerce,
    _recompute_account_metrics,
    build_alert_candidates,
    build_evidence_package,
    detect_layering,
    detect_roundtrip,
    explain_dormant,
    explain_smurfing,
    get_neo4j_stats,
    refresh_data,
    score_account,
    trace_account,
    upsert_account_record,
    upsert_transaction_record,
)
from trace_x_schemas.models import Account, Transaction

router = APIRouter(tags=["fraud"])


def _driver():
    return get_db()


# ── Stats ──────────────────────────────────────────────────────────────────────
@router.get("/stats")
def get_stats():
    """
    Fast aggregate stats for the dashboard header cards.
    All data comes from Neo4j — no CSV reads.
    """
    return _coerce(get_neo4j_stats())


# ── Score ──────────────────────────────────────────────────────────────────────
@router.get("/score/{account_id}")
def get_score(account_id: str):
    try:
        return _coerce(score_account(account_id))
    except Exception as e:
        print(f"score_account error for {account_id}: {e}")
        return _coerce({
            "account_id": account_id,
            "is_flagged": False,
            "risk_level": "LOW",
            "combined_score": 0.0,
            "flagged_for": [],
            "detections": {
                "layering":     {"detected": False, "fraud_type": "LAYERING",    "error": str(e)},
                "round_trip":   {"detected": False, "fraud_type": "ROUND_TRIP",  "error": str(e)},
                "smurfing":     {"detected": False, "fraud_type": "SMURFING",    "error": str(e)},
                "dormant":      {"detected": False, "fraud_type": "DORMANCY",    "error": str(e)},
                "kyc_mismatch": {"detected": False, "fraud_type": "KYC_MISMATCH","error": str(e)},
            },
            "error": str(e),
        })


# ── Alerts (full ML scoring - slow) ────────────────────────────────────────────
@router.get("/alerts")
def get_alerts(limit: int = 50):
    candidates = build_alert_candidates()
    score_limit = min(len(candidates), limit * 3)
    candidates  = candidates[:score_limit]

    alerts: List[Dict[str, Any]] = []
    for account_id in candidates:
        try:
            report = score_account(account_id)
        except Exception:
            continue
        if report["is_flagged"]:
            alerts.append(_coerce({
                "account_id": account_id,
                "risk_level": report["risk_level"],
                "flagged_for": report["flagged_for"],
                "score": report["combined_score"],
                "detections": report["detections"],
            }))

    alerts.sort(key=lambda item: item["score"], reverse=True)
    return _coerce({"total": len(alerts), "alerts": alerts[:limit]})


# ── Alerts Quick (reads Alert nodes directly from Neo4j — instant) ──────────────
@router.get("/alerts/quick")
def get_alerts_quick(limit: int = 200):
    """
    Reads pre-generated Alert nodes from Neo4j.
    Instant — no ML inference. Used by the dashboard.
    """
    if NEO4J_DRIVER is None:
        return {"total": 0, "alerts": []}

    query = """
        MATCH (a:Account)-[:FLAGGED_IN]->(al:Alert)
        RETURN
            a.account_id                           AS account_id,
            al.pattern                             AS pattern,
            al.fraud_prob                          AS fraud_prob,
            al.tier                                AS tier,
            al.total_amount                        AS total_amount,
            al.status                              AS status,
            coalesce(a.fraud_score, al.fraud_prob) AS score,
            coalesce(a.volume_30d, 0.0)            AS volume_30d,
            coalesce(a.dormancy_days, 0)           AS dormancy_days
    """
    try:
        with NEO4J_DRIVER.session() as session:
            records = list(session.run(query))
    except Exception as e:
        print(f"Neo4j Error: {e}")
        return {"total": 0, "alerts": [], "error": str(e)}

    PATTERN_RISK = {
        "LAYERING": "CRITICAL", "ROUND_TRIP": "CRITICAL",
        "SMURFING": "HIGH",     "KYC_MISMATCH": "HIGH",
        "DORMANCY": "MEDIUM",
    }
    PATTERN_KEY = {
        "LAYERING": "layering",   "ROUND_TRIP": "round_trip",
        "SMURFING": "smurfing",   "KYC_MISMATCH": "kyc_mismatch",
        "DORMANCY": "dormant",
    }

    seen: set = set()
    alerts: List[Dict[str, Any]] = []
    for rec in records:
        acc_id  = rec["account_id"]
        pattern = str(rec["pattern"] or "")
        key     = PATTERN_KEY.get(pattern, pattern.lower())
        score   = float(rec["score"] or 0.85)
        tier    = PATTERN_RISK.get(pattern, "HIGH")
        dedup   = f"{acc_id}-{pattern}"
        if dedup in seen:
            continue
        seen.add(dedup)
        alerts.append(_coerce({
            "account_id":  acc_id,
            "risk_level":  tier,
            "flagged_for": [key],
            "score":       round(score, 4),
            "total_amount": float(rec["total_amount"] or 0),
            "detections":  {key: {"detected": True, "confidence": round(score, 4)}},
        }))

    # Sort in memory: CRITICAL > HIGH > MEDIUM, then score, then amount
    def sort_key(a):
        tier_val = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1}.get(a["risk_level"], 0)
        return (tier_val, a["score"], a["total_amount"])
    
    alerts.sort(key=sort_key, reverse=True)

    return _coerce({"total": len(alerts), "alerts": alerts[:limit]})


# ── Trace (graph path for investigation page) ──────────────────────────────────
@router.get("/trace/{account_id}")
def get_trace(account_id: str, hint: str = ""):
    """Returns layering chain or round-trip loop for the investigation graph.
    hint: 'layering' or 'round_trip' — forces search for that specific pattern."""
    try:
        # If a hint is provided, try that detector first
        if hint in ("layering", "LAYERING"):
            result = detect_layering(account_id)
            if not result.get("detected"):
                result = detect_roundtrip(account_id)
        elif hint in ("round_trip", "ROUND_TRIP"):
            result = detect_roundtrip(account_id)
            if not result.get("detected"):
                result = detect_layering(account_id)
        else:
            result = trace_account(account_id)
        return _coerce(result)
    except Exception as e:
        print(f"Neo4j Trace Error: {e}")
        return {"detected": False, "fraud_type": "NONE", "chain": [], "amounts": [], "error": str(e)}


# ── Live Feed (real transactions from Neo4j) ───────────────────────────────────
@router.get("/feed")
def get_live_feed(limit: int = 30):
    """
    Returns the most recent transactions from Neo4j for the live feed.
    Each row includes whether the sender account is flagged.
    """
    if NEO4J_DRIVER is None:
        return {"transactions": []}

    query = f"""
        MATCH (sender:Account)-[r:{REL_TYPE}]->(receiver:Account)
        WHERE r.txn_ts IS NOT NULL
        RETURN
            sender.account_id           AS account_id,
            toFloat(r.amount)           AS amount,
            toUpper(r.channel)          AS channel,
            toString(r.txn_ts)          AS txn_ts,
            toUpper(r.status)           AS status,
            coalesce(sender.fraud_score, 0.0)  AS fraud_score,
            coalesce(sender.is_fraud, false)   AS is_fraud
        ORDER BY r.txn_ts DESC
        LIMIT $limit
    """
    with NEO4J_DRIVER.session() as session:
        records = list(session.run(query, limit=limit))

    rows = []
    for rec in records:
        rows.append(_coerce({
            "account_id": rec["account_id"],
            "amount": float(rec["amount"] or 0),
            "channel": str(rec["channel"] or ""),
            "txn_ts": str(rec["txn_ts"] or ""),
            "status": str(rec["status"] or ""),
            "fraud_score": float(rec["fraud_score"] or 0.0),
            "is_flagged": bool(rec["is_fraud"]),
        }))

    return {"transactions": rows}


# ── Report ─────────────────────────────────────────────────────────────────────
@router.get("/report/{account_id}")
def get_report(account_id: str):
    return _coerce(build_evidence_package(account_id))


# ── Explainability ─────────────────────────────────────────────────────────────
@router.get("/explain/dormant/{account_id}")
def get_dormant_explanation(account_id: str):
    return _coerce(explain_dormant(account_id))


@router.get("/explain/smurfing/{account_id}")
def get_smurfing_explanation(account_id: str):
    return _coerce(explain_smurfing(account_id))


@router.get("/explain/{account_id}")
def get_full_explanation(account_id: str):
    return _coerce({
        "account_id": account_id,
        "dormant":   explain_dormant(account_id),
        "smurfing":  explain_smurfing(account_id),
    })


@router.get("/narrative/{account_id}")
def get_narrative(account_id: str):
    from app.services.genai_explain import generate_narrative
    return _coerce(generate_narrative(account_id))


# ── Lab: Create Account ────────────────────────────────────────────────────────
@router.post("/accounts")
def create_account(account: Account):
    record = account.model_dump()
    # upsert_account_record now writes to Neo4j AND CSV
    upsert_account_record(record)
    refresh_data()
    return {"message": "account created", "account": record}


# ── Lab: Create Transaction ────────────────────────────────────────────────────
@router.post("/transactions")
def create_transaction(transaction: Transaction):
    record = transaction.model_dump()

    # Verify both accounts exist in Neo4j
    driver = _driver()
    with driver.session() as session:
        sender = session.run(
            "MATCH (a:Account {account_id: $id}) RETURN a.account_id AS id",
            id=record["sender_id"],
        ).single()
        receiver = session.run(
            "MATCH (a:Account {account_id: $id}) RETURN a.account_id AS id",
            id=record["receiver_id"],
        ).single()

    if not sender or not receiver:
        raise HTTPException(status_code=404, detail="sender or receiver account not found in Neo4j")

    # Write the transaction (Neo4j + CSV)
    upsert_transaction_record(record)

    # Recompute live metrics from Neo4j relationships
    sender_updates   = _recompute_account_metrics(record["sender_id"])
    receiver_updates = _recompute_account_metrics(record["receiver_id"])

    sender_score   = score_account(record["sender_id"])
    receiver_score = score_account(record["receiver_id"])

    # Update account nodes in Neo4j with fresh metrics
    for acc_id, updates, score in [
        (record["sender_id"],   sender_updates,   sender_score),
        (record["receiver_id"], receiver_updates, receiver_score),
    ]:
        merged = {
            "account_id":    acc_id,
            **updates,
            "fraud_score":   score["combined_score"],
            "is_fraud":      score["is_flagged"],
            "last_scored_ts": datetime.utcnow().isoformat(),
        }
        upsert_account_record(merged)

    response = {
        "message": "transaction created",
        "transaction": record,
        "impacted_accounts": [
            {"account_id": record["sender_id"],   "score": sender_score},
            {"account_id": record["receiver_id"], "score": receiver_score},
        ],
    }

    if sender_score["is_flagged"] or receiver_score["is_flagged"]:
        response["evidence"] = {
            record["sender_id"]:   build_evidence_package(record["sender_id"]),
            record["receiver_id"]: build_evidence_package(record["receiver_id"]),
        }

    return _coerce(response)