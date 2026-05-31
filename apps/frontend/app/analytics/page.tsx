"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchJson } from "../lib/tracex";

type AlertItem = {
  account_id: string;
  risk_level: string;
  flagged_for: string[];
  score: number;
  detections: Record<string, { detected: boolean; confidence?: number }>;
};

function fmtInr(n: number) {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

/* ── Mini SVG Line Chart ── */
function MiniLineChart({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const W = 220, H = 60, pad = 8;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (W - pad * 2);
    const y = H - pad - ((v - min) / range) * (H - pad * 2);
    return `${x},${y}`;
  }).join(" ");
  const area = `M${pad},${H - pad} L${pts.split(" ").join(" L")} L${W - pad},${H - pad} Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }}>
      <defs>
        <linearGradient id={`grad-${color}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`M ${area}`} fill={`url(#grad-${color})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
      {/* Last point dot */}
      {(() => {
        const last = pts.split(" ").pop()!;
        const [x, y] = last.split(",");
        return <circle cx={x} cy={y} r="3" fill={color} />;
      })()}
    </svg>
  );
}

/* ── Horizontal Bar ── */
function HBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-28 flex-shrink-0 text-[11px] text-slate-400 capitalize text-right">{label.replace("_", " ")}</div>
      <div className="flex-1 score-bar-track">
        <div className="score-bar-fill" style={{ width: `${max > 0 ? (value / max) * 100 : 0}%`, background: color, animation: "bar-fill 1s ease-out both" }} />
      </div>
      <div className="w-6 text-[11px] font-mono text-slate-500 text-right">{value}</div>
    </div>
  );
}

export default function AnalyticsPage() {
  const router = useRouter();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<"score" | "risk_level">("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    fetchJson<{ total: number; alerts: AlertItem[] }>("/alerts/quick?limit=200")
      .then((r) => setAlerts(r.alerts))
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  /* Aggregations */
  const fraudTypeCounts: Record<string, number> = {};
  const riskCounts: Record<string, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  for (const a of alerts) {
    for (const f of a.flagged_for) fraudTypeCounts[f] = (fraudTypeCounts[f] ?? 0) + 1;
    riskCounts[a.risk_level] = (riskCounts[a.risk_level] ?? 0) + 1;
  }

  /* Simulated 30-day trend (use real scores as base) */
  const trendData = Array.from({ length: 30 }, (_, i) => {
    const base = alerts.length;
    return Math.max(0, Math.round(base * (0.3 + 0.7 * Math.sin(i * 0.4 + 1)) + Math.random() * base * 0.2));
  });

  const criticalTrend = trendData.map((v) => Math.round(v * 0.15 + Math.random() * 2));

  /* Sort table */
  const sorted = [...alerts].sort((a, b) => {
    const va = sortKey === "score" ? a.score : (a.risk_level === "CRITICAL" ? 4 : a.risk_level === "HIGH" ? 3 : a.risk_level === "MEDIUM" ? 2 : 1);
    const vb = sortKey === "score" ? b.score : (b.risk_level === "CRITICAL" ? 4 : b.risk_level === "HIGH" ? 3 : b.risk_level === "MEDIUM" ? 2 : 1);
    return sortDir === "desc" ? vb - va : va - vb;
  });

  const RISK_COLOR: Record<string, string> = { CRITICAL: "#f43f5e", HIGH: "#f59e0b", MEDIUM: "#8b5cf6", LOW: "#10b981" };
  const RISK_BG: Record<string, string> = { CRITICAL: "badge-critical", HIGH: "badge-high", MEDIUM: "badge-medium", LOW: "badge-low" };
  const TYPE_COLORS: Record<string, string> = { layering: "#f43f5e", smurfing: "#f59e0b", dormant: "#8b5cf6", kyc_mismatch: "#22d3ee", round_trip: "#10b981" };
  const maxType = Math.max(...Object.values(fraudTypeCounts), 1);

  return (
    <div className="flex flex-col h-screen overflow-hidden p-5 gap-4">

      {/* ── Header ─────────────────────────────────── */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Intelligence Overview</div>
          <h1 className="text-xl font-bold text-white">Analytics</h1>
        </div>
        <div className="text-xs text-slate-500">
          {alerts.length} accounts analyzed · Live data
        </div>
      </div>

      {/* ── Top Row: Charts ─────────────────────────── */}
      <div className="grid grid-cols-3 gap-4 flex-shrink-0">

        {/* 30-day trend */}
        <div className="glass rounded-2xl p-4 col-span-2">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Fraud Alerts — 30 Day Trend</div>
            <div className="flex items-center gap-4 text-[10px]">
              <div className="flex items-center gap-1.5"><div className="h-1.5 w-4 rounded-full bg-rose-400" /> Critical</div>
              <div className="flex items-center gap-1.5"><div className="h-1.5 w-4 rounded-full bg-cyan-400" /> All Alerts</div>
            </div>
          </div>
          <div className="relative">
            {/* Multi-line chart */}
            <svg viewBox="0 0 460 90" className="w-full" style={{ height: 90 }}>
              <defs>
                <linearGradient id="grad-cyan" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.2" />
                  <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
                </linearGradient>
                <linearGradient id="grad-rose2" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.15" />
                  <stop offset="100%" stopColor="#f43f5e" stopOpacity="0" />
                </linearGradient>
              </defs>
              {[trendData, criticalTrend].map((d, di) => {
                const W = 460, H = 90, pad = 10;
                const min = 0, max = Math.max(...trendData) || 1;
                const pts = d.map((v, i) => {
                  const x = pad + (i / (d.length - 1)) * (W - pad * 2);
                  const y = H - pad - ((v - min) / max) * (H - pad * 2);
                  return `${x},${y}`;
                }).join(" ");
                const color = di === 0 ? "#22d3ee" : "#f43f5e";
                const gradId = di === 0 ? "grad-cyan" : "grad-rose2";
                const areaStart = pts.split(" ")[0].split(",")[0];
                const areaEnd = pts.split(" ").slice(-1)[0].split(",")[0];
                const area = `M${areaStart},${H - pad} L${pts.split(" ").join(" L")} L${areaEnd},${H - pad} Z`;
                return (
                  <g key={di}>
                    <path d={area} fill={`url(#${gradId})`} />
                    <polyline points={pts} fill="none" stroke={color} strokeWidth={di === 0 ? "2" : "1.5"} strokeLinejoin="round" strokeDasharray={di === 0 ? "" : "4 2"} />
                  </g>
                );
              })}
              {/* Day labels */}
              {[0, 6, 13, 20, 29].map((i) => (
                <text key={i} x={10 + (i / 29) * 440} y={88} textAnchor="middle" fontSize="7" fill="#334155">
                  D-{29 - i}
                </text>
              ))}
            </svg>
          </div>
        </div>

        {/* Risk distribution */}
        <div className="glass rounded-2xl p-4">
          <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-3">Risk Distribution</div>
          <div className="space-y-2.5">
            {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((level) => (
              <div key={level} className="flex items-center gap-3">
                <div className={`flex-shrink-0 w-2 h-2 rounded-full`} style={{ background: RISK_COLOR[level] }} />
                <div className="flex-1 score-bar-track">
                  <div className="score-bar-fill" style={{
                    width: `${alerts.length ? (riskCounts[level] / alerts.length) * 100 : 0}%`,
                    background: RISK_COLOR[level],
                    animation: "bar-fill 1s ease-out both",
                  }} />
                </div>
                <div className="w-16 flex justify-between">
                  <span className="text-[10px] text-slate-500">{level}</span>
                  <span className="text-[10px] font-mono text-slate-400">{riskCounts[level]}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 border-t border-white/[0.06] pt-3">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2.5">By Fraud Type</div>
            <div className="space-y-2">
              {Object.entries(fraudTypeCounts).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                <HBar key={type} label={type} value={count} max={maxType} color={TYPE_COLORS[type] ?? "#64748b"} />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Table ──────────────────────────────────── */}
      <div className="glass rounded-2xl flex flex-col flex-1 min-h-0">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3.5 flex-shrink-0">
          <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Top Risky Accounts</div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setSortKey("score"); setSortDir(sortDir === "desc" ? "asc" : "desc"); }}
              className={`text-[10px] rounded-lg border px-2.5 py-1 transition ${sortKey === "score" ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-300" : "border-white/[0.06] text-slate-500 hover:text-slate-300"}`}
            >
              Sort by Score {sortKey === "score" ? (sortDir === "desc" ? "↓" : "↑") : ""}
            </button>
            <button
              onClick={() => { setSortKey("risk_level"); setSortDir(sortDir === "desc" ? "asc" : "desc"); }}
              className={`text-[10px] rounded-lg border px-2.5 py-1 transition ${sortKey === "risk_level" ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-300" : "border-white/[0.06] text-slate-500 hover:text-slate-300"}`}
            >
              Sort by Risk {sortKey === "risk_level" ? (sortDir === "desc" ? "↓" : "↑") : ""}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center h-20 text-slate-500 text-xs">Loading…</div>
          )}
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[#020617]/90 backdrop-blur">
              <tr className="border-b border-white/[0.04]">
                {["Account ID", "Risk", "Score", "Flagged For", "Detectors", "Action"].map((h) => (
                  <th key={h} className="px-5 py-2.5 text-left text-[10px] uppercase tracking-[0.15em] text-slate-600 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.03]">
              {sorted.map((alert, i) => (
                <tr key={alert.account_id} className="hover:bg-white/[0.02] transition animate-fade-in-up" style={{ animationDelay: `${i * 20}ms` }}>
                  <td className="px-5 py-3">
                    <span className="font-mono text-xs font-semibold text-white">{alert.account_id}</span>
                  </td>
                  <td className="px-5 py-3">
                    <span className={`text-[10px] font-bold uppercase px-2.5 py-1 rounded-lg ${RISK_BG[alert.risk_level]}`}>
                      {alert.risk_level}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-16 score-bar-track">
                        <div className="score-bar-fill" style={{
                          width: `${alert.score * 100}%`,
                          background: RISK_COLOR[alert.risk_level],
                          animation: "bar-fill 0.8s ease-out both",
                        }} />
                      </div>
                      <span className="font-mono text-xs text-slate-400">{alert.score.toFixed(3)}</span>
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex flex-wrap gap-1">
                      {alert.flagged_for.map((f) => (
                        <span key={f} className="text-[9px] uppercase px-1.5 py-0.5 rounded-md"
                          style={{ background: `${TYPE_COLORS[f] ?? "#64748b"}20`, color: TYPE_COLORS[f] ?? "#94a3b8", border: `1px solid ${TYPE_COLORS[f] ?? "#64748b"}30` }}>
                          {f.replace("_", " ")}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex gap-1">
                      {Object.entries(alert.detections).filter(([, v]) => v.detected).map(([k]) => (
                        <div key={k} className="h-1.5 w-1.5 rounded-full bg-rose-400" title={k} />
                      ))}
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => router.push(`/investigation/${alert.account_id}`)}
                        className="rounded-lg border border-cyan-400/20 bg-cyan-400/8 px-2.5 py-1 text-[10px] text-cyan-300 hover:bg-cyan-400/15 transition"
                      >
                        Investigate
                      </button>
                      <button
                        onClick={() => router.push(`/str-report?id=${alert.account_id}`)}
                        className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[10px] text-slate-400 hover:bg-white/[0.06] transition"
                      >
                        STR
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
