"use client";

import { useState } from "react";
import { fetchJson } from "../lib/tracex";

type DemoAccount = {
  account_id: string;
  entity_id: string;
  account_type: string;
  kyc_tier: number;
  status: string;
  opened_on: string;
  risk_category: string;
  declared_annual_income: number;
};

type DemoTransaction = {
  txn_id: string;
  sender_id: string;
  receiver_id: string;
  amount: number;
  channel: string;
  txn_ts: string;
  status: string;
  narration: string;
};

export default function RxLabPage() {
  const [accountForm, setAccountForm] = useState({
    account_id: "",
    entity_id: "",
    account_type: "SAVINGS",
    kyc_tier: "1",
    status: "ACTIVE",
    opened_on: new Date().toISOString().slice(0, 10),
    risk_category: "LOW",
    declared_annual_income: "600000",
  });
  const [transactionForm, setTransactionForm] = useState({
    sender_id: "",
    receiver_id: "",
    amount: "",
    channel: "UPI",
    status: "SUCCESS",
    narration: "rent payment",
  });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastResponse, setLastResponse] = useState<unknown>(null);

  async function createAccount() {
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const payload: DemoAccount = {
        account_id:
          accountForm.account_id ||
          `ACC_${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
        entity_id:
          accountForm.entity_id ||
          `ENT_${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
        account_type: accountForm.account_type,
        kyc_tier: Number(accountForm.kyc_tier),
        status: accountForm.status,
        opened_on: accountForm.opened_on,
        risk_category: accountForm.risk_category,
        declared_annual_income: Number(accountForm.declared_annual_income),
      };
      const response = await fetchJson<{
        message: string;
        account: DemoAccount;
      }>("/accounts", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setLastResponse(response);
      setMessage(`Created account ${response.account.account_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create account");
    } finally {
      setLoading(false);
    }
  }

  async function createTransaction() {
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const payload: DemoTransaction = {
        txn_id: `TXN_${Date.now()}`,
        sender_id: transactionForm.sender_id,
        receiver_id: transactionForm.receiver_id,
        amount: Number(transactionForm.amount),
        channel: transactionForm.channel,
        txn_ts: new Date().toISOString(),
        status: transactionForm.status,
        narration: transactionForm.narration,
      };
      const response = await fetchJson<{
        message: string;
        impacted_accounts: Array<{ account_id: string; score: unknown }>;
        evidence?: unknown;
      }>("/transactions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setLastResponse(response);
      setMessage(
        `Created transaction and re-scored ${response.impacted_accounts.map((item) => item.account_id).join(", ")}`,
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create transaction",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-6 lg:px-8">
      <section className="rounded-[32px] border border-white/10 bg-slate-950/45 p-6">
        <div className="text-xs uppercase tracking-[0.35em] text-cyan-200/80">
          lab
        </div>
        <h1 className="mt-3 text-3xl font-semibold text-white">Demo lab</h1>
        <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-400">
          Create an account or transaction live. The backend updates Neo4j,
          recomputes metrics, and returns an immediate fraud result.
        </p>

        <div className="mt-6 grid gap-6 xl:grid-cols-2">
          <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
            <div className="text-xs uppercase tracking-[0.35em] text-slate-400">
              create account
            </div>
            <div className="mt-4 grid gap-3">
              {[
                ["account_id", accountForm.account_id],
                ["entity_id", accountForm.entity_id],
                ["declared_annual_income", accountForm.declared_annual_income],
              ].map(([field, value]) => (
                <label
                  key={field}
                  className="space-y-1 text-xs uppercase tracking-[0.2em] text-slate-400"
                >
                  <span>{field}</span>
                  <input
                    value={value}
                    onChange={(event) =>
                      setAccountForm((current) => ({
                        ...current,
                        [field]: event.target.value,
                      }))
                    }
                    className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                  />
                </label>
              ))}
              <button
                type="button"
                onClick={createAccount}
                disabled={loading}
                className="rounded-full bg-cyan-400 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
              >
                {loading ? "Working..." : "Create account"}
              </button>
            </div>
          </div>

          <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
            <div className="text-xs uppercase tracking-[0.35em] text-slate-400">
              create transaction
            </div>
            <div className="mt-4 grid gap-3">
              {[
                ["sender_id", transactionForm.sender_id],
                ["receiver_id", transactionForm.receiver_id],
                ["amount", transactionForm.amount],
                ["narration", transactionForm.narration],
              ].map(([field, value]) => (
                <label
                  key={field}
                  className="space-y-1 text-xs uppercase tracking-[0.2em] text-slate-400"
                >
                  <span>{field}</span>
                  <input
                    value={value}
                    onChange={(event) =>
                      setTransactionForm((current) => ({
                        ...current,
                        [field]: event.target.value,
                      }))
                    }
                    className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                  />
                </label>
              ))}
              <button
                type="button"
                onClick={createTransaction}
                disabled={loading}
                className="rounded-full bg-fuchsia-400 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-fuchsia-300 disabled:opacity-50"
              >
                {loading ? "Submitting..." : "Create transaction"}
              </button>
            </div>
          </div>
        </div>

        {message ? (
          <div className="mt-4 rounded-2xl border border-emerald-400/20 bg-emerald-400/10 p-4 text-emerald-100">
            {message}
          </div>
        ) : null}
        {error ? (
          <div className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-4 text-rose-100">
            {error}
          </div>
        ) : null}

        <pre className="mt-6 max-h-[28rem] overflow-auto rounded-[28px] border border-white/10 bg-[#07111f] p-5 text-xs leading-6 text-slate-200">
          {lastResponse
            ? JSON.stringify(lastResponse, null, 2)
            : "The backend response will appear here after you create something."}
        </pre>
      </section>
    </main>
  );
}
