import { useState, useMemo } from "react";
import { useGex, useOptionsOI } from "../hooks/useOptions";
import { useLatestPrice } from "../hooks/usePrice";
import { useDailySnapshot } from "../hooks/useSignal";

/* ── Helpers ─────────────────────────────────────────────── */

function fmt(n: number, decimals = 0) {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtK(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toFixed(0);
}

function fmtStrike(s: number) {
  return `$${(s / 1000).toFixed(0)}K`;
}

interface AggOi {
  strike: number;
  call_oi: number;
  put_oi: number;
  total: number;
  call_iv: number | null;
  put_iv: number | null;
}

function aggregateOi(
  raw: { strike: number; call_oi: number; put_oi: number; call_iv: number | null; put_iv: number | null; expiry?: string }[],
  expiry?: string,
): AggOi[] {
  const filtered = expiry ? raw.filter((r) => r.expiry === expiry) : raw;
  const map = new Map<number, AggOi>();
  for (const r of filtered) {
    const existing = map.get(r.strike);
    if (existing) {
      existing.call_oi += r.call_oi;
      existing.put_oi += r.put_oi;
      existing.total += r.call_oi + r.put_oi;
      if (r.call_iv != null) existing.call_iv = r.call_iv;
      if (r.put_iv != null) existing.put_iv = r.put_iv;
    } else {
      map.set(r.strike, {
        strike: r.strike, call_oi: r.call_oi, put_oi: r.put_oi,
        total: r.call_oi + r.put_oi, call_iv: r.call_iv, put_iv: r.put_iv,
      });
    }
  }
  return Array.from(map.values()).sort((a, b) => a.strike - b.strike);
}

function findMaxPain(oi: AggOi[]): number | null {
  if (oi.length === 0) return null;
  let minPain = Infinity, mpStrike = oi[0].strike;
  for (const target of oi) {
    let pain = 0;
    for (const row of oi) {
      if (target.strike > row.strike) pain += (target.strike - row.strike) * row.put_oi;
      if (target.strike < row.strike) pain += (row.strike - target.strike) * row.call_oi;
    }
    if (pain < minPain) { minPain = pain; mpStrike = target.strike; }
  }
  return mpStrike;
}

/* ── Shared Components ───────────────────────────────────── */

function MetricCard({ label, value, sub, color, large }: {
  label: string; value: string; sub?: string; color?: string; large?: boolean;
}) {
  return (
    <div className="card p-4">
      <div className="text-[10px] uppercase tracking-wider text-text-muted font-medium mb-1.5">{label}</div>
      <div className={`font-data font-bold ${large ? "text-xl" : "text-lg"}`} style={{ color: color ?? "#f1f5f9" }}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-text-muted font-data mt-1">{sub}</div>}
    </div>
  );
}

function ChartCard({ title, info, children, className }: {
  title: string; info?: string; children: React.ReactNode; className?: string;
}) {
  const [showInfo, setShowInfo] = useState(false);
  return (
    <div className={`card p-5 ${className ?? ""}`}>
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm font-semibold text-text-secondary">{title}</div>
        {info && (
          <button
            onClick={() => setShowInfo(!showInfo)}
            className="text-[10px] text-text-muted px-2 py-0.5 rounded border border-border-subtle hover:border-border-bright transition-colors"
          >
            {showInfo ? "×" : "?"}
          </button>
        )}
      </div>
      {showInfo && info && (
        <div className="text-xs text-text-secondary bg-bg-primary/60 rounded-lg p-3 mb-4 leading-relaxed border border-border-subtle/50">
          {info}
        </div>
      )}
      {children}
    </div>
  );
}

/* ── IV Smile Chart ──────────────────────────────────────── */

function IVSmileChart({ data, currentPrice, expiries, selectedExpiry, onExpiryChange }: {
  data: AggOi[]; currentPrice: number; expiries: string[];
  selectedExpiry: string; onExpiryChange: (e: string) => void;
}) {
  const filtered = useMemo(() => {
    const lo = currentPrice * 0.75;
    const hi = currentPrice * 1.25;
    return data.filter((d) => d.strike >= lo && d.strike <= hi && (d.call_iv != null || d.put_iv != null))
      .sort((a, b) => a.strike - b.strike);
  }, [data, currentPrice]);

  if (filtered.length < 3) return <div className="h-[200px] flex items-center justify-center text-text-muted text-xs">Not enough IV data</div>;

  const allIv = filtered.flatMap((d) => [d.call_iv, d.put_iv].filter((v): v is number => v != null && v > 0));
  if (allIv.length === 0) return null;
  const minIv = Math.min(...allIv) * 0.9;
  const maxIv = Math.max(...allIv) * 1.1;

  const W = 560, H = 200;
  const M = { top: 15, bottom: 30, left: 40, right: 10 };

  const scaleX = (strike: number) => {
    const lo = filtered[0].strike, hi = filtered[filtered.length - 1].strike;
    return M.left + ((strike - lo) / (hi - lo || 1)) * (W - M.left - M.right);
  };
  const scaleY = (iv: number) => M.top + (H - M.top - M.bottom) - ((iv - minIv) / (maxIv - minIv)) * (H - M.top - M.bottom);

  const makePath = (key: "call_iv" | "put_iv") => {
    const pts = filtered.filter((d) => d[key] != null && d[key]! > 0).map((d) => ({ x: scaleX(d.strike), y: scaleY(d[key]!) }));
    return pts.length < 2 ? "" : pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  };

  const callPath = makePath("call_iv");
  const putPath = makePath("put_iv");
  const priceX = scaleX(currentPrice);

  // Area fill for call IV
  const callPts = filtered.filter((d) => d.call_iv != null && d.call_iv! > 0).map((d) => ({ x: scaleX(d.strike), y: scaleY(d.call_iv!) }));
  const areaPath = callPts.length >= 2 ? callPath + ` L ${callPts[callPts.length - 1].x} ${H - M.bottom} L ${callPts[0].x} ${H - M.bottom} Z` : "";

  return (
    <div>
      <div className="flex gap-1.5 mb-3 overflow-x-auto">
        <button
          onClick={() => onExpiryChange("")}
          className="text-[10px] font-data px-2 py-1 rounded transition-colors whitespace-nowrap"
          style={{
            backgroundColor: selectedExpiry === "" ? "#1a2236" : "transparent",
            color: selectedExpiry === "" ? "#f1f5f9" : "#475569",
            border: selectedExpiry === "" ? "1px solid #2a3654" : "1px solid transparent",
          }}
        >
          ALL
        </button>
        {expiries.slice(0, 8).map((exp) => (
          <button
            key={exp}
            onClick={() => onExpiryChange(exp)}
            className="text-[10px] font-data px-2 py-1 rounded transition-colors whitespace-nowrap"
            style={{
              backgroundColor: selectedExpiry === exp ? "#1a2236" : "transparent",
              color: selectedExpiry === exp ? "#f1f5f9" : "#475569",
              border: selectedExpiry === exp ? "1px solid #2a3654" : "1px solid transparent",
            }}
          >
            {exp}
          </button>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <defs>
          <linearGradient id="ivGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Grid */}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const y = M.top + f * (H - M.top - M.bottom);
          const iv = maxIv - f * (maxIv - minIv);
          return (
            <g key={f}>
              <line x1={M.left} x2={W - M.right} y1={y} y2={y} stroke="#1a2236" strokeWidth={0.5} />
              <text x={M.left - 4} y={y + 3} textAnchor="end" fill="#475569" fontSize={8} fontFamily="var(--font-mono)">{iv.toFixed(0)}%</text>
            </g>
          );
        })}
        {/* Area fill */}
        {areaPath && <path d={areaPath} fill="url(#ivGrad)" />}
        {/* Lines */}
        <path d={callPath} fill="none" stroke="#10b981" strokeWidth={2} opacity={0.8} />
        <path d={putPath} fill="none" stroke="#ef4444" strokeWidth={2} opacity={0.8} />
        {/* Dots */}
        {filtered.map((d) => {
          if (d.call_iv == null || d.call_iv <= 0) return null;
          const x = scaleX(d.strike), y = scaleY(d.call_iv);
          const isATM = Math.abs(d.strike - currentPrice) < (currentPrice * 0.02);
          return <circle key={`c${d.strike}`} cx={x} cy={y} r={isATM ? 4 : 2.5} fill={isATM ? "#f1f5f9" : "#10b981"} stroke={isATM ? "#10b981" : "none"} strokeWidth={2} />;
        })}
        {/* ATM line */}
        <line x1={priceX} x2={priceX} y1={M.top} y2={H - M.bottom} stroke="#475569" strokeWidth={1} strokeDasharray="3 3" />
        <text x={priceX} y={M.top - 3} textAnchor="middle" fill="#94a3b8" fontSize={8} fontFamily="var(--font-mono)">ATM</text>
        {/* X labels */}
        <text x={M.left + 5} y={H - M.bottom + 16} fill="#475569" fontSize={8} fontFamily="var(--font-mono)">OTM Puts</text>
        <text x={W - M.right - 5} y={H - M.bottom + 16} textAnchor="end" fill="#475569" fontSize={8} fontFamily="var(--font-mono)">OTM Calls</text>
        {/* Legend */}
        <line x1={W - 140} y1={M.top + 5} x2={W - 125} y2={M.top + 5} stroke="#10b981" strokeWidth={2} />
        <text x={W - 122} y={M.top + 8} fill="#94a3b8" fontSize={9}>Call IV</text>
        <line x1={W - 80} y1={M.top + 5} x2={W - 65} y2={M.top + 5} stroke="#ef4444" strokeWidth={2} />
        <text x={W - 62} y={M.top + 8} fill="#94a3b8" fontSize={9}>Put IV</text>
      </svg>
    </div>
  );
}

/* ── OI Chart ────────────────────────────────────────────── */

function OIChart({ data, currentPrice, maxPain, gammaFlip }: {
  data: AggOi[]; currentPrice: number; maxPain: number | null; gammaFlip: number | null;
}) {
  const filtered = useMemo(() => {
    const lo = currentPrice * 0.80, hi = currentPrice * 1.20;
    return data.filter((d) => d.strike >= lo && d.strike <= hi);
  }, [data, currentPrice]);

  if (filtered.length === 0) return null;

  const max = Math.max(...filtered.map((d) => Math.max(d.call_oi, d.put_oi)));
  const W = 560, H = 200;
  const M = { top: 10, bottom: 28, left: 35, right: 10 };
  const chartH = H - M.top - M.bottom;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {/* Grid */}
      {[0, 0.5, 1].map((f) => {
        const y = M.top + chartH - f * chartH;
        return <line key={f} x1={M.left} x2={W - M.right} y1={y} y2={y} stroke="#1a2236" strokeWidth={0.5} />;
      })}
      {/* Bars */}
      {filtered.map((row, i) => {
        const x = M.left + (i / (filtered.length - 1 || 1)) * (W - M.left - M.right);
        const hC = (row.call_oi / max) * chartH;
        const hP = (row.put_oi / max) * chartH;
        const bw = ((W - M.left - M.right) / filtered.length) * 0.35;
        const isMP = maxPain === row.strike;
        const isFlip = gammaFlip === row.strike;
        return (
          <g key={row.strike}>
            <rect x={x - bw - 0.5} y={M.top + chartH - hC} width={bw} height={hC} fill="#10b981" rx={1.5} opacity={0.8} />
            <rect x={x + 0.5} y={M.top + chartH - hP} width={bw} height={hP} fill="#ef4444" rx={1.5} opacity={0.8} />
            {isMP && <line x1={x} y1={M.top} x2={x} y2={M.top + chartH} stroke="#f59e0b" strokeWidth={1} strokeDasharray="2 2" />}
            {isFlip && <line x1={x} y1={M.top} x2={x} y2={M.top + chartH} stroke="#a78bfa" strokeWidth={1} strokeDasharray="3 2" />}
            {i % Math.max(1, Math.ceil(filtered.length / 10)) === 0 && (
              <text x={x} y={H - M.bottom + 14} textAnchor="middle" fill="#475569" fontSize={7.5} fontFamily="var(--font-mono)">{fmtStrike(row.strike)}</text>
            )}
          </g>
        );
      })}
      {/* Spot line */}
      {(() => {
        const spotIdx = filtered.reduce((best, s, i) => Math.abs(s.strike - currentPrice) < Math.abs(filtered[best].strike - currentPrice) ? i : best, 0);
        const x = M.left + (spotIdx / (filtered.length - 1 || 1)) * (W - M.left - M.right);
        return <line x1={x} y1={M.top} x2={x} y2={M.top + chartH} stroke="#475569" strokeWidth={1} strokeDasharray="3 3" />;
      })()}
      {/* Legend */}
      <rect x={W - 150} y={4} width={8} height={8} fill="#10b981" rx={1.5} />
      <text x={W - 138} y={11} fill="#94a3b8" fontSize={9}>Calls</text>
      <rect x={W - 95} y={4} width={8} height={8} fill="#ef4444" rx={1.5} />
      <text x={W - 83} y={11} fill="#94a3b8" fontSize={9}>Puts</text>
      {maxPain && <text x={M.left + 5} y={M.top + 10} fill="#f59e0b" fontSize={8}>Max Pain ${fmtK(maxPain)}</text>}
    </svg>
  );
}

/* ── GEX Chart ───────────────────────────────────────────── */

function GEXChart({ data, currentPrice, gammaFlip }: {
  data: { strike: number; net_gex: number }[]; currentPrice: number; gammaFlip: number | null;
}) {
  const sorted = useMemo(() => {
    const lo = currentPrice * 0.85, hi = currentPrice * 1.15;
    return data.filter((d) => d.strike >= lo && d.strike <= hi && Math.abs(d.net_gex) > 1)
      .sort((a, b) => a.strike - b.strike);
  }, [data, currentPrice]);

  if (sorted.length === 0) return <div className="h-[200px] flex items-center justify-center text-text-muted text-xs">No GEX data</div>;

  const maxAbs = Math.max(...sorted.map((d) => Math.abs(d.net_gex)));
  const W = 560, H = 200;
  const M = { top: 15, bottom: 28, left: 10, right: 10 };
  const chartH = H - M.top - M.bottom;
  const zeroY = M.top + chartH / 2;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <line x1={M.left} x2={W - M.right} y1={zeroY} y2={zeroY} stroke="#1e2633" strokeWidth={1} />
      <text x={M.left + 2} y={zeroY - 3} fill="#475569" fontSize={8} fontFamily="var(--font-mono)">0</text>
      {sorted.map((d, i) => {
        const x = M.left + (i / (sorted.length - 1 || 1)) * (W - M.left - M.right);
        const h = maxAbs > 0 ? (Math.abs(d.net_gex) / maxAbs) * (chartH / 2) : 0;
        const isPos = d.net_gex >= 0;
        const bw = Math.min(20, (W - M.left - M.right) / sorted.length * 0.7);
        return (
          <g key={d.strike}>
            <rect x={x - bw / 2} y={isPos ? zeroY - h : zeroY} width={bw} height={h} fill={isPos ? "#10b981" : "#ef4444"} rx={2} opacity={0.75} />
            {i % Math.max(1, Math.ceil(sorted.length / 10)) === 0 && (
              <text x={x} y={H - M.bottom + 14} textAnchor="middle" fill="#475569" fontSize={7.5} fontFamily="var(--font-mono)">{fmtStrike(d.strike)}</text>
            )}
          </g>
        );
      })}
      {/* Gamma flip */}
      {gammaFlip && (() => {
        const idx = sorted.findIndex((d) => d.strike >= gammaFlip);
        if (idx < 0) return null;
        const x = M.left + (idx / (sorted.length - 1 || 1)) * (W - M.left - M.right);
        return (
          <g>
            <line x1={x} y1={M.top} x2={x} y2={M.top + chartH} stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="4 3" />
            <text x={x + 4} y={M.top + 10} fill="#f59e0b" fontSize={9} fontWeight={600}>GEX FLIP</text>
          </g>
        );
      })()}
      <text x={M.left + 5} y={M.top + 10} fill="#10b981" fontSize={8} opacity={0.7}>+ Dealers dampen vol</text>
      <text x={M.left + 5} y={M.top + chartH - 4} fill="#ef4444" fontSize={8} opacity={0.7}>- Dealers amplify vol</text>
    </svg>
  );
}

/* ── P/C Ratio Gauge ─────────────────────────────────────── */

function PCGauge({ ratio }: { ratio: number }) {
  const clamped = Math.min(Math.max(ratio, 0.2), 1.8);
  const pct = (clamped - 0.2) / 1.6;
  const deg = -90 + pct * 180;
  const rad = (deg * Math.PI) / 180;
  const nx = 100 + 60 * Math.cos(rad);
  const ny = 105 + 60 * Math.sin(rad);

  return (
    <div className="text-center">
      <svg viewBox="0 0 200 125" className="w-full" style={{ maxWidth: 200, margin: "0 auto" }}>
        <path d="M 25 105 A 75 75 0 0 1 175 105" fill="none" stroke="#1a2236" strokeWidth={10} strokeLinecap="round" />
        <path d="M 25 105 A 75 75 0 0 1 100 30" fill="none" stroke="#10b981" strokeWidth={10} strokeLinecap="round" opacity={0.4} />
        <path d="M 100 30 A 75 75 0 0 1 175 105" fill="none" stroke="#ef4444" strokeWidth={10} strokeLinecap="round" opacity={0.4} />
        <line x1={100} y1={105} x2={nx} y2={ny} stroke="#f1f5f9" strokeWidth={2.5} strokeLinecap="round" />
        <circle cx={100} cy={105} r={4} fill="#f1f5f9" />
        <text x={100} y={92} textAnchor="middle" fill="#f1f5f9" fontSize={20} fontWeight={700} fontFamily="var(--font-mono)">{ratio.toFixed(2)}</text>
        <text x={28} y={118} fill="#10b981" fontSize={8}>Bullish</text>
        <text x={172} y={118} textAnchor="end" fill="#ef4444" fontSize={8}>Bearish</text>
      </svg>
      <div className="text-[10px] text-text-muted -mt-2">
        {ratio < 0.7 ? "Calls dominate (bullish)" : ratio > 1.0 ? "Puts dominate (bearish)" : "Neutral"}
      </div>
    </div>
  );
}

/* ── Skew Indicator ──────────────────────────────────────── */

function SkewIndicator({ data, currentPrice }: { data: AggOi[]; currentPrice: number }) {
  const putIv25 = useMemo(() => {
    const target = currentPrice * 0.90;
    const near = data.filter((d) => d.put_iv != null && d.put_iv > 0 && d.strike < currentPrice)
      .sort((a, b) => Math.abs(a.strike - target) - Math.abs(b.strike - target));
    return near.length > 0 ? near[0].put_iv! : null;
  }, [data, currentPrice]);

  const callIv25 = useMemo(() => {
    const target = currentPrice * 1.10;
    const near = data.filter((d) => d.call_iv != null && d.call_iv > 0 && d.strike > currentPrice)
      .sort((a, b) => Math.abs(a.strike - target) - Math.abs(b.strike - target));
    return near.length > 0 ? near[0].call_iv! : null;
  }, [data, currentPrice]);

  if (putIv25 == null || callIv25 == null) return <div className="text-text-muted text-xs text-center py-8">No skew data</div>;

  const skew = Math.round((putIv25 - callIv25) * 10) / 10;

  return (
    <div>
      <div className="flex justify-between mb-3 text-xs">
        <div>
          <div className="text-[9px] text-text-muted uppercase mb-1">25D Put IV</div>
          <div className="font-data font-bold text-bear">{putIv25.toFixed(1)}%</div>
        </div>
        <div className="text-center">
          <div className="text-[9px] text-text-muted uppercase mb-1">Skew (P - C)</div>
          <div className="font-data font-bold text-lg" style={{ color: skew > 0 ? "#f59e0b" : "#10b981" }}>
            {skew > 0 ? "+" : ""}{skew}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[9px] text-text-muted uppercase mb-1">25D Call IV</div>
          <div className="font-data font-bold text-bull">{callIv25.toFixed(1)}%</div>
        </div>
      </div>
      <div className="h-2 bg-bg-primary rounded-full relative overflow-hidden">
        <div
          className="absolute h-full rounded-full"
          style={{
            left: skew > 0 ? "50%" : undefined,
            right: skew <= 0 ? "50%" : undefined,
            width: `${Math.min(Math.abs(skew) * 3, 50)}%`,
            backgroundColor: skew > 0 ? "#f59e0b" : "#10b981",
            opacity: 0.6,
          }}
        />
        <div className="absolute left-1/2 top-[-2px] w-0.5 h-3 bg-text-muted" />
      </div>
      <div className="flex justify-between text-[9px] text-text-muted mt-1.5">
        <span>Call skew (bullish)</span>
        <span>Put skew (fear)</span>
      </div>
    </div>
  );
}

/* ── Term Structure ──────────────────────────────────────── */

function parseDeribitExpiry(e: string): Date | null {
  const months: Record<string, string> = {
    JAN: "01", FEB: "02", MAR: "03", APR: "04", MAY: "05", JUN: "06",
    JUL: "07", AUG: "08", SEP: "09", OCT: "10", NOV: "11", DEC: "12",
  };
  // e.g. "27MAR26" → day="27", mon="MAR", yr="26"
  const match = e.match(/^(\d{1,2})([A-Z]{3})(\d{2})$/);
  if (!match) return null;
  const [, day, mon, yr] = match;
  const mm = months[mon];
  if (!mm) return null;
  return new Date(`20${yr}-${mm}-${day.padStart(2, "0")}T08:00:00Z`);
}

function fmtDTE(days: number): string {
  if (days <= 0) return "exp";
  if (days === 1) return "1d";
  if (days < 7) return `${days}d`;
  if (days < 30) return `${Math.round(days / 7)}w`;
  return `${Math.round(days / 30)}m`;
}

function TermStructure({ oiData, currentPrice }: {
  oiData: { strike: number; call_iv: number | null; put_iv: number | null; expiry: string }[];
  currentPrice: number;
}) {
  const termData = useMemo(() => {
    const now = new Date();
    const expiries = [...new Set(oiData.map((r) => r.expiry))];
    const results: { expiry: string; atmIv: number; dte: number }[] = [];

    for (const exp of expiries) {
      // Parse and filter expired
      const expDate = parseDeribitExpiry(exp);
      if (!expDate) continue;
      const dte = Math.round((expDate.getTime() - now.getTime()) / 86400000);
      if (dte < 0) continue; // Skip expired

      // Find ATM IV: average of nearest 3 strikes to spot
      const rows = oiData
        .filter((r) => r.expiry === exp && r.call_iv != null && r.call_iv! > 10)
        .sort((a, b) => Math.abs(a.strike - currentPrice) - Math.abs(b.strike - currentPrice));

      const atmRows = rows.slice(0, 3);
      if (atmRows.length === 0) continue;

      const avgIv = atmRows.reduce((s, r) => s + r.call_iv!, 0) / atmRows.length;
      results.push({ expiry: exp, atmIv: avgIv, dte });
    }

    return results.sort((a, b) => a.dte - b.dte);
  }, [oiData, currentPrice]);

  if (termData.length < 3) return <div className="h-[180px] flex items-center justify-center text-text-muted text-xs">Not enough expiry data</div>;

  const ivs = termData.map((d) => d.atmIv);
  const minIv = Math.min(...ivs) - 3;
  const maxIv = Math.max(...ivs) + 3;

  const W = 560, H = 200;
  const M = { top: 15, bottom: 45, left: 35, right: 15 };

  const scaleX = (i: number) => M.left + (i / (termData.length - 1)) * (W - M.left - M.right);
  const scaleY = (iv: number) => M.top + (H - M.top - M.bottom) - ((iv - minIv) / (maxIv - minIv)) * (H - M.top - M.bottom);

  const path = termData.map((d, i) => `${i === 0 ? "M" : "L"} ${scaleX(i)} ${scaleY(d.atmIv)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {/* Grid */}
      {[0, 0.25, 0.5, 0.75, 1].map((f) => {
        const y = M.top + f * (H - M.top - M.bottom);
        const iv = maxIv - f * (maxIv - minIv);
        return (
          <g key={f}>
            <line x1={M.left} x2={W - M.right} y1={y} y2={y} stroke="#1a2236" strokeWidth={0.5} />
            <text x={M.left - 4} y={y + 3} textAnchor="end" fill="#475569" fontSize={8} fontFamily="var(--font-mono)">{iv.toFixed(0)}%</text>
          </g>
        );
      })}
      {/* Line + area */}
      <path d={path + ` L ${scaleX(termData.length - 1)} ${H - M.bottom} L ${scaleX(0)} ${H - M.bottom} Z`} fill="rgba(167,139,250,0.08)" />
      <path d={path} fill="none" stroke="#a78bfa" strokeWidth={2} />
      {/* Dots + labels */}
      {termData.map((d, i) => (
        <g key={i}>
          <circle cx={scaleX(i)} cy={scaleY(d.atmIv)} r={3.5} fill="#a78bfa" />
          {/* IV value on hover area */}
          <text x={scaleX(i)} y={scaleY(d.atmIv) - 8} textAnchor="middle" fill="#a78bfa" fontSize={8} fontFamily="var(--font-mono)" opacity={0.8}>
            {d.atmIv.toFixed(1)}%
          </text>
          {/* Bottom: DTE + expiry */}
          <text x={scaleX(i)} y={H - M.bottom + 12} textAnchor="middle" fill="#94a3b8" fontSize={8} fontFamily="var(--font-mono)">
            {fmtDTE(d.dte)}
          </text>
          <text x={scaleX(i)} y={H - M.bottom + 22} textAnchor="middle" fill="#475569" fontSize={6.5} fontFamily="var(--font-mono)">
            {d.expiry}
          </text>
        </g>
      ))}
    </svg>
  );
}

/* ── Main Page ───────────────────────────────────────────── */

export default function OptionsPage({ symbol }: { symbol?: string }) {
  const { data: gexResp, isLoading: gexLoading } = useGex(symbol);
  const { data: oiData, isLoading: oiLoading } = useOptionsOI(symbol);
  const { data: latestPrice } = useLatestPrice(symbol);
  const { data: dailySnap } = useDailySnapshot(symbol);
  const [ivExpiry, setIvExpiry] = useState("");

  const currentPrice = latestPrice?.close ?? 0;
  const gexData = gexResp?.strikes ?? [];
  const gammaFlip = gexResp?.gamma_flip ?? null;

  const expiries = useMemo(() => {
    if (!oiData) return [];
    return [...new Set(oiData.map((r) => r.expiry))].sort();
  }, [oiData]);

  const aggregatedOi = useMemo(() => (oiData ? aggregateOi(oiData) : []), [oiData]);
  const ivFilteredOi = useMemo(() => (oiData ? aggregateOi(oiData, ivExpiry || undefined) : []), [oiData, ivExpiry]);
  const maxPain = useMemo(() => findMaxPain(aggregatedOi), [aggregatedOi]);

  const totalCallOi = aggregatedOi.reduce((s, r) => s + r.call_oi, 0);
  const totalPutOi = aggregatedOi.reduce((s, r) => s + r.put_oi, 0);
  const pcRatio = totalCallOi > 0 ? totalPutOi / totalCallOi : 0;

  const gammaDistance = gammaFlip && currentPrice ? ((currentPrice - gammaFlip) / currentPrice) * 100 : null;
  const isPositiveGamma = gammaDistance != null && gammaDistance > 0;

  const dvol = dailySnap?.dvol ?? null;

  if (gexLoading || oiLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted animate-pulse font-data text-sm">Loading options data...</div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* ── Metrics Row ──────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
        <MetricCard
          label="DVol (30D IV)"
          value={dvol ? `${dvol.toFixed(1)}%` : "---"}
          sub="Deribit implied vol"
          color="#a78bfa"
        />
        <MetricCard
          label="Gamma Flip"
          value={gammaFlip ? `$${fmt(gammaFlip)}` : "---"}
          sub={gammaDistance != null ? `${gammaDistance > 0 ? "+" : ""}${gammaDistance.toFixed(1)}% from spot` : undefined}
          color="#a78bfa"
        />
        <MetricCard
          label="Max Pain"
          value={maxPain ? `$${fmt(maxPain)}` : "---"}
          sub={maxPain && currentPrice ? `${((currentPrice - maxPain) / currentPrice * 100).toFixed(1)}% from spot` : undefined}
          color="#f59e0b"
        />
        <MetricCard
          label="P/C Ratio"
          value={pcRatio.toFixed(2)}
          sub={pcRatio > 1 ? "Put heavy (bearish)" : "Call heavy (bullish)"}
          color={pcRatio > 1 ? "#ef4444" : "#10b981"}
        />
        <MetricCard
          label="Gamma Territory"
          value={gammaDistance != null ? (isPositiveGamma ? "+γ" : "−γ") : "---"}
          sub={isPositiveGamma ? "Dealers long gamma" : "Dealers short gamma"}
          color={isPositiveGamma ? "#10b981" : "#ef4444"}
          large
        />
      </div>

      {/* ── Row 1: IV Smile + OI ─────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <ChartCard
          title="IV Smile by Strike"
          info="IV low at ATM, high at wings. Steeper put side = put skew (demand for downside protection). Use expiry buttons to compare term structure."
        >
          <IVSmileChart
            data={ivFilteredOi}
            currentPrice={currentPrice}
            expiries={expiries}
            selectedExpiry={ivExpiry}
            onExpiryChange={setIvExpiry}
          />
        </ChartCard>

        <ChartCard
          title="Open Interest by Strike"
          info="OI shows where money is positioned. High-OI strikes often act as support/resistance. Yellow line = Max Pain (strike where option buyers lose the most)."
        >
          {aggregatedOi.length > 0 && currentPrice > 0 ? (
            <OIChart data={aggregatedOi} currentPrice={currentPrice} maxPain={maxPain} gammaFlip={gammaFlip} />
          ) : (
            <div className="h-[200px] flex items-center justify-center text-text-muted text-xs">No OI data</div>
          )}
        </ChartCard>
      </div>

      {/* ── Row 2: GEX + Term Structure ──────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <ChartCard
          title="Gamma Exposure (GEX)"
          info="Positive GEX = dealers suppress volatility (buy dips, sell rips). Negative GEX = dealers amplify moves. GEX Flip is the critical boundary."
        >
          <GEXChart data={gexData} currentPrice={currentPrice} gammaFlip={gammaFlip} />
        </ChartCard>

        <ChartCard
          title="IV Term Structure"
          info="Contango (upward slope) = normal. Backwardation (short-term IV higher than long-term) = market pricing near-term event risk."
        >
          {oiData ? (
            <TermStructure oiData={oiData} currentPrice={currentPrice} />
          ) : (
            <div className="h-[180px] flex items-center justify-center text-text-muted text-xs">No data</div>
          )}
        </ChartCard>
      </div>

      {/* ── Row 3: P/C Gauge + Skew ──────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <ChartCard
          title="Put/Call Ratio"
          info="Below 0.7 = bullish (calls dominate). Above 1.0 = bearish (puts dominate). Extreme readings are often contrarian signals."
        >
          <PCGauge ratio={pcRatio} />
        </ChartCard>

        <ChartCard
          title="25D Risk Reversal Skew"
          info="Positive skew = OTM put IV > OTM call IV = market pricing downside risk. Negative skew = calls more expensive = upside expectation."
        >
          <SkewIndicator data={aggregatedOi} currentPrice={currentPrice} />
        </ChartCard>
      </div>

      {/* ── Market Summary ───────────────────────────────── */}
      <div className="card p-5">
        <div className="text-sm font-semibold text-text-secondary mb-3">Options Market Read</div>
        <div className="text-xs text-text-secondary leading-relaxed space-y-2">
          {dvol != null && (
            <div>
              <span className="text-purple">*</span>{" "}
              <span className="text-text-primary font-medium">DVol {dvol.toFixed(1)}%</span> —{" "}
              {dvol > 70 ? "Extreme implied vol — options expensive, favor selling." :
               dvol > 55 ? "Elevated vol — market pricing uncertainty." :
               dvol > 40 ? "Moderate vol — normal conditions." :
               "Low vol — options cheap, favor buying."}
            </div>
          )}
          <div>
            <span className="text-bull">*</span>{" "}
            <span className="text-text-primary font-medium">P/C Ratio {pcRatio.toFixed(2)}</span> —{" "}
            {pcRatio < 0.7 ? "Calls dominate, sentiment bullish." :
             pcRatio > 1.0 ? "Puts dominate, sentiment bearish — potential contrarian buy." :
             "Balanced positioning."}
          </div>
          {gammaFlip && gammaDistance != null && (
            <div>
              <span style={{ color: isPositiveGamma ? "#10b981" : "#ef4444" }}>*</span>{" "}
              <span className="text-text-primary font-medium">
                {isPositiveGamma ? "Positive gamma" : "Negative gamma"} territory
              </span> —{" "}
              {isPositiveGamma
                ? "Dealers dampen moves. Expect range-bound price action near gamma flip."
                : "Dealers amplify moves. Breakouts will accelerate. Watch GEX flip at $" + fmtK(gammaFlip) + "."}
            </div>
          )}
          {maxPain && currentPrice > 0 && (
            <div>
              <span className="text-gold">*</span>{" "}
              <span className="text-text-primary font-medium">Max Pain ${fmtK(maxPain)}</span> —{" "}
              {Math.abs(((currentPrice - maxPain) / currentPrice) * 100) < 2
                ? "Price near max pain. Expect pinning behavior into expiry."
                : currentPrice > maxPain
                  ? "Price above max pain — gravitational pull downward into expiry."
                  : "Price below max pain — gravitational pull upward into expiry."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
