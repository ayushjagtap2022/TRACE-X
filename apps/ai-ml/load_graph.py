import argparse
import os
import random
from pathlib import Path
from typing import Iterable, List, Dict

import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ACCOUNTS_CSV = DATA_DIR / "accounts.csv"
TRANSACTIONS_CSV = DATA_DIR / "transactions.csv"

ROOT_ENV = BASE_DIR.parents[2] / ".env"
load_dotenv(ROOT_ENV, override=False)
load_dotenv(BASE_DIR / ".env", override=True)


def chunked(rows: List[Dict], size: int) -> Iterable[List[Dict]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def load_accounts(path: Path) -> List[Dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")

    df = pd.read_csv(path)
    df["opened_on"] = pd.to_datetime(df["opened_on"], errors="coerce").dt.date
    df["last_active_ts"] = pd.to_datetime(df["last_active_ts"], errors="coerce")
    df["last_scored_ts"] = pd.to_datetime(df["last_scored_ts"], errors="coerce")
    if "declared_annual_income" in df.columns:
        df["declared_annual_income"] = pd.to_numeric(df["declared_annual_income"], errors="coerce")
    df["is_fraud"] = df["is_fraud"].fillna(False).astype(bool)

    df = df.where(pd.notna(df), None)
    return df.to_dict("records")


def load_transactions(path: Path) -> List[Dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")

    df = pd.read_csv(path)
    df["txn_ts"] = pd.to_datetime(df["txn_ts"], errors="coerce")
    df = df.where(pd.notna(df), None)
    return df.to_dict("records")


def create_constraints(tx) -> None:
    tx.run(
        "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Account) REQUIRE a.account_id IS UNIQUE"
    )


def clear_graph(tx) -> None:
    tx.run("MATCH (n) DETACH DELETE n")


def insert_accounts(tx, rows: List[Dict]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (a:Account {account_id: row.account_id})
        SET a += row
        """,
        rows=rows,
    )


def insert_transactions(tx, rows: List[Dict], rel_type: str) -> None:
    query = f"""
    UNWIND $rows AS row
    MATCH (sender:Account {{account_id: row.sender_id}})
    MATCH (receiver:Account {{account_id: row.receiver_id}})
    MERGE (sender)-[t:{rel_type} {{txn_id: row.txn_id}}]->(receiver)
    SET t.amount = row.amount,
        t.channel = row.channel,
        t.txn_ts = row.txn_ts,
        t.status = row.status,
        t.narration = row.narration
    """
    tx.run(query, rows=rows)


def write_tx(session, func, *args):
    if hasattr(session, "execute_write"):
        return session.execute_write(func, *args)
    return session.write_transaction(func, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load CSV data into Neo4j.")
    parser.add_argument("--clear", action="store_true", help="Delete all nodes/edges before loading")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size for inserts")
    parser.add_argument("--data-dir", type=str, default=None, help="Folder containing CSVs")
    parser.add_argument("--accounts-csv", type=str, default=None, help="Path to accounts.csv")
    parser.add_argument("--transactions-csv", type=str, default=None, help="Path to transactions.csv")
    parser.add_argument(
        "--max-relationships",
        type=int,
        default=None,
        help="Limit number of relationships inserted (Aura Free safety)",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=42,
        help="Seed used when sampling transactions",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR
    accounts_csv = Path(args.accounts_csv) if args.accounts_csv else data_dir / "accounts.csv"
    transactions_csv = (
        Path(args.transactions_csv) if args.transactions_csv else data_dir / "transactions.csv"
    )

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    rel_type = os.getenv("NEO4J_REL_TYPE", "SENT")

    if not password:
        raise ValueError("NEO4J_PASSWORD is required. Set it in apps/ai-ml/.env")

    accounts = load_accounts(accounts_csv)
    transactions = load_transactions(transactions_csv)

    if args.max_relationships and len(transactions) > args.max_relationships:
        rng = random.Random(args.sample_seed)
        transactions = rng.sample(transactions, args.max_relationships)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        write_tx(session, create_constraints)

        if args.clear:
            write_tx(session, clear_graph)

        for batch in chunked(accounts, args.batch_size):
            write_tx(session, insert_accounts, batch)

        for batch in chunked(transactions, args.batch_size):
            write_tx(session, insert_transactions, batch, rel_type)

    driver.close()

    print("Load complete.")
    print(f"Accounts loaded: {len(accounts)}")
    print(f"Transactions loaded: {len(transactions)}")
    print(f"Relationship type: {rel_type}")
    print(f"Source accounts CSV: {accounts_csv}")
    print(f"Source transactions CSV: {transactions_csv}")
    if args.max_relationships:
        print(f"Max relationships cap: {args.max_relationships}")


if __name__ == "__main__":
    main()
