"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "overview" },
  { href: "/dashboard", label: "dashboard" },
  { href: "/case", label: "case view" },
  { href: "/graph", label: "graph trace" },
  { href: "/report", label: "report" },
  { href: "/lab", label: "demo lab" },
  { href: "/explain", label: "explain" },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-slate-950/80 backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-[1600px] items-center justify-between gap-4 px-4 py-4 md:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-3 text-white">
          <span className="rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-3 py-2 text-sm font-semibold tracking-[0.25em] text-cyan-200">
            TRACE-X
          </span>
          <span className="hidden text-sm text-slate-300 md:inline">
            fund flow intelligence
          </span>
        </Link>
        <nav className="flex flex-wrap items-center justify-end gap-2 text-xs uppercase tracking-[0.2em] text-slate-300">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-full border px-3 py-2 transition ${
                  active
                    ? "border-cyan-300/40 bg-cyan-400/15 text-cyan-100"
                    : "border-white/10 bg-white/5 hover:border-cyan-400/30 hover:bg-white/10"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
