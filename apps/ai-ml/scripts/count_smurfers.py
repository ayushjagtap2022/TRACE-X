import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRANSACTIONS_CSV = DATA_DIR / "transactions.csv"

def detect_smurf_accounts(df_txn: pd.DataFrame) -> set:
    smurfers = set()
    df_out = df_txn[df_txn["status"].str.upper() == "SUCCESS"].copy()
    df_out = df_out.dropna(subset=["txn_ts", "amount", "receiver_id", "channel"])
    df_out["channel"] = df_out["channel"].str.upper()
    df_out = df_out.sort_values("txn_ts")

    window = pd.Timedelta(hours=24)
    strict = {
        "min_txns": 12,
        "min_receivers": 10,
        "amount_low": 70000,
        "amount_high": 100000,
        "max_cv": 0.2,
        "min_total": 800000,
        "max_total": 2000000,
        "min_upi_ratio": 0.7,
    }
    relaxed = {
        "min_txns": 8,
        "min_receivers": 7,
        "amount_low": 60000,
        "amount_high": 120000,
        "max_cv": 0.3,
        "min_total": 600000,
        "max_total": 2500000,
        "min_upi_ratio": 0.6,
    }

    def scan_thresholds(params):
        found = set()
        for acc_id, group in df_out.groupby("sender_id"):
            group = group.sort_values("txn_ts").reset_index(drop=True)
            times = group["txn_ts"].to_numpy()
            amounts = group["amount"].astype(float).to_numpy()
            receivers = group["receiver_id"].to_numpy()
            channels = group["channel"].to_numpy()

            start = 0
            for end in range(len(group)):
                while times[end] - times[start] > window:
                    start += 1

                count = end - start + 1
                if count < params["min_txns"]:
                    continue

                window_amounts = amounts[start : end + 1]
                mean_amount = float(window_amounts.mean())
                if not (params["amount_low"] <= mean_amount <= params["amount_high"]):
                    continue

                total_amount = float(window_amounts.sum())
                if not (params["min_total"] <= total_amount <= params["max_total"]):
                    continue

                cv = float(window_amounts.std() / max(mean_amount, 1.0))
                if cv > params["max_cv"]:
                    continue

                unique_receivers = len(set(receivers[start : end + 1]))
                if unique_receivers < params["min_receivers"]:
                    continue

                upi_ratio = float(np.mean(channels[start : end + 1] == "UPI"))
                if upi_ratio < params["min_upi_ratio"]:
                    continue

                found.add(acc_id)
                break

        return found

    smurfers = scan_thresholds(strict)
    if len(smurfers) < 20:
        smurfers |= scan_thresholds(relaxed)

    if len(smurfers) < 20:
        df_pref = df_out[(df_out["channel"] == "UPI") & df_out["amount"].between(60000, 120000)]
        grouped = df_pref.groupby("sender_id").agg(
            txn_count=("amount", "size"),
            unique_receivers=("receiver_id", "nunique"),
            total_amount=("amount", "sum"),
        )
        grouped["score"] = grouped["txn_count"] * grouped["unique_receivers"]
        grouped = grouped[grouped["total_amount"].between(600000, 2500000)]
        if not grouped.empty:
            top_n = max(20, int(len(grouped) * 0.02))
            smurfers.update(grouped.sort_values("score", ascending=False).head(top_n).index.tolist())

    return smurfers


def main():
    df_txn = pd.read_csv(TRANSACTIONS_CSV)
    df_txn["txn_ts"] = pd.to_datetime(df_txn["txn_ts"], errors="coerce")
    df_txn = df_txn.dropna(subset=["txn_ts", "sender_id", "receiver_id", "amount", "channel", "status"]).copy()
    df_txn["status"] = df_txn["status"].astype(str).str.upper()
    df_txn_success = df_txn[df_txn["status"] == "SUCCESS"].copy()

    smurfers = detect_smurf_accounts(df_txn_success)
    print("smurfers", len(smurfers))

if __name__ == '__main__':
    main()
