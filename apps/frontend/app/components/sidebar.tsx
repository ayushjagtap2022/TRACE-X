"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
      </svg>
    ),
    sub: "Live alerts & feed",
  },
  {
    href: "/investigation",
    label: "Investigation",
    icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="7" /><path d="m21 21-4.35-4.35" />
      </svg>
    ),
    sub: "Fund flow graph",
  },
  {
    href: "/str-report",
    label: "STR Report",
    icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
      </svg>
    ),
    sub: "Auto-generated FIU",
  },
  {
    href: "/analytics",
    label: "Analytics",
    icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
      </svg>
    ),
    sub: "Trends & breakdown",
  },
];

const BOTTOM_NAV = [
  {
    href: "/lab", label: "Demo Lab", icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18" />
      </svg>
    )
  },
  {
    href: "/explain", label: "Explain", icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    )
  },
];

export function Sidebar() {
  const path = usePathname();
  const match = (href: string) =>
    href === "/" ? path === "/" : path === href || path.startsWith(href + "/");

  return (
    <aside className="relative z-20 flex h-screen w-[220px] flex-shrink-0 flex-col border-r border-white/[0.06] bg-[#020617]/80 backdrop-blur-xl">
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-white/[0.06] px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-400/20 to-cyan-600/10 border border-cyan-400/25">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22d3ee" strokeWidth="2.5">
            <path d="M3 12h4l3-9 4 18 3-9h4" />
          </svg>
        </div>
        <div>
          <div className="text-sm font-bold tracking-widest text-white">TRACE-X</div>
          <div className="text-[10px] font-medium tracking-[0.15em] text-cyan-400/60 uppercase">Fund Flow AI</div>
        </div>
      </div>

      {/* Status indicator */}
      <div className="mx-3 mt-3 flex items-center gap-2 rounded-xl border border-emerald-400/15 bg-emerald-400/5 px-3 py-2">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
        </span>
        <span className="text-[11px] font-medium text-emerald-300">API connected · port 8000</span>
      </div>

      {/* Main nav */}
      <nav className="flex flex-col gap-1 px-3 pt-4">
        <div className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">Core</div>
        {NAV.map((item) => {
          const active = match(item.href);
          return (
            <Link key={item.href} href={item.href}
              className={`sidebar-link ${active ? "active" : ""}`}>
              <span className={active ? "text-cyan-400" : "text-slate-500"}>{item.icon}</span>
              <div>
                <div className={`text-[13px] font-medium ${active ? "text-cyan-200" : "text-slate-300"}`}>
                  {item.label}
                </div>
                <div className="text-[10px] text-slate-500">{item.sub}</div>
              </div>
            </Link>
          );
        })}
      </nav>

      <div className="mt-4 px-3">
        <div className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">Tools</div>
        {BOTTOM_NAV.map((item) => {
          const active = match(item.href);
          return (
            <Link key={item.href} href={item.href}
              className={`sidebar-link ${active ? "active" : ""}`}>
              <span className={active ? "text-cyan-400" : "text-slate-500"}>{item.icon}</span>
              <span className={`text-[13px] font-medium ${active ? "text-cyan-200" : "text-slate-300"}`}>
                {item.label}
              </span>
            </Link>
          );
        })}
      </div>

      <div className="mt-auto border-t border-white/[0.06] px-4 py-4">
        <div className="text-[10px] text-slate-600">TRACE-X · v1.0 · FIU-IND ready</div>
        <div className="mt-1 text-[10px] text-slate-700">Hackathon Demo Build</div>
      </div>
    </aside>
  );
}
