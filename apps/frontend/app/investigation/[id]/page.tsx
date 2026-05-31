"use client";
import { useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { fetchJson } from "../../lib/tracex";
import * as d3 from "d3";

/* ─── Types ─────────────────────────────────────────── */
type ScoreResponse = {
  account_id: string;
  is_flagged: boolean;
  risk_level: string;
  combined_score: number;
  flagged_for: string[];
  detections: {
    layering?: { detected: boolean; confidence?: number; error?: string };
    round_trip?: { detected: boolean; confidence?: number; error?: string };
    smurfing?: { detected: boolean; confidence?: number };
    dormant?: { detected: boolean; confidence?: number; dormancy_days?: number; volume_30d?: number };
    kyc_mismatch?: { detected: boolean; confidence?: number; mismatch_ratio?: number; severity?: string; expected_monthly?: number; actual_monthly?: number };
  };
};

type TraceResponse = {
  detected: boolean;
  fraud_type: string;
  chain?: string[];
  loop?: string[];
  amounts?: number[];
  timestamps?: string[];
  hops?: number;
  confidence?: number;
  error?: string;
};

type ShapResponse = {
  account_id: string;
  base_value: number;
  top_features: { feature: string; shap: number }[];
  error?: string;
};

/* ─── Helpers ─────────────────────────────────────────── */
const RISK_COLOR: Record<string, string> = { CRITICAL: "#f43f5e", HIGH: "#f59e0b", MEDIUM: "#8b5cf6", LOW: "#10b981" };
const RISK_BG: Record<string, string> = { CRITICAL: "badge-critical", HIGH: "badge-high", MEDIUM: "badge-medium", LOW: "badge-low" };

function fmtInr(n: number) {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

function getInsights(score: ScoreResponse): string[] {
  const ins: string[] = [];
  const d = score.detections;
  if (d.dormant?.detected) {
    const days = d.dormant.dormancy_days ?? 0;
    const vol = d.dormant.volume_30d ?? 0;
    ins.push(`Account dormant for ${days} days — ₹${(vol / 1e5).toFixed(1)}L transacted in last 30 days`);
  }
  if (d.smurfing?.detected) {
    ins.push(`LSTM smurfing model fired with ${((d.smurfing.confidence ?? 0) * 100).toFixed(1)}% confidence — structured below reporting thresholds`);
  }
  if (d.kyc_mismatch?.detected) {
    const ratio = d.kyc_mismatch.mismatch_ratio ?? 0;
    const exp = d.kyc_mismatch.expected_monthly ?? 0;
    const act = d.kyc_mismatch.actual_monthly ?? 0;
    ins.push(`KYC mismatch ${ratio.toFixed(1)}× — expected ₹${(exp / 1000).toFixed(0)}K/mo, actual ₹${(act / 1000).toFixed(0)}K/mo`);
  }
  if (d.layering?.detected && !d.layering.error) {
    ins.push(`Layering detected — funds moved through multiple hops within 2 hours`);
  }
  if (d.round_trip?.detected && !d.round_trip.error) {
    ins.push(`Round-trip detected — funds returned to origin account`);
  }
  if (ins.length === 0) ins.push(`Combined score ${score.combined_score.toFixed(3)} — account flagged for ${score.flagged_for.join(", ")}`);
  return ins.slice(0, 4);
}

/* ─── D3 Graph ─────────────────────────────────────── */
function FundFlowGraph({ chain, amounts, suspicious }: { chain: string[]; amounts: number[]; suspicious: boolean }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!chain.length || !svgRef.current || !wrapperRef.current) return;
    
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = wrapperRef.current.clientWidth || 600;
    const height = wrapperRef.current.clientHeight || 400;
    
    // Prepare data
    const nodes = chain.map((id, i) => ({ 
      id, 
      label: id.replace("ACC_", ""),
      isOrigin: i === 0,
      isDest: i === chain.length - 1
    }));
    
    const links = [];
    for (let i = 0; i < chain.length - 1; i++) {
      links.push({
        source: chain[i],
        target: chain[i + 1],
        amount: amounts[i]
      });
    }

    // Set up zoom & pan
    const zoom = d3.zoom().scaleExtent([0.3, 4]).on("zoom", (e) => {
      gMain.attr("transform", e.transform);
    });
    svg.call(zoom as any);

    const gMain = svg.append("g");

    // Defs for arrows & glow
    const defs = svg.append("defs");
    
    const createMarker = (id: string, color: string) => {
      defs.append("marker")
        .attr("id", id)
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 28)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("fill", color);
    };
    createMarker("arrow-normal", "#475569");
    createMarker("arrow-sus", "#f43f5e");

    const filter = defs.append("filter").attr("id", "glow");
    filter.append("feGaussianBlur").attr("stdDeviation", "5").attr("result", "coloredBlur");
    const feMerge = filter.append("feMerge");
    feMerge.append("feMergeNode").attr("in", "coloredBlur");
    feMerge.append("feMergeNode").attr("in", "SourceGraphic");

    // Simulation
    const simulation = d3.forceSimulation(nodes as any)
      .force("link", d3.forceLink(links).id((d: any) => d.id).distance(140))
      .force("charge", d3.forceManyBody().strength(-1200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(50));

    // Links
    const linkGroup = gMain.append("g")
      .attr("stroke-opacity", 0.6)
      .selectAll("g")
      .data(links)
      .enter().append("g");

    const linkPaths = linkGroup.append("line")
      .attr("stroke", suspicious ? "#f43f5e" : "#334155")
      .attr("stroke-width", suspicious ? 2 : 1.5)
      .attr("marker-end", suspicious ? "url(#arrow-sus)" : "url(#arrow-normal)");

    const linkLabels = linkGroup.append("text")
      .attr("font-size", "10")
      .attr("fill", suspicious ? "#fda4af" : "#64748b")
      .attr("font-family", "JetBrains Mono, monospace")
      .attr("text-anchor", "middle")
      .attr("dy", -6)
      .text((d: any) => d.amount != null ? fmtInr(d.amount) : "");

    // Nodes
    const nodeGroup = gMain.append("g")
      .selectAll("g")
      .data(nodes)
      .enter().append("g")
      .style("cursor", "grab")
      .call(d3.drag()
        .on("start", function(e, d: any) {
          d3.select(this).style("cursor", "grabbing");
          if (!e.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (e, d: any) => {
          d.fx = e.x; d.fy = e.y;
        })
        .on("end", function(e, d: any) {
          d3.select(this).style("cursor", "grab");
          if (!e.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        }) as any);

    // Node outer glow / pulsing rings
    nodeGroup.append("circle")
      .attr("r", 28)
      .attr("fill", "transparent")
      .attr("stroke", (d: any) => suspicious ? "rgba(244,63,94,0.3)" : "rgba(34,211,238,0.2)")
      .attr("stroke-width", 1)
      .attr("filter", suspicious ? "url(#glow)" : null)
      .attr("class", suspicious ? "animate-pulse" : "");

    // Node circles
    nodeGroup.append("circle")
      .attr("r", 22)
      .attr("fill", (d: any) => suspicious 
        ? (d.isOrigin ? "rgba(244,63,94,0.35)" : d.isDest ? "rgba(244,63,94,0.2)" : "rgba(244,63,94,0.1)")
        : "rgba(34,211,238,0.15)")
      .attr("stroke", (d: any) => suspicious ? "#f43f5e" : d.isOrigin ? "#22d3ee" : "#334155")
      .attr("stroke-width", (d: any) => d.isOrigin || d.isDest ? 2 : 1.5)
      .style("transition", "fill 0.3s");

    // Node Labels
    nodeGroup.append("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .attr("font-size", "7.5")
      .attr("font-family", "JetBrains Mono, monospace")
      .attr("fill", suspicious ? "#fda4af" : "#67e8f9")
      .attr("font-weight", "600")
      .style("pointer-events", "none")
      .text((d: any) => d.label);

    nodeGroup.append("text")
      .attr("y", 38)
      .attr("text-anchor", "middle")
      .attr("font-size", "9")
      .attr("fill", "#64748b")
      .style("pointer-events", "none")
      .text((d: any, i) => d.isOrigin ? "Origin" : d.isDest ? "Destination" : `Hop ${i}`);

    simulation.on("tick", () => {
      linkPaths
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);
      
      linkLabels
        .attr("x", (d: any) => (d.source.x + d.target.x) / 2)
        .attr("y", (d: any) => (d.source.y + d.target.y) / 2);

      nodeGroup.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
    });

    // Center initially
    setTimeout(() => {
      svg.transition().duration(750).call(
        zoom.transform as any, 
        d3.zoomIdentity.translate(width/2, height/2).scale(0.8).translate(-width/2, -height/2)
      );
    }, 100);

  }, [chain, amounts, suspicious]);

  return (
    <div ref={wrapperRef} className="relative w-full h-full min-h-[400px] bg-slate-900/40 rounded-xl border border-white/[0.04] overflow-hidden cursor-move shadow-inner">
      <svg ref={svgRef} className="w-full h-full" />
      <div className="absolute top-3 left-3 flex items-center gap-2 pointer-events-none bg-slate-900/60 px-3 py-1.5 rounded-lg border border-white/[0.05] backdrop-blur-md">
        <svg width="12" height="12" fill="none" stroke="#22d3ee" strokeWidth="2" viewBox="0 0 24 24"><path d="M5 9l-3 3 3 3M9 5l3-3 3 3M19 9l3 3-3 3M9 19l3 3 3-3M2 12h20M12 2v20"/></svg>
        <span className="text-[10px] uppercase tracking-widest text-cyan-400 font-semibold">Interactive D3 Force Graph</span>
      </div>
      <div className="absolute bottom-3 right-3 pointer-events-none text-[10px] text-slate-500 font-mono flex flex-col items-end gap-1">
        <span>Scroll to zoom</span>
        <span>Drag to pan / move nodes</span>
      </div>
    </div>
  );
}

/* ─── Score Bar ─────────────────────────────────────── */
function ScoreBar({ label, value, color, detected }: { label: string; value: number; color: string; detected: boolean }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <div className={`h-1.5 w-1.5 rounded-full ${detected ? "bg-rose-400 animate-pulse" : "bg-slate-600"}`} />
          <span className="text-xs text-slate-400">{label}</span>
        </div>
        <span className="font-mono text-xs text-slate-400">{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{
          width: `${value * 100}%`,
          background: detected ? color : "rgba(71,85,105,0.5)",
          animation: "bar-fill 1s ease-out both",
        }} />
      </div>
    </div>
  );
}

/* ─── Main Page ─────────────────────────────────────── */
export default function InvestigationPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const hintType = searchParams?.get("type") ?? "";
  const [score, setScore] = useState<ScoreResponse | null>(null);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [shap, setShap] = useState<ShapResponse | null>(null);
  const [narrative, setNarrative] = useState<string>("");
  const [loadingNarrative, setLoadingNarrative] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    // Determine trace hint: use URL ?type= param (passed from dashboard) or auto-detect
    const traceHint = hintType ? `?hint=${hintType}` : "";
    Promise.all([
      fetchJson<ScoreResponse>(`/score/${id}`),
      fetchJson<TraceResponse>(`/trace/${id}${traceHint}`),
      fetchJson<ShapResponse>(`/explain/dormant/${id}`).catch(() => null),
    ]).then(([s, t, sh]) => {
      setScore(s);
      setTrace(t);
      setShap(sh);
      // Kick off Gemini narrative (non-blocking)
      setLoadingNarrative(true);
      fetchJson<{narrative?: string; error?: string}>(`/narrative/${id}`)
        .then(res => setNarrative(res.narrative || res.error || ""))
        .catch(() => setNarrative(""))
        .finally(() => setLoadingNarrative(false));
    }).catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, hintType]);

  const chain = trace?.chain ?? trace?.loop ?? [];
  const amounts = trace?.amounts ?? [];
  const suspicious = trace?.detected ?? false;
  const insights = score ? getInsights(score) : [];
  const d = score?.detections ?? {};

  if (loading) return (
    <div className="flex h-screen items-center justify-center">
      <div className="text-center">
        <div className="inline-flex h-10 w-10 animate-spin rounded-full border-2 border-cyan-400/30 border-t-cyan-400" />
        <div className="mt-3 text-sm text-slate-400">Loading investigation…</div>
      </div>
    </div>
  );

  if (error) return (
    <div className="flex h-screen items-center justify-center">
      <div className="glass rounded-2xl p-8 max-w-sm text-center">
        <div className="text-rose-400 text-3xl mb-3">⚠</div>
        <div className="text-slate-300 text-sm">{error}</div>
        <button onClick={() => router.back()} className="mt-4 text-xs text-cyan-400 hover:text-cyan-300">← Back</button>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-screen overflow-hidden p-5 gap-4">

      {/* ── Header ─────────────────────────────────── */}
      <div className="flex items-center gap-4 flex-shrink-0">
        <button onClick={() => router.push("/dashboard")}
          className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-2 hover:bg-white/[0.08] transition">
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg>
        </button>
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Investigation · Fund Flow Analysis</div>
          <h1 className="text-xl font-bold text-white font-mono">{id}</h1>
        </div>
        {score && (
          <div className="ml-auto flex items-center gap-3">
            <span className={`text-sm font-bold uppercase px-4 py-2 rounded-xl ${RISK_BG[score.risk_level]}`}>
              {score.risk_level}
            </span>
            <div className="text-2xl font-bold font-mono" style={{ color: RISK_COLOR[score.risk_level] }}>
              {score.combined_score.toFixed(3)}
            </div>
            <button onClick={() => router.push(`/str-report?id=${id}`)}
              className="rounded-xl bg-cyan-400/10 border border-cyan-400/25 px-4 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-400/20 transition">
              Generate STR →
            </button>
          </div>
        )}
      </div>

      {/* ── Main Grid ──────────────────────────────── */}
      <div className="grid grid-cols-[240px_1fr] gap-4 flex-1 min-h-0">

        {/* ── Left: Account Info ────────────────────── */}
        <div className="flex flex-col gap-3 min-h-0 overflow-y-auto">
          {/* Account card */}
          <div className="glass rounded-2xl p-4 flex-shrink-0 animate-fade-in-left">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-3">Account Profile</div>
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.06] bg-white/[0.05] font-mono text-xs font-bold text-slate-300">
                {id?.slice(-3)}
              </div>
              <div>
                <div className="font-mono text-sm font-bold text-white">{id}</div>
                <div className="text-[10px] text-slate-500">
                  {score?.is_flagged ? "🚨 Flagged account" : "✅ Clean account"}
                </div>
              </div>
            </div>

            {/* Dormancy info — only show when account was actually dormant */}
            {d.dormant && (d.dormant.dormancy_days ?? 0) > 0 && (
              <div className="space-y-2 mb-3">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Days dormant</span>
                  <span className="font-mono font-semibold text-amber-300">{d.dormant.dormancy_days}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">30d volume</span>
                  <span className="font-mono font-semibold text-slate-300">{d.dormant.volume_30d != null ? fmtInr(d.dormant.volume_30d) : "—"}</span>
                </div>
              </div>
            )}

            {/* KYC info — only show when actually detected as mismatched */}
            {d.kyc_mismatch && d.kyc_mismatch.detected && (
              <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 p-3 space-y-1.5 mb-3">
                <div className="text-[10px] text-cyan-400/70 uppercase tracking-wide">KYC Profile</div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Expected / mo</span>
                  <span className="font-mono text-slate-300">{d.kyc_mismatch.expected_monthly != null ? fmtInr(d.kyc_mismatch.expected_monthly) : "—"}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Actual / mo</span>
                  <span className="font-mono font-semibold text-rose-400">
                    {d.kyc_mismatch.actual_monthly != null ? fmtInr(d.kyc_mismatch.actual_monthly) : "—"}
                  </span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Mismatch ratio</span>
                  <span className="font-mono font-bold text-rose-300">
                    {d.kyc_mismatch.mismatch_ratio?.toFixed(2)}×
                  </span>
                </div>
              </div>
            )}

            {/* Flagged for */}
            <div className="flex flex-wrap gap-1.5">
              {score?.flagged_for.map((f) => (
                <span key={f} className={`text-[9px] uppercase tracking-wide px-2 py-1 rounded-lg font-medium ${
                  f === "layering" ? "chip-layering" : f === "smurfing" ? "chip-smurfing" : f === "dormant" ? "chip-dormant" : f === "round_trip" ? "chip-round_trip" : "chip-kyc"
                }`}>{f.replace("_", " ")}</span>
              ))}
            </div>
          </div>

          {/* Detector scores */}
          <div className="glass rounded-2xl p-4 flex-shrink-0 animate-fade-in-left delay-100">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-3">Model Scores</div>
            <div className="space-y-3">
              {/* Each ScoreBar is dimmed if its pattern is NOT in flagged_for */}
              <div className={score?.flagged_for.includes("dormant") ? "" : "opacity-40"}>
                <ScoreBar label="Dormant (Isolation Forest)" value={d.dormant?.confidence ?? 0} color="#8b5cf6" detected={!!d.dormant?.detected} />
              </div>
              <div className={score?.flagged_for.includes("smurfing") ? "" : "opacity-40"}>
                <ScoreBar label="Smurfing (BiLSTM)" value={d.smurfing?.confidence ?? 0} color="#f59e0b" detected={!!d.smurfing?.detected} />
              </div>
              <div className={score?.flagged_for.includes("layering") ? "" : "opacity-40"}>
                <ScoreBar label="Layering (Neo4j)" value={d.layering?.confidence ?? 0} color="#f43f5e" detected={!!(d.layering?.detected && !d.layering.error)} />
              </div>
              <div className={score?.flagged_for.includes("round_trip") ? "" : "opacity-40"}>
                <ScoreBar label="Round Trip (Graph)" value={d.round_trip?.confidence ?? 0} color="#10b981" detected={!!(d.round_trip?.detected && !d.round_trip.error)} />
              </div>
              <div className={score?.flagged_for.includes("kyc_mismatch") ? "" : "opacity-40"}>
                <ScoreBar label="KYC Mismatch (Rules)" value={d.kyc_mismatch?.confidence ?? 0} color="#22d3ee" detected={!!d.kyc_mismatch?.detected} />
              </div>
            </div>
          </div>

          {/* SHAP explanation */}
          {shap && !shap.error && (
            <div className="glass rounded-2xl p-4 flex-shrink-0 animate-fade-in-left delay-200">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-3">SHAP Feature Importance</div>
              <div className="space-y-2">
                {shap.top_features.slice(0, 5).map((f) => {
                  const maxShap = Math.max(...shap.top_features.map((x) => Math.abs(x.shap)));
                  const pct = maxShap > 0 ? (Math.abs(f.shap) / maxShap) * 100 : 0;
                  return (
                    <div key={f.feature}>
                      <div className="flex justify-between text-[10px] mb-1">
                        <span className="text-slate-400 capitalize">{f.feature.replace("_", " ")}</span>
                        <span className={`font-mono ${f.shap >= 0 ? "text-rose-400" : "text-emerald-400"}`}>
                          {f.shap >= 0 ? "+" : ""}{f.shap.toFixed(4)}
                        </span>
                      </div>
                      <div className="score-bar-track">
                        <div className="score-bar-fill" style={{
                          width: `${pct}%`,
                          background: f.shap >= 0 ? "#f43f5e" : "#10b981",
                          animation: "bar-fill 0.8s ease-out both",
                        }} />
                      </div>
                    </div>
                  );
                })}
                <div className="text-[9px] text-slate-600 mt-2">base value: {shap.base_value.toFixed(4)}</div>
              </div>
            </div>
          )}
        </div>

        {/* ── Right: Graph + Insights ──────────────── */}
        <div className="flex flex-col gap-4 min-h-0">

          {/* D3 Graph */}
          <div className="glass rounded-2xl flex-1 min-h-0 flex flex-col">
            <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3.5 flex-shrink-0">
              <div className="flex items-center gap-3">
                <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Fund Flow Graph</div>
                {suspicious && (
                  <span className="animate-pulse-glow rounded-lg border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-[9px] uppercase font-bold text-rose-300">
                    Suspicious Path
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-[10px] text-slate-600">
                {trace?.fraud_type && <span className="text-slate-400 capitalize">{trace.fraud_type.replace("_", " ")}</span>}
                {trace?.hops != null && <span>· {trace.hops} hops</span>}
                {trace?.confidence != null && <span>· {(trace.confidence * 100).toFixed(0)}% confidence</span>}
              </div>
            </div>

            <div className="flex-1 p-4 min-h-0">
              {chain.length > 0 ? (
                <FundFlowGraph chain={chain} amounts={amounts} suspicious={suspicious} />
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
                  <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-6">
                    <svg width="32" height="32" fill="none" stroke="#334155" strokeWidth="1.5" viewBox="0 0 24 24" className="mx-auto mb-3">
                      <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
                    </svg>
                    <div className="text-sm text-slate-500">
                      {trace?.error
                        ? `Graph error: ${trace.error}`
                        : score?.flagged_for?.includes("smurfing") || score?.flagged_for?.includes("dormant") || score?.flagged_for?.includes("kyc_mismatch")
                        ? "No fund-flow graph for this fraud type"
                        : "Fund flow graph will appear here after detection"}
                    </div>
                    <div className="mt-1 text-xs text-slate-600">
                      {score?.flagged_for?.includes("smurfing") ? "Smurfing uses LSTM sequence analysis" :
                       score?.flagged_for?.includes("dormant") ? "Dormancy uses Isolation Forest on account metrics" :
                       score?.flagged_for?.includes("kyc_mismatch") ? "KYC Mismatch is detected via income-to-volume ratio" :
                       "Graph detection requires layering or round-trip pattern"}
                    </div>
                  </div>
                  {/* Show score detections as pattern tiles */}
                  <div className="grid grid-cols-2 gap-3 w-full max-w-md">
                    {Object.entries(d).map(([k, v]) => (
                      <div key={k} className={`rounded-xl border p-3 ${
                        v.detected
                          ? k === "layering" || k === "round_trip" ? "border-rose-400/40 bg-rose-400/8 ring-1 ring-rose-400/20"
                          : k === "smurfing" ? "border-amber-400/40 bg-amber-400/5"
                          : k === "kyc_mismatch" ? "border-cyan-400/40 bg-cyan-400/5"
                          : "border-purple-400/40 bg-purple-400/5"
                          : "border-white/[0.06] bg-white/[0.03]"
                      }`}>
                        <div className="text-[10px] text-slate-500 capitalize mb-1">{k.replace(/_/g, " ")}</div>
                        <div className={`text-lg font-bold font-mono ${
                          v.detected
                            ? k === "layering" || k === "round_trip" ? "text-rose-400"
                            : k === "smurfing" ? "text-amber-400"
                            : k === "kyc_mismatch" ? "text-cyan-400"
                            : "text-purple-400"
                            : "text-slate-600"
                        }`}>
                          {v.confidence != null ? (v.confidence * 100).toFixed(1) + "%" : v.detected ? "✓" : "—"}
                        </div>
                        <div className={`text-[9px] mt-0.5 font-semibold ${v.detected ? "text-rose-300" : "text-slate-600"}`}>
                          {v.detected ? "DETECTED" : "CLEAR"}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* AI Insights — Gemini-powered narrative OR rule-based bullets */}
          <div className="glass rounded-2xl p-5 flex-shrink-0 animate-fade-in-up">
            <div className="flex items-center gap-2 mb-3">
              <svg width="14" height="14" fill="none" stroke="#22d3ee" strokeWidth="2" viewBox="0 0 24 24">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
              <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-400/70">AI-Generated Insights</div>
              {loadingNarrative && (
                <div className="ml-2 h-3 w-3 animate-spin rounded-full border-2 border-cyan-400/30 border-t-cyan-400" />
              )}
            </div>
            {narrative ? (
              <p className="text-sm leading-relaxed text-slate-300 whitespace-pre-line">{narrative}</p>
            ) : (
              <div className="space-y-2">
                {insights.map((ins, i) => (
                  <div key={i} className="flex items-start gap-3 animate-fade-in-up" style={{ animationDelay: `${i * 100}ms` }}>
                    <div className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-rose-400" />
                    <p className="text-sm leading-relaxed text-slate-300">{ins}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
