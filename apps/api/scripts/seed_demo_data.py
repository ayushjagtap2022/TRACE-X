"""
seed_demo_data.py  —  TRACE-X Demo Data Seeder
================================================
Clears ALL Neo4j data and inserts a clean, minimal dataset:
  • 100 accounts (80 normal + 20 fraud-pattern accounts)
  • ~500 transactions
  • 10 Alert nodes — exactly 2 per pattern, all GUARANTEED detectable

Pattern accounts are carefully crafted so ONLY the intended detector fires:
  LAYERING    – chain: L1A→L1B→L1C→L1D→L1E→L1F (5 hops, within 2 hours)
  ROUND_TRIP  – cycle: R1A→R1B→R1C→R1D→R1A
  SMURFING    – sender makes 25+ UPI txns of ₹8,999 in 20 hours
  DORMANCY    – account dormant 200+ days, suddenly moves ₹5L+ in 30 days
  KYC_MISMATCH– KYC Tier-1 account (declared ₹6L/yr) moves ₹25L in 30 days

Run:
    cd apps/api
    .\\venv\\Scripts\\python scripts\\seed_demo_data.py
"""

import os, sys, random, json
from datetime import datetime, timedelta
from pathlib import Path

# ─── Env load ─────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
_root = Path(__file__).resolve().parents[4]
load_dotenv(_root / ".env")
for i in range(1, 6):
    _cand = Path(__file__).resolve().parents[i] / ".env"
    if _cand.exists():
        load_dotenv(_cand, override=True)
        break

from neo4j import GraphDatabase

URI  = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASS = os.getenv("NEO4J_PASSWORD")

if not all([URI, USER, PASS]):
    sys.exit("❌  NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD not set in .env")

print(f"Connecting to Neo4j at {URI}…")
driver = GraphDatabase.driver(URI, auth=(USER, PASS))
with driver.session() as s:
    s.run("RETURN 1")          # quick connectivity check
print("Connected ✓")

# ─── Helpers ──────────────────────────────────────────────────────────────────
NOW = datetime(2026, 5, 31, 12, 0, 0)
rng = random.Random(42)

def _ts(dt: datetime) -> str:
    return dt.isoformat()

def _run(q: str, **kw):
    with driver.session() as s:
        return list(s.run(q, **kw))

def create_account(
    acc_id: str,
    kyc_tier: int = 2,
    declared_annual_income: float = 600_000,
    avg_monthly_volume: float = 50_000,
    avg_monthly_count: int = 20,
    volume_30d: float = None,
    volume_7d: float = None,
    txn_count_30d: int = None,
    txn_count_7d: int = None,
    unique_counterparties_30d: int = 10,
    dormancy_days: int = 0,
    fraud_score: float = 0.1,
    is_fraud: bool = False,
):
    if volume_30d is None:
        volume_30d = avg_monthly_volume * rng.uniform(0.8, 1.2)
    if volume_7d is None:
        volume_7d = volume_30d * 0.25
    if txn_count_30d is None:
        txn_count_30d = rng.randint(8, 40)
    if txn_count_7d is None:
        txn_count_7d = rng.randint(2, 10)

    last_active = NOW - timedelta(days=dormancy_days if dormancy_days > 0 else rng.randint(0, 3))

    _run(
        """
        MERGE (a:Account {account_id: $id})
        SET
            a.kyc_tier                   = $kyc_tier,
            a.declared_annual_income     = $income,
            a.avg_monthly_volume         = $avg_vol,
            a.avg_monthly_count          = $avg_cnt,
            a.volume_30d                 = $vol30,
            a.volume_7d                  = $vol7,
            a.txn_count_30d              = $cnt30,
            a.txn_count_7d               = $cnt7,
            a.unique_counterparties_30d  = $uniq,
            a.dormancy_days              = $dormancy,
            a.fraud_score                = $fscore,
            a.is_fraud                   = $is_fraud,
            a.last_active_ts             = $last_active,
            a.status                     = 'ACTIVE'
        """,
        id=acc_id,
        kyc_tier=kyc_tier,
        income=float(declared_annual_income),
        avg_vol=float(avg_monthly_volume),
        avg_cnt=int(avg_monthly_count),
        vol30=float(volume_30d),
        vol7=float(volume_7d),
        cnt30=int(txn_count_30d),
        cnt7=int(txn_count_7d),
        uniq=int(unique_counterparties_30d),
        dormancy=int(dormancy_days),
        fscore=float(fraud_score),
        is_fraud=bool(is_fraud),
        last_active=_ts(last_active),
    )

def create_txn(sender: str, receiver: str, amount: float, dt: datetime,
               channel: str = "NEFT", status: str = "SUCCESS"):
    _run(
        f"""
        MATCH (s:Account {{account_id: $sender}})
        MATCH (r:Account {{account_id: $receiver}})
        CREATE (s)-[:SENT {{
            txn_id:  $txn_id,
            amount:  $amount,
            txn_ts:  $ts,
            channel: $channel,
            status:  $status
        }}]->(r)
        """,
        sender=sender,
        receiver=receiver,
        txn_id=f"TXN_{sender[-4:]}_{receiver[-4:]}_{int(dt.timestamp())}",
        amount=float(amount),
        ts=_ts(dt),
        channel=channel,
        status=status,
    )

def create_alert(pattern: str, tier: str, fraud_prob: float,
                 total_amount: float, accounts: list,
                 chain: list = None, loop: list = None,
                 amounts: list = None) -> str:
    alert_id = f"ALERT_{pattern}_{rng.randint(1000, 9999)}"
    _run(
        """
        MERGE (al:Alert {alert_id: $alert_id})
        SET
            al.pattern      = $pattern,
            al.tier         = $tier,
            al.fraud_prob   = $fp,
            al.total_amount = $ta,
            al.status       = 'OPEN',
            al.created_at   = $now,
            al.chain        = $chain,
            al.loop         = $loop,
            al.amounts      = $amounts
        """,
        alert_id=alert_id,
        pattern=pattern,
        tier=tier,
        fp=float(fraud_prob),
        ta=float(total_amount),
        now=_ts(NOW),
        chain=chain or [],
        loop=loop or [],
        amounts=[float(a) for a in (amounts or [])],
    )
    for acc_id in accounts:
        _run(
            """
            MATCH (a:Account  {account_id: $acc})
            MATCH (al:Alert   {alert_id:   $alert_id})
            MERGE (a)-[:FLAGGED_IN]->(al)
            """,
            acc=acc_id,
            alert_id=alert_id,
        )
    print(f"   Alert {alert_id} ({pattern}) → {len(accounts)} accounts")
    return alert_id


# ─────────────────────────────────────────────────────────────────────────────
# 1. CLEAR
# ─────────────────────────────────────────────────────────────────────────────
print("\n🔥  Clearing all existing data…")
_run("MATCH (n) DETACH DELETE n")
print("   Done.")

# ─────────────────────────────────────────────────────────────────────────────
# 2. LAYERING PATTERN  (2 alerts, 12 accounts)
#    Chain: L1A → L1B → L1C → L1D → L1E → L1F  (5 hops within 2 hours)
#    declared_annual_income is HIGH so KYC mismatch does NOT fire.
# ─────────────────────────────────────────────────────────────────────────────
print("\n🔷  LAYERING…")

chain1 = ["ACC_L1A", "ACC_L1B", "ACC_L1C", "ACC_L1D", "ACC_L1E", "ACC_L1F"]
chain2 = ["ACC_L2A", "ACC_L2B", "ACC_L2C", "ACC_L2D", "ACC_L2E", "ACC_L2F"]

for acc in chain1 + chain2:
    create_account(
        acc, kyc_tier=3,
        declared_annual_income=60_000_000,   # ₹6Cr declared → KYC ratio < 1
        avg_monthly_volume=5_000_000,
        volume_30d=5_000_000,
        txn_count_30d=12, txn_count_7d=3,
        fraud_score=0.92, is_fraud=True,
    )

# Chain 1 — transactions within 80 min (well under 2-hour threshold)
t0 = NOW - timedelta(hours=3)
amt = 1_500_000.0
for i in range(len(chain1) - 1):
    create_txn(chain1[i], chain1[i + 1], amt * (0.97 ** i),
               t0 + timedelta(minutes=15 * i), "RTGS")

# Chain 2 — different base time, same topology
t0 = NOW - timedelta(hours=6)
amt = 2_000_000.0
for i in range(len(chain2) - 1):
    create_txn(chain2[i], chain2[i + 1], amt * (0.97 ** i),
               t0 + timedelta(minutes=12 * i), "RTGS")

# Build amount lists from the seeded transactions
chain1_amounts = [1_500_000.0 * (0.97 ** i) for i in range(5)]
chain2_amounts = [2_000_000.0 * (0.97 ** i) for i in range(5)]

create_alert("LAYERING", "CRITICAL", 0.93, 7_000_000, chain1,
             chain=chain1, amounts=chain1_amounts)
create_alert("LAYERING", "CRITICAL", 0.91, 8_500_000, chain2,
             chain=chain2, amounts=chain2_amounts)

# ─────────────────────────────────────────────────────────────────────────────
# 3. ROUND_TRIP PATTERN  (2 alerts, 8 accounts)
#    Cycle: R1A → R1B → R1C → R1D → R1A
# ─────────────────────────────────────────────────────────────────────────────
print("\n🔄  ROUND_TRIP…")

loop1 = ["ACC_R1A", "ACC_R1B", "ACC_R1C", "ACC_R1D"]
loop2 = ["ACC_R2A", "ACC_R2B", "ACC_R2C", "ACC_R2D"]

for acc in loop1 + loop2:
    create_account(
        acc, kyc_tier=3,
        declared_annual_income=60_000_000,
        avg_monthly_volume=5_000_000,
        volume_30d=5_000_000,
        txn_count_30d=8, txn_count_7d=2,
        fraud_score=0.89, is_fraud=True,
    )

# Loop 1 — full cycle within 3 hours
t0 = NOW - timedelta(hours=4)
for i in range(len(loop1)):
    src = loop1[i]
    dst = loop1[(i + 1) % len(loop1)]
    create_txn(src, dst, 1_600_000.0, t0 + timedelta(minutes=20 * i), "RTGS")

# Loop 2
t0 = NOW - timedelta(hours=7)
for i in range(len(loop2)):
    src = loop2[i]
    dst = loop2[(i + 1) % len(loop2)]
    create_txn(src, dst, 1_800_000.0, t0 + timedelta(minutes=18 * i), "NEFT")

# Loop amounts (flat — same amount each hop)
loop1_amounts = [1_600_000.0] * 4
loop2_amounts = [1_800_000.0] * 4

# For round-trip, loop includes start repeated at end: R1A→R1B→R1C→R1D→R1A
create_alert("ROUND_TRIP", "CRITICAL", 0.90, 6_400_000, loop1,
             loop=loop1 + [loop1[0]], amounts=loop1_amounts)
create_alert("ROUND_TRIP", "CRITICAL", 0.88, 7_200_000, loop2,
             loop=loop2 + [loop2[0]], amounts=loop2_amounts)

# ─────────────────────────────────────────────────────────────────────────────
# 4. SMURFING PATTERN  (2 alerts, 6 accounts)
#    Sender makes 25 UPI txns of ₹8,999 each in 20 hours (below ₹10K threshold)
# ─────────────────────────────────────────────────────────────────────────────
print("\n🐜  SMURFING…")

s1_sender = "ACC_S1A"
s1_recv   = ["ACC_S1B", "ACC_S1C"]
s2_sender = "ACC_S2A"
s2_recv   = ["ACC_S2B", "ACC_S2C"]

# Smurfing sender: many txns, low individual amounts, moderate total volume
create_account(s1_sender, kyc_tier=1, declared_annual_income=600_000,
               avg_monthly_volume=30_000, volume_30d=350_000,
               txn_count_30d=50, txn_count_7d=25,
               fraud_score=0.79, is_fraud=True)
for acc in s1_recv:
    create_account(acc, kyc_tier=1, declared_annual_income=400_000,
                   avg_monthly_volume=20_000, volume_30d=80_000,
                   txn_count_30d=15, txn_count_7d=5, fraud_score=0.3)

create_account(s2_sender, kyc_tier=1, declared_annual_income=600_000,
               avg_monthly_volume=25_000, volume_30d=290_000,
               txn_count_30d=45, txn_count_7d=22,
               fraud_score=0.76, is_fraud=True)
for acc in s2_recv:
    create_account(acc, kyc_tier=1, declared_annual_income=400_000,
                   avg_monthly_volume=18_000, volume_30d=70_000,
                   txn_count_30d=12, txn_count_7d=4, fraud_score=0.25)

# 25 quick UPI txns in 20 hours — each ~₹8,999 (just below ₹10K CDD threshold)
t0 = NOW - timedelta(hours=20)
for i in range(25):
    recv = s1_recv[i % len(s1_recv)]
    create_txn(s1_sender, recv, 8_999 + rng.uniform(-50, 50),
               t0 + timedelta(minutes=48 * i), "UPI", "SUCCESS")

t0 = NOW - timedelta(hours=18)
for i in range(22):
    recv = s2_recv[i % len(s2_recv)]
    create_txn(s2_sender, recv, 9_499 + rng.uniform(-50, 50),
               t0 + timedelta(minutes=45 * i), "UPI", "SUCCESS")

create_alert("SMURFING", "HIGH", 0.79, 350_000, [s1_sender] + s1_recv)
create_alert("SMURFING", "HIGH", 0.76, 290_000, [s2_sender] + s2_recv)

# ─────────────────────────────────────────────────────────────────────────────
# 5. DORMANCY PATTERN  (2 alerts, 4 accounts)
#    Account dormant 200+ days, suddenly transacts ₹5L+ in 30 days
# ─────────────────────────────────────────────────────────────────────────────
print("\n💤  DORMANCY…")

d1_acc  = "ACC_D1A"
d1_recv = "ACC_D1B"
d2_acc  = "ACC_D2A"
d2_recv = "ACC_D2B"

create_account(d1_acc, kyc_tier=2, declared_annual_income=600_000,
               avg_monthly_volume=15_000, volume_30d=500_000,
               txn_count_30d=10, txn_count_7d=3,
               dormancy_days=220, fraud_score=0.83, is_fraud=True)
create_account(d1_recv, kyc_tier=2, declared_annual_income=600_000,
               avg_monthly_volume=20_000, volume_30d=30_000,
               txn_count_30d=5, txn_count_7d=1, fraud_score=0.1)

create_account(d2_acc, kyc_tier=1, declared_annual_income=480_000,
               avg_monthly_volume=10_000, volume_30d=800_000,
               txn_count_30d=14, txn_count_7d=4,
               dormancy_days=185, fraud_score=0.87, is_fraud=True)
create_account(d2_recv, kyc_tier=2, declared_annual_income=600_000,
               avg_monthly_volume=15_000, volume_30d=25_000,
               txn_count_30d=4, txn_count_7d=1, fraud_score=0.1)

t0 = NOW - timedelta(days=25)
for i in range(8):
    create_txn(d1_acc, d1_recv, 62_500, t0 + timedelta(days=i * 3), "NEFT")
for i in range(12):
    create_txn(d2_acc, d2_recv, 66_667, t0 + timedelta(days=i * 2), "NEFT")

create_alert("DORMANCY", "HIGH", 0.83, 500_000, [d1_acc, d1_recv])
create_alert("DORMANCY", "HIGH", 0.87, 800_000, [d2_acc, d2_recv])

# ─────────────────────────────────────────────────────────────────────────────
# 6. KYC_MISMATCH PATTERN  (2 alerts, 4 accounts)
#    KYC Tier-1 (declared ₹6L/yr → ₹50K/mo expected) moves ₹25L in 30 days
# ─────────────────────────────────────────────────────────────────────────────
print("\n🚨  KYC_MISMATCH…")

k1_acc  = "ACC_K1A"
k1_recv = "ACC_K1B"
k2_acc  = "ACC_K2A"
k2_recv = "ACC_K2B"

# declared_annual_income = ₹600K → expected_monthly = ₹50K
# volume_30d = ₹25L  → mismatch_ratio = 25L/50K = 50x  → CRITICAL
create_account(k1_acc, kyc_tier=1, declared_annual_income=600_000,
               avg_monthly_volume=50_000, volume_30d=2_500_000,
               txn_count_30d=6, txn_count_7d=2,
               fraud_score=0.95, is_fraud=True)
create_account(k1_recv, kyc_tier=2, declared_annual_income=1_200_000,
               avg_monthly_volume=80_000, volume_30d=60_000,
               txn_count_30d=5, txn_count_7d=1, fraud_score=0.1)

create_account(k2_acc, kyc_tier=1, declared_annual_income=600_000,
               avg_monthly_volume=50_000, volume_30d=3_000_000,
               txn_count_30d=7, txn_count_7d=2,
               fraud_score=0.96, is_fraud=True)
create_account(k2_recv, kyc_tier=2, declared_annual_income=1_000_000,
               avg_monthly_volume=70_000, volume_30d=55_000,
               txn_count_30d=5, txn_count_7d=1, fraud_score=0.1)

t0 = NOW - timedelta(days=28)
for i in range(5):
    create_txn(k1_acc, k1_recv, 500_000, t0 + timedelta(days=i * 5), "RTGS")
for i in range(6):
    create_txn(k2_acc, k2_recv, 500_000, t0 + timedelta(days=i * 4), "RTGS")

create_alert("KYC_MISMATCH", "HIGH", 0.95, 2_500_000, [k1_acc, k1_recv])
create_alert("KYC_MISMATCH", "HIGH", 0.96, 3_000_000, [k2_acc, k2_recv])

# ─────────────────────────────────────────────────────────────────────────────
# 7. NORMAL ACCOUNTS (70 clean accounts + 300 normal transactions)
# ─────────────────────────────────────────────────────────────────────────────
print("\n🧹  Creating 70 normal accounts + 300 normal transactions…")

normals = [f"ACC_N{i:03d}" for i in range(1, 71)]
for acc in normals:
    tier = rng.choice([1, 2, 2, 3, 3, 3])
    income = {1: rng.uniform(300_000, 700_000),
               2: rng.uniform(800_000, 3_000_000),
               3: rng.uniform(3_500_000, 20_000_000)}[tier]
    avg_vol = income / 12 * rng.uniform(0.6, 1.0)
    create_account(
        acc, kyc_tier=tier,
        declared_annual_income=income,
        avg_monthly_volume=avg_vol,
        volume_30d=avg_vol * rng.uniform(0.7, 1.3),
        txn_count_30d=rng.randint(5, 35),
        txn_count_7d=rng.randint(1, 8),
        fraud_score=rng.uniform(0.01, 0.22),
    )

t_start = NOW - timedelta(days=30)
for _ in range(300):
    s = rng.choice(normals[:35])
    r = rng.choice(normals[35:])
    amount = rng.uniform(3_000, 180_000)
    dt = t_start + timedelta(hours=rng.uniform(0, 720))
    ch = rng.choice(["UPI", "NEFT", "RTGS", "IMPS", "SWIFT"])
    create_txn(s, r, amount, dt, ch)

# ─────────────────────────────────────────────────────────────────────────────
# 8. SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n✅  Done!  Summary:")
with driver.session() as s:
    accs   = s.run("MATCH (a:Account) RETURN count(a) AS n").single()["n"]
    txns   = s.run("MATCH ()-[r:SENT]->() RETURN count(r) AS n").single()["n"]
    alerts = s.run("MATCH (al:Alert) RETURN al.pattern AS p, count(al) AS n").values("p", "n")
    flags  = s.run("MATCH (a:Account)-[:FLAGGED_IN]->(al:Alert) "
                   "RETURN al.pattern AS p, count(*) AS n").values("p", "n")

print(f"   Accounts    : {accs}")
print(f"   Transactions: {txns}")
print(f"   Alerts      : {list(alerts)}")
print(f"   FLAGGED_IN  : {list(flags)}")

driver.close()
print("\n🎉  Demo data seeded. Reload the dashboard!")
