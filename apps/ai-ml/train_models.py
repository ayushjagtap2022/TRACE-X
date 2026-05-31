# ════════════════════════════════════════════════════════════
# WHAT THIS FILE DOES:
# Reads your CSV data → trains 2 models → saves them as files
#
# You run this once (or when you regenerate data).
# It saves:
#   models/isolation_forest.pkl  ← dormant anomaly detector
#   models/lstm_model.pt         ← smurfing detector
#   models/scaler.pkl            ← data normalizer
#   models/acc_ids.npy           ← account ID list
# ════════════════════════════════════════════════════════════

import copy
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import StandardScaler

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"

ACCOUNTS_CSV = DATA_DIR / "accounts.csv"
TRANSACTIONS_CSV = DATA_DIR / "transactions.csv"

MODELS_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)


def load_accounts() -> pd.DataFrame:
    if not ACCOUNTS_CSV.exists():
        raise FileNotFoundError(f"Missing {ACCOUNTS_CSV}")

    df = pd.read_csv(ACCOUNTS_CSV)

    if "last_active_ts" in df.columns:
        df["last_active_ts"] = pd.to_datetime(df["last_active_ts"], errors="coerce")

    if "opened_on" in df.columns:
        df["opened_on"] = pd.to_datetime(df["opened_on"], errors="coerce").dt.date

    now = datetime.now()
    if "dormancy_days" not in df.columns:
        df["dormancy_days"] = df["last_active_ts"].apply(
            lambda ts: (now - ts).days if pd.notna(ts) else 0
        )

    return df


def load_transactions() -> pd.DataFrame:
    if not TRANSACTIONS_CSV.exists():
        raise FileNotFoundError(f"Missing {TRANSACTIONS_CSV}")

    df = pd.read_csv(TRANSACTIONS_CSV)
    df["txn_ts"] = pd.to_datetime(df["txn_ts"], errors="coerce")
    df = df.dropna(subset=["txn_ts", "sender_id", "receiver_id", "amount", "channel", "status"])
    return df


def train_isolation_forest(df_acc: pd.DataFrame) -> None:
    print("Training Model A: Isolation Forest (dormant anomaly detector)...")

    feature_cols = [
        "dormancy_days",
        "txn_count_7d",
        "txn_count_30d",
        "volume_7d",
        "volume_30d",
        "avg_monthly_volume",
        "avg_monthly_count",
        "unique_counterparties_30d",
    ]

    missing = [col for col in feature_cols if col not in df_acc.columns]
    if missing:
        raise ValueError(f"accounts.csv missing columns: {missing}")

    X = df_acc[feature_cols].copy().fillna(0)
    X = X.astype(float).values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    iso = IsolationForest(n_estimators=200, contamination=0.05, random_state=RANDOM_SEED)
    iso.fit(X_scaled)

    predictions = iso.predict(X_scaled)
    anomaly_count = int((predictions == -1).sum())
    print(f"  Flagged {anomaly_count} anomalous accounts out of {len(X)}")

    joblib.dump(iso, MODELS_DIR / "isolation_forest.pkl")
    joblib.dump(scaler, MODELS_DIR / "scaler.pkl")
    print("  Saved: models/isolation_forest.pkl")


def detect_smurf_accounts(df_txn: pd.DataFrame) -> Set[str]:
    smurfers: Set[str] = set()
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

    def scan_thresholds(params: Dict[str, float]) -> Set[str]:
        found: Set[str] = set()
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


def pick_threshold(y_true: np.ndarray, y_prob: np.ndarray, beta: float = 0.5) -> Tuple[float, float]:
    best_score = -1.0
    best_threshold = 0.5
    for threshold in np.linspace(0.05, 0.95, 19):
        y_pred = (y_prob >= threshold).astype(int)
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        if precision == 0 and recall == 0:
            score = 0.0
        else:
            score = (1 + beta**2) * (precision * recall) / ((beta**2 * precision) + recall)
        if score > best_score:
            best_score = score
            best_threshold = float(threshold)
    return best_threshold, best_score


def build_sequence(group: pd.DataFrame, window: int) -> np.ndarray:
    group = group.sort_values("txn_ts").tail(window)
    seq: List[List[float]] = []
    prev_time = None

    for _, row in group.iterrows():
        gap = 0.0 if prev_time is None else (row["txn_ts"] - prev_time).total_seconds() / 60
        seq.append(
            [
                float(np.log1p(row["amount"])) / 15.0,
                min(gap / 1440.0, 1.0),
                row["txn_ts"].hour / 23.0,
                row["txn_ts"].dayofweek / 6.0,
                1.0 if row["channel"] == "UPI" else 0.0,
            ]
        )
        prev_time = row["txn_ts"]

    while len(seq) < window:
        seq.insert(0, [0.0, 0.0, 0.0, 0.0, 0.0])

    return np.array(seq[-window:], dtype=np.float32)


def train_smurf_lstm(df_acc: pd.DataFrame, df_txn: pd.DataFrame) -> None:
    print("\nTraining Model B: BiLSTM (smurfing detector)...")

    window = 30
    min_seq_len = 10

    df_txn = df_txn.copy()
    df_txn["status"] = df_txn["status"].str.upper()
    df_txn_success = df_txn[df_txn["status"] == "SUCCESS"].copy()

    labels_path = DATA_DIR / "labels" / "smurf_accounts.csv"
    if labels_path.exists():
        labels_df = pd.read_csv(labels_path)
        smurfers = set(labels_df["account_id"].dropna().astype(str))
        print(f"  Smurf labels loaded: {len(smurfers)} accounts")
    else:
        smurfers = detect_smurf_accounts(df_txn_success)
        print(f"  Smurf labeler found {len(smurfers)} accounts")

    sequences: List[np.ndarray] = []
    labels: List[int] = []

    for acc_id in df_acc["account_id"].tolist():
        txns = df_txn_success[df_txn_success["sender_id"] == acc_id]
        if len(txns) < min_seq_len:
            continue

        sequences.append(build_sequence(txns, window))
        labels.append(1 if acc_id in smurfers else 0)

    X = np.array(sequences, dtype=np.float32)
    y = np.array(labels, dtype=np.int64)

    print(f"  Dataset: {len(X)} accounts, {int(y.sum())} smurfers")

    if len(X) == 0:
        raise ValueError("No sequences available for training.")

    if int(y.sum()) == 0:
        raise ValueError("Smurf labeler produced 0 positives. Regenerate data or relax thresholds.")

    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]
    np.random.shuffle(pos_idx)
    np.random.shuffle(neg_idx)
    pos_split = int(len(pos_idx) * 0.8)
    neg_split = int(len(neg_idx) * 0.8)
    train_idx = np.concatenate([pos_idx[:pos_split], neg_idx[:neg_split]])
    val_idx = np.concatenate([pos_idx[pos_split:], neg_idx[neg_split:]])
    np.random.shuffle(train_idx)
    np.random.shuffle(val_idx)

    X_train = torch.tensor(X[train_idx], dtype=torch.float32)
    y_train = torch.tensor(y[train_idx], dtype=torch.long)
    X_val = torch.tensor(X[val_idx], dtype=torch.float32)
    y_val = torch.tensor(y[val_idx], dtype=torch.long)

    class SmurfLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=5,
                hidden_size=64,
                num_layers=2,
                batch_first=True,
                bidirectional=True,
                dropout=0.3,
            )
            self.fc = nn.Sequential(
                nn.Linear(64 * 2, 32),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(32, 2),
            )

        def forward(self, x):
            out, _ = self.lstm(x)
            last = out[:, -1, :]
            return self.fc(last)

    model = SmurfLSTM()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    smurf_count = int(y_train.sum())
    normal_count = len(y_train) - smurf_count
    weights = torch.tensor([1.0, normal_count / max(smurf_count, 1)], dtype=torch.float32)
    criterion = nn.CrossEntropyLoss(weight=weights)

    dataset = TensorDataset(X_train, y_train)
    class_counts = np.bincount(y_train.cpu().numpy(), minlength=2)
    class_weights = 1.0 / np.maximum(class_counts, 1)
    sample_weights = class_weights[y_train.cpu().numpy()]
    sampler = WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)
    loader = DataLoader(dataset, batch_size=64, sampler=sampler)

    best_state = None
    best_threshold = 0.5
    best_score = -1.0

    for epoch in range(50):
        model.train()
        total_loss = 0.0
        for bx, by in loader:
            optimizer.zero_grad()
            out = model(bx)
            loss = criterion(out, by)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        if epoch % 10 == 0:
            print(f"  Epoch {epoch:2d} | Loss: {total_loss / len(loader):.4f}")

        if (epoch + 1) % 5 == 0:
            model.eval()
            with torch.no_grad():
                logits = model(X_val)
                probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
                y_true = y_val.cpu().numpy()
                if len(np.unique(y_true)) > 1:
                    threshold, score = pick_threshold(y_true, probs, beta=0.5)
                    if score > best_score:
                        best_score = score
                        best_threshold = threshold
                        best_state = copy.deepcopy(model.state_dict())

    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    with torch.no_grad():
        logits = model(X_val)
        probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
        y_true = y_val.cpu().numpy()
        if len(np.unique(y_true)) < 2:
            print("\nValidation report: only one class present in validation split.")
        else:
            y_pred = (probs >= best_threshold).astype(int)
            report = classification_report(
                y_true, y_pred, target_names=["normal", "smurf"], zero_division=0
            )
            matrix = confusion_matrix(y_true, y_pred)
            precision = precision_score(y_true, y_pred, zero_division=0)
            recall = recall_score(y_true, y_pred, zero_division=0)
            f1 = f1_score(y_true, y_pred, zero_division=0)
            print("\nValidation report (thresholded):\n" + report)
            print("Confusion matrix:\n" + str(matrix))
            print(f"Chosen threshold: {best_threshold:.2f} | Precision: {precision:.3f} | Recall: {recall:.3f} | F1: {f1:.3f}")

    torch.save(model.state_dict(), MODELS_DIR / "lstm_model.pt")
    with open(MODELS_DIR / "smurf_threshold.json", "w", encoding="utf-8") as handle:
        handle.write(f"{{\"threshold\": {best_threshold:.4f}}}\n")
    print("  Saved: models/lstm_model.pt")
    print("  Saved: models/smurf_threshold.json")


def main() -> None:
    df_acc = load_accounts()
    df_txn = load_transactions()

    acc_ids = df_acc["account_id"].tolist()
    np.save(MODELS_DIR / "acc_ids.npy", np.array(acc_ids))

    train_isolation_forest(df_acc)
    train_smurf_lstm(df_acc, df_txn)

    print("\nAll models trained and saved.")


if __name__ == "__main__":
    main()
