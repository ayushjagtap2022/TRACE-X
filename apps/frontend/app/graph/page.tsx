"use client";

import Link from "next/link";
import { useState } from "react";
import { fetchJson } from "../lib/tracex";

type TraceResponse = {
  detected: boolean;
  fraud_type: string;
  confidence?: number;
  chain?: string[];
  loop?: string[];
  amounts?: number[];
  timestamps?: string[];
  hops?: number;
  error?: string;
};

export default function RxGraphPage() {
  const [accountId, setAccountId] = useState("");
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadTrace() {
    if (!accountId) return;
    setLoading(true);
    setError("");
    try {
      const data = await fetchJson<TraceResponse>(`/trace/${accountId}`);
      setTrace(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load trace");
    } finally {
      setLoading(false);
    }
  }

  const nodes = trace?.chain?.length
    ? trace.chain
    : trace?.loop?.length
      ? trace.loop
      : [];

  return (
    <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 md:px-6 lg:px-8">
      <section className="rounded-[32px] border border-white/10 bg-slate-950/45 p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.35em] text-cyan-200/80">
              graph
            </div>
            <h1 className="mt-3 text-3xl font-semibold text-white">
              Graph trace
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-400">
              Visualize layering chains and circular fund movement from Neo4j.
            </p>
          </div>
          <Link
            href="/explain"
            className="text-sm text-cyan-200 hover:text-cyan-100"
          >
            Open explainability →
          </Link>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-[1fr_auto]">
          <input
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
            placeholder="Enter account_id for graph trace"
            className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
          />
          <button
            type="button"
            onClick={loadTrace}
            disabled={loading}
            className="rounded-full bg-cyan-400 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Tracing..." : "Trace funds"}
          </button>
        </div>

        {error ? (
          <div className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="mt-6 rounded-[28px] border border-white/10 bg-white/5 p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.35em] text-slate-400">
                trace status
              </div>
              <div className="mt-2 text-xl font-semibold text-white">
                {trace?.detected ? trace.fraud_type : "No trace loaded"}
              </div>
            </div>
            <div className="text-right text-sm text-slate-400">
              <div>confidence: {trace?.confidence?.toFixed(3) ?? "-"}</div>
              <div>hops: {trace?.hops ?? "-"}</div>
            </div>
          </div>

          <div className="mt-5 rounded-3xl border border-cyan-400/15 bg-[#07111f] p-5">
            {nodes.length ? (
              <div className="flex flex-wrap items-center gap-3">
                {nodes.map((node, index) => (
                  <div key={node} className="flex items-center gap-3">
                    <div className="rounded-full border border-cyan-300/30 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100">
                      {node}
                    </div>
                    {index < nodes.length - 1 ? (
                      <div className="text-cyan-300/50">→</div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-400">
                Load a case to render the graph chain or loop here.
              </div>
            )}

            {trace?.amounts?.length ? (
              <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-300">
                {trace.amounts.map((amount) => (
                  <span
                    key={String(amount)}
                    className="rounded-full border border-white/10 bg-white/5 px-3 py-1"
                  >
                    ₹{new Intl.NumberFormat("en-IN").format(Number(amount))}
                  </span>
                ))}
              </div>
            ) : null}

            {trace?.timestamps?.length ? (
              <div className="mt-4 space-y-1 text-xs text-slate-400">
                {trace.timestamps.map((ts) => (
                  <div key={ts}>{ts}</div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </main>
  );
}
