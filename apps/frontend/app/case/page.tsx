"use client";

import Link from "next/link";
import { useState } from "react";
import { fetchJson } from "../lib/tracex";

type ScoreResponse = {
  account_id: string;
  is_flagged: boolean;
  risk_level: string;
  combined_score: number;
  flagged_for: string[];
  detections: Record<string, unknown>;
};

export default function RxCasePage() {
  const [accountId, setAccountId] = useState("");
  const [score, setScore] = useState<ScoreResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadCase() {
    if (!accountId) return;
    setLoading(true);
    setError("");
    try {
      const data = await fetchJson<ScoreResponse>(`/score/${accountId}`);
      setScore(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load case");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 md:px-6 lg:px-8">
      <section className="rounded-[32px] border border-white/10 bg-slate-950/45 p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.35em] text-cyan-200/80">
              case
            </div>
            <h1 className="mt-3 text-3xl font-semibold text-white">
              Case view
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-400">
              Pull a single account and inspect the combined risk, all detector
              outputs, and the case narrative.
            </p>
          </div>
          <Link
            href="/report"
            className="text-sm text-cyan-200 hover:text-cyan-100"
          >
            Open report page →
          </Link>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-[1fr_auto]">
          <input
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
            placeholder="Enter account_id, e.g. ACC_0001"
            className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
          />
          <button
            type="button"
            onClick={loadCase}
            disabled={loading}
            className="rounded-full bg-fuchsia-400 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-fuchsia-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Loading..." : "Load case"}
          </button>
        </div>

        {error ? (
          <div className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="mt-6 grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
            <div className="text-xs uppercase tracking-[0.35em] text-slate-400">
              summary
            </div>
            <div className="mt-3 text-2xl font-semibold text-white">
              {score?.account_id || "No case loaded"}
            </div>
            <div className="mt-2 text-sm text-slate-400">
              {score
                ? score.is_flagged
                  ? "Flagged account"
                  : "Not flagged"
                : "Enter an account id and load a case."}
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
                <div className="text-xs uppercase tracking-[0.25em] text-slate-400">
                  risk
                </div>
                <div className="mt-2 text-xl font-semibold text-white">
                  {score?.risk_level ?? "-"}
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
                <div className="text-xs uppercase tracking-[0.25em] text-slate-400">
                  score
                </div>
                <div className="mt-2 text-xl font-semibold text-white">
                  {score?.combined_score?.toFixed(3) ?? "-"}
                </div>
              </div>
            </div>

            <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-[0.25em] text-slate-400">
                flagged for
              </div>
              <div className="mt-2 text-sm text-slate-200">
                {score?.flagged_for.join(", ") || "None"}
              </div>
            </div>
          </div>

          <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
            <div className="text-xs uppercase tracking-[0.35em] text-slate-400">
              detector outputs
            </div>
            <pre className="mt-3 max-h-[36rem] overflow-auto rounded-3xl border border-white/10 bg-[#07111f] p-4 text-xs leading-6 text-slate-200">
              {score
                ? JSON.stringify(score.detections, null, 2)
                : "Load a case to inspect detector outputs."}
            </pre>
          </div>
        </div>
      </section>
    </main>
  );
}
