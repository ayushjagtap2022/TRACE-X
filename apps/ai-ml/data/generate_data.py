import argparse
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd
from faker import Faker

DATA_DIR = Path(__file__).resolve().parent
LABELS_DIR = DATA_DIR / "labels"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic TRACE-X data.")
    parser.add_argument("--accounts", type=int, default=20000, help="Total accounts to create")
    parser.add_argument("--normal-txns", type=int, default=400000, help="Normal transactions to create")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")

    parser.add_argument("--layering-chains", type=int, default=0, help="Layering chains (0 = auto)")
    parser.add_argument("--round-trips", type=int, default=0, help="Round-trip rings (0 = auto)")
    parser.add_argument("--smurf-clusters", type=int, default=0, help="Smurfing clusters (0 = auto)")
    parser.add_argument("--dormant-activations", type=int, default=0, help="Dormant activation events (0 = auto)")
    parser.add_argument("--smurf-receivers-min", type=int, default=15, help="Min receivers per smurf cluster")
    parser.add_argument("--smurf-receivers-max", type=int, default=25, help="Max receivers per smurf cluster")

    parser.add_argument("--neo4j-accounts", type=int, default=5000, help="Accounts in Neo4j sample")
    parser.add_argument("--neo4j-transactions", type=int, default=100000, help="Transactions in Neo4j sample")
    parser.add_argument("--neo4j-dir", type=str, default="neo4j", help="Subfolder for Neo4j CSVs")
    parser.add_argument("--no-neo4j-sample", action="store_true", help="Skip Neo4j sample output")

    return parser.parse_args()


def next_txn_id(counter: Dict[str, int], width: int) -> str:
    counter["value"] += 1
    return f"TXN_{counter['value']:0{width}d}"


def make_txn(counter: Dict[str, int], width: int, sender_id: str, receiver_id: str, amount: float,
             channel: str, txn_ts: datetime, status: str, narration: str) -> Dict:
    return {
        "txn_id": next_txn_id(counter, width),
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "amount": round(float(amount), 2),
        "channel": channel,
        "txn_ts": txn_ts,
        "status": status,
        "narration": narration,
    }


def compute_auto_counts(total_accounts: int) -> Dict[str, int]:
    return {
        "layering_chains": max(80, total_accounts // 150),
        "round_trips": max(50, total_accounts // 200),
        "smurf_clusters": max(200, total_accounts // 50),
        "dormant_activations": max(60, total_accounts // 150),
    }


def build_neo4j_sample(
    df_acc: pd.DataFrame,
    df_txn: pd.DataFrame,
    fraud_accounts: Set[str],
    target_accounts: int,
    target_txns: int,
    seed: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    acc_ids = df_acc["account_id"].tolist()

    if target_accounts <= 0 or target_txns <= 0:
        return pd.DataFrame(), pd.DataFrame()

    target_accounts = min(target_accounts, len(acc_ids))

    fraud_list = list(fraud_accounts)
    target_fraud = min(len(fraud_list), max(100, target_accounts // 10))
    selected = set(rng.sample(fraud_list, target_fraud)) if fraud_list else set()

    remaining = target_accounts - len(selected)
    if remaining > 0:
        non_fraud = [a for a in acc_ids if a not in selected]
        selected.update(rng.sample(non_fraud, min(remaining, len(non_fraud))))

    filtered = df_txn[
        df_txn["sender_id"].isin(selected) & df_txn["receiver_id"].isin(selected)
    ]

    while len(filtered) < target_txns and len(selected) < len(acc_ids):
        add_count = min(500, len(acc_ids) - len(selected))
        candidates = [a for a in acc_ids if a not in selected]
        selected.update(rng.sample(candidates, add_count))
        filtered = df_txn[
            df_txn["sender_id"].isin(selected) & df_txn["receiver_id"].isin(selected)
        ]

    if len(filtered) > target_txns:
        filtered = filtered.sample(n=target_txns, random_state=seed).reset_index(drop=True)

    active_ids = set(filtered["sender_id"]).union(set(filtered["receiver_id"]))
    df_acc_sample = df_acc[df_acc["account_id"].isin(active_ids)].copy()

    return df_acc_sample, filtered.reset_index(drop=True)


def main() -> None:
    args = parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    fake = Faker("en_IN")
    Faker.seed(args.seed)

    os.makedirs(DATA_DIR, exist_ok=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)

    auto_counts = compute_auto_counts(args.accounts)
    layering_chains = args.layering_chains or auto_counts["layering_chains"]
    round_trips = args.round_trips or auto_counts["round_trips"]
    smurf_clusters = args.smurf_clusters or auto_counts["smurf_clusters"]
    dormant_activations = args.dormant_activations or auto_counts["dormant_activations"]

    smurf_min = min(args.smurf_receivers_min, args.smurf_receivers_max)
    smurf_max = max(args.smurf_receivers_min, args.smurf_receivers_max)

    acc_width = max(4, len(str(args.accounts)))
    txn_width = max(7, len(str(args.normal_txns + 100000)))

    print("Generating accounts...")

    entity_ids = [f"ENT_{i:0{acc_width}d}" for i in range(int(args.accounts * 0.7))]
    accounts: List[Dict] = []
    for i in range(args.accounts):
        accounts.append(
            {
                "account_id": f"ACC_{i:0{acc_width}d}",
                "entity_id": random.choice(entity_ids),
                "account_type": random.choice(["SAVINGS", "CURRENT", "WALLET"]),
                "kyc_tier": random.choices([0, 1, 2], weights=[10, 45, 45])[0],
                "status": "ACTIVE",
                "opened_on": fake.date_between(start_date="-5y", end_date="today"),
                "risk_category": random.choices(
                    ["LOW", "MEDIUM", "HIGH"], weights=[70, 20, 10]
                )[0],
                "declared_annual_income": int(
                    random.choice([150000, 300000, 600000, 1200000, 2500000])
                    * random.uniform(0.7, 1.4)
                ),
            }
        )

    df_acc = pd.DataFrame(accounts)
    acc_ids = df_acc["account_id"].tolist()

    print("Generating normal transactions...")

    transactions: List[Dict] = []
    fraud_accounts: Set[str] = set()
    smurf_masters: Set[str] = set()
    counter = {"value": 0}

    dormant_candidates = set(random.sample(acc_ids, int(args.accounts * 0.08)))
    active_accounts = [acc for acc in acc_ids if acc not in dormant_candidates]

    for _ in range(args.normal_txns):
        sender = random.choice(active_accounts)
        receiver = random.choice(active_accounts)
        while receiver == sender:
            receiver = random.choice(active_accounts)

        amount = min(np.random.lognormal(mean=9.5, sigma=1.8), 200000)
        txn_ts = fake.date_time_between("-120d", "now")
        status = random.choices(["SUCCESS", "FAILED", "PENDING"], weights=[92, 4, 4])[0]
        narration = fake.sentence(nb_words=4)

        transactions.append(
            make_txn(
                counter,
                txn_width,
                sender,
                receiver,
                amount,
                random.choices(["UPI", "NEFT", "RTGS", "IMPS", "CASH"], weights=[50, 20, 10, 15, 5])[0],
                txn_ts,
                status,
                narration,
            )
        )

    print("Planting fraud patterns...")

    for _ in range(layering_chains):
        chain = random.sample(acc_ids, random.randint(6, 10))
        base_time = datetime.now() - timedelta(days=random.randint(1, 60))
        amount = random.uniform(800000, 2000000)
        for i in range(len(chain) - 1):
            fraud_accounts.update([chain[i], chain[i + 1]])
            transactions.append(
                make_txn(
                    counter,
                    txn_width,
                    chain[i],
                    chain[i + 1],
                    amount * (0.97**i),
                    "NEFT",
                    base_time + timedelta(minutes=i * 15),
                    "SUCCESS",
                    "fund transfer",
                )
            )

    for _ in range(round_trips):
        ring = random.sample(acc_ids, random.randint(3, 6))
        ring.append(ring[0])
        base_time = datetime.now() - timedelta(days=random.randint(1, 45))
        amount = random.uniform(300000, 1500000)
        for i in range(len(ring) - 1):
            fraud_accounts.update([ring[i], ring[i + 1]])
            transactions.append(
                make_txn(
                    counter,
                    txn_width,
                    ring[i],
                    ring[i + 1],
                    amount * (0.98**i),
                    "IMPS",
                    base_time + timedelta(minutes=i * 30),
                    "SUCCESS",
                    "settlement",
                )
            )

    for _ in range(smurf_clusters):
        master = random.choice(acc_ids)
        receivers = random.sample(
            [a for a in acc_ids if a != master], random.randint(smurf_min, smurf_max)
        )
        base_time = datetime.now() - timedelta(days=random.randint(1, 30))
        fraud_accounts.add(master)
        smurf_masters.add(master)
        for recv in receivers:
            fraud_accounts.add(recv)
            transactions.append(
                make_txn(
                    counter,
                    txn_width,
                    master,
                    recv,
                    random.uniform(70000, 100000),
                    "UPI",
                    base_time + timedelta(minutes=random.randint(1, 120)),
                    "SUCCESS",
                    "split transfer",
                )
            )

    dormant_targets = list(dormant_candidates)[:dormant_activations]
    for acc in dormant_targets:
        spike_time = datetime.now() - timedelta(hours=random.randint(2, 48))
        amount = random.uniform(500000, 3000000)
        fraud_accounts.add(acc)

        transactions.append(
            make_txn(
                counter,
                txn_width,
                random.choice(acc_ids),
                acc,
                amount,
                "RTGS",
                spike_time,
                "SUCCESS",
                "urgent credit",
            )
        )

        transactions.append(
            make_txn(
                counter,
                txn_width,
                acc,
                random.choice(acc_ids),
                amount * 0.99,
                "RTGS",
                spike_time + timedelta(hours=random.randint(1, 6)),
                "SUCCESS",
                "urgent payout",
            )
        )

    df_txn = pd.DataFrame(transactions).sample(frac=1, random_state=args.seed).reset_index(drop=True)
    df_txn["txn_ts"] = pd.to_datetime(df_txn["txn_ts"])

    ledger = pd.concat(
        [
            df_txn[["sender_id", "receiver_id", "amount", "txn_ts"]].rename(
                columns={"sender_id": "account_id", "receiver_id": "counterparty_id"}
            ),
            df_txn[["receiver_id", "sender_id", "amount", "txn_ts"]].rename(
                columns={"receiver_id": "account_id", "sender_id": "counterparty_id"}
            ),
        ],
        ignore_index=True,
    )

    now = datetime.now()

    def window_stats(days):
        cutoff = now - timedelta(days=days)
        window = ledger[ledger["txn_ts"] >= cutoff]
        grouped = window.groupby("account_id").agg(
            **{
                f"txn_count_{days}d": ("amount", "size"),
                f"volume_{days}d": ("amount", "sum"),
            }
        )
        return grouped

    stats_7d = window_stats(7)
    stats_30d = window_stats(30)

    cutoff_180 = now - timedelta(days=180)
    window_180 = ledger[ledger["txn_ts"] >= cutoff_180]
    stats_180 = window_180.groupby("account_id").agg(
        total_count=("amount", "size"),
        total_volume=("amount", "sum"),
    )

    unique_30d = (
        ledger[ledger["txn_ts"] >= now - timedelta(days=30)]
        .groupby("account_id")["counterparty_id"]
        .nunique()
    )

    last_active = ledger.groupby("account_id")["txn_ts"].max()

    df_acc = df_acc.set_index("account_id")
    df_acc = df_acc.join(stats_7d).join(stats_30d).join(stats_180).join(unique_30d).join(last_active)

    df_acc = df_acc.rename(
        columns={
            "txn_count_7d": "txn_count_7d",
            "volume_7d": "volume_7d",
            "txn_count_30d": "txn_count_30d",
            "volume_30d": "volume_30d",
            "total_count": "total_count_180d",
            "total_volume": "total_volume_180d",
            "counterparty_id": "unique_counterparties_30d",
            "txn_ts": "last_active_ts",
        }
    )

    df_acc["txn_count_7d"] = df_acc["txn_count_7d"].fillna(0).astype(int)
    df_acc["txn_count_30d"] = df_acc["txn_count_30d"].fillna(0).astype(int)
    df_acc["volume_7d"] = df_acc["volume_7d"].fillna(0.0)
    df_acc["volume_30d"] = df_acc["volume_30d"].fillna(0.0)
    df_acc["total_count_180d"] = df_acc["total_count_180d"].fillna(0).astype(int)
    df_acc["total_volume_180d"] = df_acc["total_volume_180d"].fillna(0.0)
    df_acc["unique_counterparties_30d"] = df_acc["unique_counterparties_30d"].fillna(0).astype(int)

    df_acc["avg_monthly_count"] = (df_acc["total_count_180d"] / 6).round(2)
    df_acc["avg_monthly_volume"] = (df_acc["total_volume_180d"] / 6).round(2)

    df_acc["last_active_ts"] = df_acc["last_active_ts"].where(pd.notna(df_acc["last_active_ts"]), None)
    df_acc["dormancy_days"] = df_acc.apply(
        lambda row: int(
            (now - row["last_active_ts"]).days
            if pd.notna(row["last_active_ts"])
            else (now.date() - row["opened_on"]).days
        ),
        axis=1,
    )

    df_acc["status"] = np.where(df_acc["dormancy_days"] >= 365, "DORMANT", "ACTIVE")
    frozen_mask = np.random.rand(len(df_acc)) < 0.01
    df_acc.loc[frozen_mask, "status"] = "FROZEN"

    df_acc["is_fraud"] = df_acc.index.to_series().isin(fraud_accounts)
    df_acc["fraud_score"] = df_acc["is_fraud"].apply(
        lambda flag: round(random.uniform(0.7, 0.98), 3) if flag else round(random.uniform(0.0, 0.3), 3)
    )
    df_acc["last_scored_ts"] = now

    df_acc = df_acc.reset_index()

    df_acc["opened_on"] = df_acc["opened_on"].astype(str)
    df_acc["last_active_ts"] = df_acc["last_active_ts"].apply(
        lambda value: value.isoformat() if pd.notna(value) else None
    )
    df_acc["last_scored_ts"] = df_acc["last_scored_ts"].apply(lambda value: value.isoformat())

    df_txn["txn_ts"] = df_txn["txn_ts"].apply(lambda value: value.isoformat())

    account_columns = [
        "account_id",
        "entity_id",
        "account_type",
        "kyc_tier",
        "status",
        "opened_on",
        "risk_category",
        "declared_annual_income",
        "txn_count_7d",
        "txn_count_30d",
        "volume_7d",
        "volume_30d",
        "avg_monthly_volume",
        "avg_monthly_count",
        "unique_counterparties_30d",
        "last_active_ts",
        "dormancy_days",
        "is_fraud",
        "fraud_score",
        "last_scored_ts",
    ]

    transaction_columns = [
        "txn_id",
        "sender_id",
        "receiver_id",
        "amount",
        "channel",
        "txn_ts",
        "status",
        "narration",
    ]

    df_txn.to_csv(DATA_DIR / "transactions.csv", index=False, columns=transaction_columns)
    df_acc.to_csv(DATA_DIR / "accounts.csv", index=False, columns=account_columns)

    pd.DataFrame({"account_id": sorted(smurf_masters)}).to_csv(
        LABELS_DIR / "smurf_accounts.csv", index=False
    )
    pd.DataFrame({"account_id": sorted(fraud_accounts)}).to_csv(
        LABELS_DIR / "fraud_accounts.csv", index=False
    )

    print("\nDone.")
    print(f"Accounts:     {len(df_acc)}")
    print(f"Transactions: {len(df_txn)}")
    print(f"Fraud accounts: {df_acc['is_fraud'].sum()} ({df_acc['is_fraud'].mean()*100:.1f}%)")
    print(f"Smurf masters: {len(smurf_masters)}")

    if not args.no_neo4j_sample:
        neo4j_dir = DATA_DIR / args.neo4j_dir
        neo4j_dir.mkdir(parents=True, exist_ok=True)

        df_acc_sample, df_txn_sample = build_neo4j_sample(
            df_acc,
            df_txn,
            fraud_accounts,
            args.neo4j_accounts,
            args.neo4j_transactions,
            args.seed,
        )

        if not df_acc_sample.empty and not df_txn_sample.empty:
            df_acc_sample.to_csv(neo4j_dir / "accounts.csv", index=False, columns=account_columns)
            df_txn_sample.to_csv(neo4j_dir / "transactions.csv", index=False, columns=transaction_columns)
            print("\nNeo4j sample written:")
            print(f"  Accounts: {len(df_acc_sample)}")
            print(f"  Transactions: {len(df_txn_sample)}")
        else:
            print("\nNeo4j sample skipped (no data).")


if __name__ == "__main__":
    main()
