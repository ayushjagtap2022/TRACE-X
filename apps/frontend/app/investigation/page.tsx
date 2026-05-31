"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchJson } from "../lib/tracex";

export default function InvestigationIndexPage() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<string[]>([]);
  const [inputId, setInputId] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchJson<{ total: number; alerts: { account_id: string; score: number; risk_level: string }[] }>("/alerts?limit=20")
      .then((r) => setAccounts(r.alerts.map((a) => a.account_id)))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex h-screen flex-col items-center justify-center p-8">
      <div className="glass rounded-2xl p-8 w-full max-w-md">
        <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-1">Fund Flow Analysis</div>
        <h1 className="text-2xl font-bold text-white mb-6">Open Investigation</h1>

        <div className="flex gap-2 mb-6">
          <input
            value={inputId}
            onChange={(e) => setInputId(e.target.value)}
            placeholder="e.g. ACC_00018"
            className="flex-1 rounded-xl border border-white/[0.08] bg-white/[0.04] px-4 py-3 text-sm font-mono text-white placeholder-slate-600 focus:border-cyan-400/40 focus:outline-none"
            onKeyDown={(e) => e.key === "Enter" && inputId && router.push(`/investigation/${inputId}`)}
          />
          <button
            onClick={() => inputId && router.push(`/investigation/${inputId}`)}
            className="rounded-xl bg-cyan-400/10 border border-cyan-400/25 px-5 py-3 text-sm font-semibold text-cyan-200 hover:bg-cyan-400/20 transition"
          >
            Go →
          </button>
        </div>

        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-3">Recent Flagged Accounts</div>
        {loading ? (
          <div className="text-xs text-slate-500 animate-pulse">Loading…</div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {accounts.map((id) => (
              <button key={id} onClick={() => router.push(`/investigation/${id}`)}
                className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2.5 text-left font-mono text-xs text-slate-300 hover:border-cyan-400/25 hover:bg-cyan-400/5 transition">
                {id}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
