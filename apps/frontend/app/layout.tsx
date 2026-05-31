import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Sidebar } from "./components/sidebar";
import "./fonts.css";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "TRACE-X — Fund Flow Intelligence",
  description: "Intelligent fund flow tracking, graph analytics, and fraud detection for banking investigators.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="flex h-full min-h-screen bg-[#020617] text-slate-100 antialiased">
        {/* Ambient background effects */}
        <div className="pointer-events-none fixed inset-0 z-0">
          <div className="absolute top-0 left-1/4 h-[600px] w-[600px] -translate-x-1/2 rounded-full bg-cyan-500/5 blur-[120px]" />
          <div className="absolute bottom-0 right-1/4 h-[400px] w-[400px] translate-x-1/2 rounded-full bg-violet-500/5 blur-[100px]" />
          <div className="absolute top-1/2 left-1/2 h-[800px] w-[800px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose-500/3 blur-[150px]" />
        </div>
        <Sidebar />
        <main className="relative z-10 flex-1 overflow-auto">{children}</main>
      </body>
    </html>
  );
}
