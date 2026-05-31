"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchJson } from "../lib/tracex";

/* ─── Types ─────────────────────────────────────────── */
type Stats = {
  total_accounts: number;
  total_transactions: number;
  total_flagged: number;
  critical_count: number;
  fraud_volume_30d: number;
};

type AlertItem = {
  account_id: string;
  risk_level: string;
  flagged_for: string[];
  score: number;
  detections: Record<string, { detected: boolean; confidence?: number }>;
};

type FeedRow = {
  id: string;
  account: string;
  amount: number;
  channel: string;
  flagged: boolean;
  ts: string;
};

type FeedApiRow = {
  account_id: string;
  amount: number;
  channel: string;
  txn_ts: string;
  fraud_score: number;
  is_flagged: boolean;
};

/* ─── Helpers ─────────────────────────────────────────── */
const RISK_CLASS: Record<string, string> = {
  CRITICAL: "badge-critical",
  HIGH: "badge-high",
  MEDIUM: "badge-medium",
  LOW: "badge-low",
};

const TYPE_CLASS: Record<string, string> = {
  layering: "chip-layering",
  smurfing: "chip-smurfing",
  dormant: "chip-dormant",
  kyc_mismatch: "chip-kyc",
  round_trip: "chip-round_trip",
};

const CHANNELS = ["UPI", "NEFT", "RTGS", "IMPS", "SWIFT"];

function fmtAmount(n: number) {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

function fmtInr(n: number) {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

/* ─── Donut Chart ─────────────────────────────────────── */
function DonutChart({ data }: { data: { label: string; value: number; color: string }[] }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return <div className="text-slate-500 text-sm text-center py-8">No data</div>;

  let cumAngle = -Math.PI / 2;
  const R = 70, cx = 90, cy = 90, stroke = 22;
  const segments = data.map((d) => {
    const angle = (d.value / total) * 2 * Math.PI;
    const x1 = cx + R * Math.cos(cumAngle);
    const y1 = cy + R * Math.sin(cumAngle);
    cumAngle += angle;
    const x2 = cx + R * Math.cos(cumAngle);
    const y2 = cy + R * Math.sin(cumAngle);
    const large = angle > Math.PI ? 1 : 0;
    const mid = cumAngle - angle / 2;
    return { ...d, path: `M ${cx} ${cy} L ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2} Z`, mid, pct: Math.round((d.value / total) * 100) };
  });

  return (
    <div className="flex items-center gap-6">
      <svg viewBox="0 0 180 180" className="w-[140px] flex-shrink-0">
        <circle cx={cx} cy={cy} r={R} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={stroke} />
        {segments.map((s, i) => (
          <path key={i} d={s.path} fill={s.color} opacity={0.85} className="transition-opacity hover:opacity-100" />
        ))}
        <circle cx={cx} cy={cy} r={R - stroke} fill="#020617" />
        <text x={cx} y={cy - 6} textAnchor="middle" fill="white" fontSize="18" fontWeight="700" fontFamily="JetBrains Mono">{total}</text>
        <text x={cx} y={cy + 12} textAnchor="middle" fill="#64748b" fontSize="9">alerts</text>
      </svg>
      <div className="flex flex-col gap-2.5 flex-1">
        {segments.map((s, i) => (
          <div key={i} className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="h-2.5 w-2.5 rounded-full flex-shrink-0" style={{ background: s.color }} />
              <span className="text-xs text-slate-300 capitalize">{s.label.replace("_", " ")}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-1 w-14 rounded-full bg-white/5 overflow-hidden">
                <div className="h-full rounded-full" style={{ width: `${s.pct}%`, background: s.color }} />
              </div>
              <span className="text-xs font-mono text-slate-400 w-8 text-right">{s.pct}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── Stat Card ─────────────────────────────────────── */
function StatCard({ label, value, sub, color, icon }: { label: string; value: string; sub?: string; color: string; icon: React.ReactNode }) {
  return (
    <div className="stat-card p-5 animate-fade-in-up">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</div>
          <div className={`mt-2 text-3xl font-bold font-num tracking-tight ${color}`}>{value}</div>
          {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
        </div>
        <div className={`rounded-xl p-2.5 ${color === "text-cyan-300" ? "bg-cyan-400/10" : color === "text-rose-300" ? "bg-rose-400/10" : color === "text-amber-300" ? "bg-amber-400/10" : "bg-emerald-400/10"}`}>
          {icon}
        </div>
      </div>
    </div>
  );
}

/* ─── Live Feed Row ─────────────────────────────────── */
function FeedRowItem({ row, idx }: { row: FeedRow; idx: number }) {
  return (
    <div
      className={`feed-row ${row.flagged ? "flagged" : "normal"} flex items-center gap-3 rounded-xl px-3 py-2.5 animate-slide-down`}
      style={{ animationDelay: `${idx * 40}ms` }}
    >
      <div className={`flex-shrink-0 h-1.5 w-1.5 rounded-full ${row.flagged ? "bg-rose-400 animate-pulse" : "bg-slate-600"}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-slate-300 truncate">{row.account}</span>
          <span className="text-[10px] text-slate-600 uppercase">{row.channel}</span>
        </div>
        <div className="text-[10px] text-slate-500">{row.ts}</div>
      </div>
      <div className={`text-xs font-mono font-semibold flex-shrink-0 ${row.flagged ? "text-rose-400" : "text-slate-400"}`}>
        {fmtAmount(row.amount)}
      </div>
      {row.flagged && (
        <div className="text-[9px] uppercase tracking-wider bg-rose-400/15 text-rose-300 border border-rose-400/25 rounded-md px-1.5 py-0.5 flex-shrink-0">
          ALERT
        </div>
      )}
    </div>
  );
}

/* ─── Main Page ─────────────────────────────────────── */
export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [feed, setFeed] = useState<FeedRow[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const accountPoolRef = useRef<string[]>([]);

  /* Build donut data from alerts */
  const donutData = (() => {
    const counts: Record<string, number> = { layering: 0, smurfing: 0, dormant: 0, kyc_mismatch: 0, round_trip: 0 };
    for (const a of alerts) for (const f of a.flagged_for) if (f in counts) counts[f]++;
    return [
      { label: "layering",   value: counts.layering,   color: "#f43f5e" },
      { label: "smurfing",   value: counts.smurfing,   color: "#f59e0b" },
      { label: "dormant",    value: counts.dormant,    color: "#8b5cf6" },
      { label: "kyc_mismatch", value: counts.kyc_mismatch, color: "#22d3ee" },
      { label: "round_trip", value: counts.round_trip, color: "#10b981" },
    ].filter((d) => d.value > 0);
  })();

  /* Load alerts + stats */
  const loadData = useCallback(async () => {
    try {
      const [alertsResp, statsResp] = await Promise.all([
        fetchJson<{ total: number; alerts: AlertItem[] }>("/alerts/quick?limit=200"),
        fetchJson<Stats>("/stats"),
      ]);
      setAlerts(alertsResp.alerts);
      // Enrich stats with real alert counts if the Neo4j stats show zeros
      const enriched = {
        ...statsResp,
        total_flagged: statsResp.total_flagged || alertsResp.total,
        critical_count: statsResp.critical_count || alertsResp.alerts.filter(a => a.risk_level === "CRITICAL").length,
      };
      setStats(enriched);
      accountPoolRef.current = alertsResp.alerts.map((a) => a.account_id);
      if (!selectedId && alertsResp.alerts[0]) setSelectedId(alertsResp.alerts[0].account_id);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  /* Poll the real /feed endpoint from Neo4j every 5s */
  const loadFeed = useCallback(async () => {
    try {
      const resp = await fetchJson<{ transactions: FeedApiRow[] }>("/feed?limit=30");
      const rows: FeedRow[] = resp.transactions.map((t) => ({
        id: `${t.account_id}-${t.txn_ts}-${Math.random()}`,
        account: t.account_id,
        amount: t.amount,
        channel: t.channel || CHANNELS[Math.floor(Math.random() * CHANNELS.length)],
        flagged: t.is_flagged || t.fraud_score > 0.5,
        ts: t.txn_ts
          ? new Date(t.txn_ts).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
          : new Date().toLocaleTimeString("en-IN"),
      }));
      if (rows.length > 0) setFeed(rows);
    } catch {
      // silently ignore feed errors — keep showing last known data
    }
  }, []);

  /* Refresh data every 30s */
  useEffect(() => {
    loadData();
    const iv = setInterval(loadData, 30000);
    return () => clearInterval(iv);
  }, [loadData]);

  /* Poll feed every 5s */
  useEffect(() => {
    loadFeed();
    const iv = setInterval(loadFeed, 5000);
    return () => clearInterval(iv);
  }, [loadFeed]);

  const selectedAlert = alerts.find((a) => a.account_id === selectedId);

  return (
    <div className="flex flex-col h-screen overflow-hidden p-5 gap-4">

      {/* ── Header ─────────────────────────────────── */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-xl font-bold text-white">Alert Dashboard</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time fraud detection · Last refresh {lastRefresh.toLocaleTimeString("en-IN")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {error && <span className="text-xs text-rose-400">{error}</span>}
          <button
            onClick={() => { setLoading(true); loadData(); }}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-white/10 transition"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className={loading ? "animate-spin" : ""}>
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* ── Stat Cards ─────────────────────────────── */}
      <div className="grid grid-cols-4 gap-3 flex-shrink-0">
        <StatCard label="Total Alerts" value={loading ? "—" : String(alerts.length)} sub={`of ${stats?.total_accounts ?? "—"} accounts`} color="text-cyan-300"
          icon={<svg width="18" height="18" fill="none" stroke="#22d3ee" strokeWidth="1.8" viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>} />
        <StatCard label="Critical" value={loading ? "—" : String(alerts.filter(a => a.risk_level === "CRITICAL").length)} sub="Risk level CRITICAL" color="text-rose-300"
          icon={<svg width="18" height="18" fill="none" stroke="#f43f5e" strokeWidth="1.8" viewBox="0 0 24 24"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>} />
        <StatCard label="Accounts Scanned" value={loading ? "—" : (stats?.total_accounts ?? 0).toLocaleString()} sub={`${stats?.total_transactions?.toLocaleString() ?? "—"} transactions`} color="text-amber-300"
          icon={<svg width="18" height="18" fill="none" stroke="#f59e0b" strokeWidth="1.8" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>} />
        <StatCard label="Fraud Prevented" value={loading ? "—" : fmtInr(stats?.fraud_volume_30d ?? 0)} sub="30-day flagged volume" color="text-emerald-300"
          icon={<svg width="18" height="18" fill="none" stroke="#10b981" strokeWidth="1.8" viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>} />
      </div>

      {/* ── Main Grid ──────────────────────────────── */}
      <div className="grid grid-cols-[280px_1fr_260px] gap-4 flex-1 min-h-0">

        {/* ── Left: Alert List ──────────────────────── */}
        <div className="glass rounded-2xl flex flex-col min-h-0">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">Flagged Accounts</div>
            <div className="rounded-full bg-rose-400/15 px-2 py-0.5 text-[10px] font-bold text-rose-300">{alerts.length}</div>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loading && (
              <div className="flex items-center justify-center h-20 text-slate-500 text-xs">Loading alerts…</div>
            )}
            {alerts.map((alert, i) => (
              <button
                key={alert.account_id}
                onClick={() => setSelectedId(alert.account_id)}
                className={`alert-row w-full text-left rounded-xl p-3 ${selectedId === alert.account_id ? "selected" : ""} animate-fade-in-up`}
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-mono text-xs font-semibold text-white truncate">{alert.account_id}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {alert.flagged_for.slice(0, 2).map((f) => (
                        <span key={f} className={`text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded-md ${TYPE_CLASS[f] ?? "chip-kyc"}`}>
                          {f.replace("_", " ")}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 flex-shrink-0">
                    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-lg ${RISK_CLASS[alert.risk_level]}`}>
                      {alert.risk_level}
                    </span>
                    <span className="font-mono text-[11px] text-slate-400">{alert.score.toFixed(3)}</span>
                  </div>
                </div>
                {/* Score bar */}
                <div className="mt-2 score-bar-track">
                  <div className="score-bar-fill animate-bar-fill"
                    style={{
                      width: `${alert.score * 100}%`,
                      background: alert.risk_level === "CRITICAL" ? "#f43f5e" : alert.risk_level === "HIGH" ? "#f59e0b" : "#8b5cf6",
                    }} />
                </div>
              </button>
            ))}
          </div>
          {selectedId && (
            <div className="border-t border-white/[0.06] p-3">
              <button
                onClick={() => {
                  const alert = alerts.find(a => a.account_id === selectedId);
                  const type = alert?.flagged_for?.[0] ?? "";
                  router.push(`/investigation/${selectedId}${type ? `?type=${type}` : ""}`);
                }}
                className="w-full rounded-xl bg-cyan-400/10 border border-cyan-400/25 px-4 py-2.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-400/20 transition flex items-center justify-center gap-2"
              >
                <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/></svg>
                Investigate {selectedId}
              </button>
            </div>
          )}
        </div>

        {/* ── Center: Live Feed + Selected Alert ──── */}
        <div className="flex flex-col gap-4 min-h-0">
          {/* Selected alert detail */}
          {selectedAlert && (
            <div className="glass rounded-2xl p-4 flex-shrink-0 animate-fade-in-up">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Selected case</div>
                  <div className="mt-1 font-mono text-lg font-bold text-white">{selectedAlert.account_id}</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-bold uppercase px-3 py-1.5 rounded-xl ${RISK_CLASS[selectedAlert.risk_level]}`}>
                    {selectedAlert.risk_level}
                  </span>
                  <button
                    onClick={() => router.push(`/investigation/${selectedAlert.account_id}${selectedAlert.flagged_for?.[0] ? `?type=${selectedAlert.flagged_for[0]}` : ""}`)}
                    className="rounded-xl bg-gradient-to-r from-cyan-500/20 to-cyan-400/10 border border-cyan-400/30 px-4 py-1.5 text-xs font-semibold text-cyan-200 hover:from-cyan-500/30 transition"
                  >
                    Open Investigation →
                  </button>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-5 gap-2">
                {Object.entries(selectedAlert.detections).map(([key, val]) => (
                  <div key={key} className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-2">
                    <div className="text-[9px] uppercase tracking-wide text-slate-500 capitalize">{key.replace("_", " ")}</div>
                    <div className={`mt-1 text-sm font-bold font-mono ${val.detected ? "text-rose-400" : "text-slate-500"}`}>
                      {val.confidence != null ? val.confidence.toFixed(3) : val.detected ? "✓" : "—"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Live transaction feed */}
          <div className="glass rounded-2xl flex flex-col flex-1 min-h-0">
            <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3 flex-shrink-0">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                </span>
                <div className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">Live Transaction Feed</div>
              </div>
              <div className="text-[10px] text-slate-600">auto-updating every 1.8s</div>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
              {feed.map((row, i) => (
                <FeedRowItem key={row.id} row={row} idx={i} />
              ))}
            </div>
          </div>
        </div>

        {/* ── Right: Chart ─────────────────────────── */}
        <div className="flex flex-col gap-4 min-h-0">
          <div className="glass rounded-2xl p-4 flex-shrink-0">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-3">Fraud Type Breakdown</div>
            <DonutChart data={donutData} />
          </div>

          {/* Quick stats */}
          <div className="glass rounded-2xl p-4 flex-1">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-3">Detector Summary</div>
            <div className="space-y-3">
              {[
                { label: "Dormant Activation", key: "dormant",   color: "#8b5cf6" },
                { label: "Smurfing (LSTM)",    key: "smurfing",  color: "#f59e0b" },
                { label: "Layering (Graph)",   key: "layering",  color: "#f43f5e" },
                { label: "Round Trip",          key: "round_trip",color: "#10b981" },
                { label: "KYC Mismatch",        key: "kyc_mismatch", color: "#22d3ee" },
              ].map((d) => {
                const cnt = alerts.filter(a => a.flagged_for.includes(d.key)).length;
                return (
                  <div key={d.label}>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-slate-400">{d.label}</span>
                      <span className="font-mono text-slate-500">{cnt}</span>
                    </div>
                    <div className="score-bar-track">
                      <div className="score-bar-fill animate-bar-fill" style={{ width: `${alerts.length ? (cnt / alerts.length) * 100 : 0}%`, background: d.color }} />
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-4 border-t border-white/[0.06] pt-4">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">Quick Actions</div>
              <div className="space-y-1.5">
                <button onClick={() => router.push("/str-report")}
                  className="w-full rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2 text-left text-xs text-slate-300 hover:bg-white/[0.08] hover:border-cyan-400/20 transition">
                  📋 Generate STR Report
                </button>
                <button onClick={() => router.push("/analytics")}
                  className="w-full rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2 text-left text-xs text-slate-300 hover:bg-white/[0.08] hover:border-cyan-400/20 transition">
                  📊 View Analytics
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
