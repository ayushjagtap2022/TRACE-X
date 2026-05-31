"use client";

import { useState } from "react";
import { fetchJson } from "../lib/tracex";

type ExplanationResponse = Record<string, unknown>;

export default function RxExplainPage() {
  const [accountId, setAccountId] = useState("");
  const [dormant, setDormant] = useState<ExplanationResponse | null>(null);
  const [smurfing, setSmurfing] = useState<ExplanationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadExplainability() {
    if (!accountId) return;
    setLoading(true);
    setError("");
    try {
      const [dormantData, smurfData] = await Promise.all([
        fetchJson<ExplanationResponse>(`/explain/dormant/${accountId}`),
        fetchJson<ExplanationResponse>(`/explain/smurfing/${accountId}`),
      ]);
      setDormant(dormantData);
      setSmurfing(smurfData);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load explanations",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 md:px-6 lg:px-8">
      <section className="rounded-[32px] border border-white/10 bg-slate-950/45 p-6">
        <div className="text-xs uppercase tracking-[0.35em] text-cyan-200/80">
          explain
        </div>
        <h1 className="mt-3 text-3xl font-semibold text-white">
          Explainability
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-400">
          See the reasons behind the score using SHAP for dormant detection and
          SHAP-style / occlusion output for smurfing.
        </p>

        <div className="mt-6 grid gap-4 md:grid-cols-[1fr_auto]">
          <input
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
            placeholder="Enter account_id for explanation"
            className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
          />
          <button
            type="button"
            onClick={loadExplainability}
            disabled={loading}
            className="rounded-full bg-cyan-400 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Loading..." : "Load explanations"}
          </button>
        </div>

        {error ? (
          <div className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="mt-6 grid gap-6 xl:grid-cols-2">
          <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
            <div className="text-xs uppercase tracking-[0.35em] text-slate-400">
              dormant SHAP
            </div>
            <pre className="mt-3 max-h-[38rem] overflow-auto whitespace-pre-wrap break-words rounded-3xl border border-white/10 bg-[#07111f] p-4 text-xs leading-6 text-slate-200">
              {dormant
                ? JSON.stringify(dormant, null, 2)
                : "Load a case to see dormant explanation output."}
            </pre>
          </div>
          <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
            <div className="text-xs uppercase tracking-[0.35em] text-slate-400">
              smurfing explanation
            </div>
            <pre className="mt-3 max-h-[38rem] overflow-auto whitespace-pre-wrap break-words rounded-3xl border border-white/10 bg-[#07111f] p-4 text-xs leading-6 text-slate-200">
              {smurfing
                ? JSON.stringify(smurfing, null, 2)
                : "Load a case to see smurfing explanation output."}
            </pre>
          </div>
        </div>
      </section>
    </main>
  );
}
