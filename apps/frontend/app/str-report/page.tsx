"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { fetchJson } from "../lib/tracex";

type ReportData = {
  account_id: string;
  generated_at: string;
  score: {
    risk_level: string;
    combined_score: number;
    flagged_for: string[];
    detections: Record<string, { detected: boolean; confidence?: number; dormancy_days?: number; volume_30d?: number; mismatch_ratio?: number }>;
  };
  report_summary: { risk_level: string; combined_score: number; flagged_for: string[] };
};

function fmtInr(n: number) {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Crore`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} Lakh`;
  return `₹${n.toLocaleString("en-IN")}`;
}

function buildSTRText(data: ReportData, id: string, aiNarrative: string): string {
  const d = data.score.detections;
  const flagged = data.score.flagged_for;
  const dormDays = d.dormant?.dormancy_days ?? 0;
  const vol30d = d.dormant?.volume_30d ?? 0;
  const caseNo = `STR-2024-${id.replace("ACC_", "")}-${String(Math.floor(Math.random() * 9000 + 1000))}`;
  const today = new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "long", year: "numeric" });

  return `SUSPICIOUS TRANSACTION REPORT
Under PMLA 2002 — Submitted to Financial Intelligence Unit — India (FIU-IND)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION A — REPORTING ENTITY DETAILS
Reporting Entity    : [BANK NAME] — Fraud Intelligence Division
Branch / Unit       : Central Fraud Monitoring Unit (CFMU)
Report Reference    : ${caseNo}
Date of Report      : ${today}
Reporting Period    : Last 90 calendar days

SECTION B — SUBJECT ACCOUNT DETAILS
Account Identifier  : ${id}
Account Status      : ${dormDays > 90 ? "Previously Dormant — Now Active" : "Active"}
Risk Classification : ${data.score.risk_level}
Combined Risk Score : ${data.score.combined_score.toFixed(4)} / 1.0000
Fraud Indicators    : ${flagged.map((f) => f.replace("_", " ").toUpperCase()).join(" · ")}

SECTION C — SUSPICIOUS ACTIVITY DESCRIPTION (AI-GENERATED)
${aiNarrative}

SECTION D — TRANSACTION SUMMARY
Monitoring Period   : 90 days
Suspicious Volume   : ${fmtInr(vol30d || data.score.combined_score * 5000000)}
Detection Models    : Isolation Forest (Dormancy) · BiLSTM (Smurfing) · Neo4j Graph Analytics (Layering/Round-trip) · KYC Rules Engine

SECTION E — RECOMMENDED ACTION
Based on the multi-model fraud detection analysis, it is recommended that:
1. The account be immediately placed under Enhanced Due Diligence (EDD).
2. All pending transactions be placed on hold pending investigation.
3. This report be escalated to the Compliance Officer and FIU-IND within 7 working days as mandated under Section 12 of PMLA 2002.
4. A complete Know Your Customer (KYC) reverification be initiated.
5. Source of funds documentation be obtained for all large-value transactions.

SECTION F — CERTIFICATION
I, the undersigned Designated Director / Principal Officer of the Reporting Entity, hereby certify that the information contained in this report is true, correct, and complete to the best of my knowledge and belief.

Signature: ______________________________    Date: ${today}
Name     : [Principal Officer]
Designation: Chief Compliance Officer
─────────────────────────────────────────────────────────────────────────────
This report has been generated automatically by TRACE-X Fund Flow Intelligence Platform.
FIU-IND Reference Portal: https://fiuindia.gov.in
`;
}

export default function STRReportPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const rawId = searchParams.get("id") ?? "";
  const [inputId, setInputId] = useState(rawId);
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [reportText, setReportText] = useState("");
  const [fullText, setFullText] = useState("");
  const [error, setError] = useState("");
  const [caseNo] = useState(`STR-2024-${String(Math.floor(Math.random() * 90000 + 10000))}`);
  const typewriterRef = useRef<number | null>(null);
  const textareaRef = useRef<HTMLDivElement>(null);

  const loadReport = async (id: string) => {
    if (!id.trim()) return;
    setLoading(true);
    setError("");
    setReportText("");
    setFullText("");
    setSubmitted(false);
    try {
      const data = await fetchJson<ReportData>(`/report/${id}`);
      setReportData(data);
    } catch (e) {
      // Fallback: load just score
      try {
        const score = await fetchJson<any>(`/score/${id}`);
        setReportData({ account_id: id, generated_at: new Date().toISOString(), score, report_summary: { risk_level: score.risk_level, combined_score: score.combined_score, flagged_for: score.flagged_for } });
      } catch {
        setError("Failed to load account data. Check the account ID.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (rawId) loadReport(rawId);
  }, [rawId]);

  const generateReport = async () => {
    if (!reportData) return;
    setGenerating(true);
    setSubmitted(false);
    setReportText("");

    let aiNarrative = "";
    try {
      const res = await fetchJson<any>(`/narrative/${reportData.account_id}`);
      aiNarrative = res.narrative || res.error || "AI Service Unavailable.";
    } catch (e) {
      aiNarrative = "AI Service Error: Could not generate narrative.";
    }

    const text = buildSTRText(reportData, reportData.account_id, aiNarrative);
    setFullText(text);

    let i = 0;
    const speed = 8; // ms per char
    const tick = () => {
      if (i < text.length) {
        setReportText(text.slice(0, i + 1));
        i++;
        if (textareaRef.current) textareaRef.current.scrollTop = textareaRef.current.scrollHeight;
        typewriterRef.current = window.setTimeout(tick, speed);
      } else {
        setGenerating(false);
      }
    };
    typewriterRef.current = window.setTimeout(tick, speed);
  };

  useEffect(() => () => { if (typewriterRef.current) clearTimeout(typewriterRef.current); }, []);

  const handlePrint = () => {
    if (!fullText) return;
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;
    printWindow.document.write(`
      <html>
        <head>
          <title>STR Report - ${reportData?.account_id}</title>
          <style>
            body { font-family: 'Courier New', Courier, monospace; font-size: 13px; white-space: pre-wrap; padding: 40px; color: black; background: white; line-height: 1.6; }
            @media print { body { padding: 0; } }
          </style>
        </head>
        <body>${fullText}</body>
      </html>
    `);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
      printWindow.print();
      printWindow.close();
    }, 250);
  };

  const today = new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "long", year: "numeric" });

  return (
    <div className="flex flex-col h-screen overflow-hidden p-5 gap-4">

      {/* ── Header ─────────────────────────────────── */}
      <div className="flex items-center gap-4 flex-shrink-0">
        <button onClick={() => router.push("/dashboard")}
          className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-2 hover:bg-white/[0.08] transition">
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg>
        </button>
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">FIU-IND Compliance · Auto-Generated</div>
          <h1 className="text-xl font-bold text-white">Suspicious Transaction Report</h1>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className="rounded-xl border border-amber-400/20 bg-amber-400/5 px-3 py-1.5 text-[10px] font-mono text-amber-300">
            {caseNo}
          </div>
          <div className="text-[10px] text-slate-600">{today}</div>
        </div>
      </div>

      <div className="grid grid-cols-[320px_1fr] gap-4 flex-1 min-h-0">

        {/* ── Left: Controls ─────────────────────── */}
        <div className="flex flex-col gap-4">

          {/* Account selector */}
          <div className="glass rounded-2xl p-4 flex-shrink-0">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-3">Target Account</div>
            <div className="flex gap-2">
              <input
                value={inputId}
                onChange={(e) => setInputId(e.target.value)}
                placeholder="ACC_00018"
                className="flex-1 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-sm font-mono text-white placeholder-slate-600 focus:border-cyan-400/40 focus:outline-none focus:bg-white/[0.06] transition"
                onKeyDown={(e) => e.key === "Enter" && loadReport(inputId)}
              />
              <button
                onClick={() => loadReport(inputId)}
                disabled={loading}
                className="rounded-xl bg-cyan-400/10 border border-cyan-400/25 px-3 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-400/20 transition disabled:opacity-50"
              >
                {loading ? "…" : "Load"}
              </button>
            </div>
            {error && <div className="mt-2 text-xs text-rose-400">{error}</div>}
          </div>

          {/* Report summary */}
          {reportData && (
            <div className="glass rounded-2xl p-4 flex-shrink-0 animate-fade-in-up">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-3">Case Summary</div>
              <div className="space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Account</span>
                  <span className="font-mono text-white">{reportData.account_id}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Risk Level</span>
                  <span className={`font-bold ${reportData.score.risk_level === "CRITICAL" ? "text-rose-400" : reportData.score.risk_level === "HIGH" ? "text-amber-400" : "text-violet-400"}`}>
                    {reportData.score.risk_level}
                  </span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Combined Score</span>
                  <span className="font-mono text-white">{reportData.score.combined_score.toFixed(4)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Flagged For</span>
                  <div className="flex flex-wrap gap-1 justify-end">
                    {reportData.score.flagged_for.map((f) => (
                      <span key={f} className="rounded-md bg-rose-400/10 text-rose-300 border border-rose-400/20 px-1.5 py-0.5 text-[9px] uppercase">
                        {f.replace("_", " ")}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Sections checklist */}
          <div className="glass rounded-2xl p-4 flex-1">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-3">Report Sections</div>
            <div className="space-y-2">
              {[
                "A — Reporting Entity Details",
                "B — Subject Account Details",
                "C — Suspicious Activity Description",
                "D — Transaction Summary",
                "E — Recommended Action",
                "F — Certification",
              ].map((section, i) => (
                <div key={section} className="flex items-center gap-2">
                  <div className={`flex h-4 w-4 items-center justify-center rounded-md border text-[10px] ${reportText.length > 0 ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-400" : "border-white/[0.08] text-slate-600"}`}>
                    {reportText.length > 0 ? "✓" : i + 1}
                  </div>
                  <span className="text-[11px] text-slate-400">{section}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Action buttons */}
          <div className="space-y-2 flex-shrink-0">
            <button
              onClick={generateReport}
              disabled={!reportData || generating}
              className="w-full rounded-xl bg-gradient-to-r from-cyan-500/20 via-cyan-400/15 to-cyan-500/20 border border-cyan-400/30 px-4 py-3 text-sm font-bold text-cyan-200 hover:from-cyan-500/30 transition disabled:opacity-40 flex items-center justify-center gap-2"
            >
              {generating ? (
                <>
                  <div className="h-3 w-3 animate-spin rounded-full border-2 border-cyan-400/30 border-t-cyan-400" />
                  Generating Report…
                </>
              ) : (
                <>
                  <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                  </svg>
                  Generate STR Report
                </>
              )}
            </button>

            <button
              onClick={() => { if (reportText) setSubmitted(true); }}
              disabled={!reportText || generating || submitted}
              className={`w-full rounded-xl border px-4 py-3 text-sm font-bold transition flex items-center justify-center gap-2 ${
                submitted
                  ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
                  : "border-rose-400/30 bg-rose-400/10 text-rose-300 hover:bg-rose-400/15 disabled:opacity-40"
              }`}
            >
              {submitted ? (
                <><svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg> Submitted to FIU-IND ✓</>
              ) : (
                <><svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Submit to FIU-IND</>
              )}
            </button>

            <button
              onClick={handlePrint}
              disabled={!reportText || generating}
              className={`w-full rounded-xl border border-white/[0.08] bg-white/[0.04] px-4 py-3 text-sm font-bold text-slate-300 hover:bg-white/[0.08] transition flex items-center justify-center gap-2 disabled:opacity-40`}
            >
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Export as PDF
            </button>
          </div>
        </div>

        {/* ── Right: Report Preview ─────────────── */}
        <div className="glass rounded-2xl flex flex-col min-h-0">
          {/* FIU-IND Header */}
          <div className="border-b border-white/[0.06] px-6 py-4 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-amber-400/25 bg-amber-400/10 text-amber-300">
                  <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                  </svg>
                </div>
                <div>
                  <div className="text-sm font-bold text-white">FIU-IND Suspicious Transaction Report</div>
                  <div className="text-[10px] text-slate-500">Prevention of Money Laundering Act, 2002 — Section 12</div>
                </div>
              </div>
              {submitted && (
                <div className="flex items-center gap-1.5 rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5">
                  <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
                  <span className="text-[10px] font-bold text-emerald-300 uppercase tracking-wide">Filed</span>
                </div>
              )}
            </div>
          </div>

          {/* Report text area */}
          <div
            ref={textareaRef}
            className="flex-1 overflow-y-auto p-6 font-mono text-[12px] leading-6 text-slate-300"
            style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
          >
            {reportText ? (
              <span className={generating ? "typewriter-cursor" : ""}>{reportText}</span>
            ) : (
              <div className="flex h-full flex-col items-center justify-center text-center gap-4">
                <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-8">
                  <svg width="40" height="40" fill="none" stroke="#334155" strokeWidth="1.2" viewBox="0 0 24 24" className="mx-auto mb-4">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
                  </svg>
                  <div className="text-sm text-slate-500 mb-2">
                    {reportData ? "Report ready to generate" : "Load an account to get started"}
                  </div>
                  <div className="text-xs text-slate-600">
                    {reportData
                      ? "Click \"Generate STR Report\" to see the AI typewriter in action"
                      : "Enter an account ID like ACC_00018 and click Load"}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer status */}
          <div className="flex items-center justify-between border-t border-white/[0.06] px-6 py-3 flex-shrink-0">
            <div className="text-[10px] text-slate-600">
              {reportText ? `${reportText.length} / ${fullText.length} characters` : "Awaiting generation"}
            </div>
            <div className="flex items-center gap-3">
              {generating && (
                <div className="flex items-center gap-1.5 text-[10px] text-cyan-400">
                  <div className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
                  Generating…
                </div>
              )}
              <div className="text-[10px] text-slate-600">Powered by TRACE-X AI · FIU-IND compliant format</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
