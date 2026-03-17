import { useState, useEffect } from "react";
import MetricCard from "../components/MetricCard";
import { usePerformance, useHealth, useSignalOutcomes } from "../hooks/usePerformance";
import type { SignalOutcome } from "../api/client";

/* ── Helpers ────────────────────────────────────────── */

function AccuracyBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const color =
    pct >= 60 ? "#10b981" : pct >= 45 ? "#f59e0b" : "#ef4444";

  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-text-muted text-[10px] uppercase tracking-wider font-medium">
          {label}
        </span>
        <span className="text-xs font-bold font-data" style={{ color }}>
          {pct.toFixed(1)}%
        </span>
      </div>
      <div className="relative h-2 bg-bg-primary rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${pct}%`,
            backgroundColor: color,
            opacity: 0.8,
          }}
        />
      </div>
    </div>
  );
}

function formatUptime(seconds: number) {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function fmtDate(ts: string) {
  const d = new Date(ts);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function fmtTime(ts: string) {
  const d = new Date(ts);
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function fmtPrice(p: number | null) {
  if (p == null) return "—";
  return p.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmtPct(p: number | null) {
  if (p == null) return "—";
  const sign = p >= 0 ? "+" : "";
  return `${sign}${p.toFixed(2)}%`;
}

function biasIcon(bias: string) {
  if (bias === "LONG") return "▲";
  if (bias === "SHORT") return "▼";
  return "◆";
}

function biasColor(bias: string) {
  if (bias === "LONG") return "#10b981";
  if (bias === "SHORT") return "#ef4444";
  return "#6366f1";
}

function outcomeTag(correct: number | null) {
  if (correct === 1) return { label: "WIN", color: "#10b981", bg: "rgba(16,185,129,0.12)" };
  if (correct === 0) return { label: "LOSS", color: "#ef4444", bg: "rgba(239,68,68,0.12)" };
  return { label: "PENDING", color: "#94a3b8", bg: "rgba(148,163,184,0.08)" };
}

/* ── Signal Detail Modal ────────────────────────────── */

function SignalDetailModal({
  signal: rawSignal,
  onClose,
}: {
  signal: SignalOutcome;
  onClose: () => void;
}) {
  const [signal, setSignal] = useState(rawSignal);
  const [planLoading, setPlanLoading] = useState(false);

  // Auto-fetch trade plan if signal is directional but has no SL/TP
  useEffect(() => {
    if (signal.bias !== "NEUTRAL" && !signal.stop_loss && !planLoading) {
      setPlanLoading(true);
      fetch(`/api/signal/${encodeURIComponent(signal.timestamp)}/plan`)
        .then((r) => r.json())
        .then((plan) => {
          if (plan && !plan.error) {
            setSignal((prev) => ({
              ...prev,
              stop_loss: plan.stop_loss,
              tp1: plan.tp1,
              tp2: plan.tp2,
              tp3: plan.tp3,
            }));
          }
        })
        .catch(() => {})
        .finally(() => setPlanLoading(false));
    }
  }, [signal.bias, signal.stop_loss, signal.timestamp, planLoading]);

  const tag = outcomeTag(signal.correct);
  const entry = signal.btc_price_at_signal;

  // Price trajectory data points
  const trajectory = [
    { label: "Entry", price: entry, hours: 0 },
    { label: "4h", price: signal.btc_price_4h_later, hours: 4 },
    { label: "12h", price: signal.btc_price_12h_later, hours: 12 },
    { label: "24h", price: signal.btc_price_24h_later, hours: 24 },
    { label: "48h", price: signal.btc_price_48h_later, hours: 48 },
  ].filter((p) => p.price != null) as { label: string; price: number; hours: number }[];

  // Collect all prices for chart range (trajectory + SL/TP levels)
  const sl = signal.stop_loss;
  const tp1 = signal.tp1;
  const tp2 = signal.tp2;

  // SVG chart dimensions
  const W = 420;
  const H = 160;
  const PAD = { top: 20, right: 15, bottom: 28, left: 55 };

  let chartContent = null;
  if (trajectory.length >= 2) {
    const allPrices = [...trajectory.map((p) => p.price)];
    if (sl) allPrices.push(sl);
    if (tp1) allPrices.push(tp1);
    if (tp2) allPrices.push(tp2);

    const minP = Math.min(...allPrices);
    const maxP = Math.max(...allPrices);
    const range = maxP - minP || 1;

    const xScale = (i: number) =>
      PAD.left + (i / (trajectory.length - 1)) * (W - PAD.left - PAD.right);
    const yScale = (p: number) =>
      PAD.top + (1 - (p - minP) / range) * (H - PAD.top - PAD.bottom);

    const points = trajectory.map((t, i) => ({ x: xScale(i), y: yScale(t.price) }));
    const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");

    const finalPrice = trajectory[trajectory.length - 1].price;
    const lineColor = finalPrice >= entry ? "#10b981" : "#ef4444";
    const areaPath = `${linePath} L ${points[points.length - 1].x} ${H - PAD.bottom} L ${points[0].x} ${H - PAD.bottom} Z`;

    // Level line helper
    const levelLine = (price: number, color: string, label: string, dashed = true) => {
      const y = yScale(price);
      if (y < PAD.top - 5 || y > H - PAD.bottom + 5) return null;
      return (
        <g key={label}>
          <line x1={PAD.left} y1={y} x2={W - PAD.right} y2={y}
                stroke={color} strokeWidth={1} strokeDasharray={dashed ? "3 3" : undefined} opacity={0.6} />
          <rect x={W - PAD.right - 48} y={y - 7} width={44} height={14} rx={2} fill={color} opacity={0.12} />
          <text x={W - PAD.right - 26} y={y + 3} textAnchor="middle" fill={color}
                fontSize={7} fontFamily="var(--font-mono)" fontWeight={600}>
            {label}
          </text>
        </g>
      );
    };

    chartContent = (
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxWidth: 440 }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = PAD.top + t * (H - PAD.top - PAD.bottom);
          const price = maxP - t * range;
          return (
            <g key={t}>
              <line x1={PAD.left} y1={y} x2={W - PAD.right} y2={y} stroke="#1a2236" strokeWidth={1} />
              <text x={PAD.left - 6} y={y + 3} textAnchor="end" fill="#475569" fontSize={8} fontFamily="var(--font-mono)">
                {fmtPrice(price)}
              </text>
            </g>
          );
        })}

        {/* SL/TP level lines */}
        {sl && levelLine(sl, "#ef4444", `SL $${fmtPrice(sl)}`)}
        {tp1 && levelLine(tp1, "#10b981", `TP1 $${fmtPrice(tp1)}`)}
        {tp2 && levelLine(tp2, "#06b6d4", `TP2 $${fmtPrice(tp2)}`)}

        {/* Entry price line */}
        {levelLine(entry, "#f59e0b", `Entry $${fmtPrice(entry)}`, true)}

        {/* Area fill */}
        <path d={areaPath} fill={lineColor} opacity={0.06} />

        {/* Line */}
        <path d={linePath} fill="none" stroke={lineColor} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

        {/* Data points */}
        {points.map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={3.5} fill="#0c1018" stroke={lineColor} strokeWidth={1.5} />
            <text x={p.x} y={H - PAD.bottom + 14} textAnchor="middle" fill="#94a3b8" fontSize={8} fontFamily="var(--font-mono)">
              {trajectory[i].label}
            </text>
          </g>
        ))}
      </svg>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)" }}
      onClick={onClose}
    >
      <div
        className="card p-5 w-full max-w-lg animate-in"
        style={{ animation: "fadeScale 0.2s ease-out" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <span className="text-lg" style={{ color: biasColor(signal.bias) }}>
              {biasIcon(signal.bias)}
            </span>
            <div>
              <div className="text-sm font-semibold">
                {signal.bias} {signal.strength !== "NEUTRAL" && signal.strength}
              </div>
              <div className="text-text-muted text-[10px] font-data">
                {fmtDate(signal.timestamp)} {fmtTime(signal.timestamp)}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="text-[10px] font-bold font-data px-2 py-0.5 rounded"
              style={{ color: tag.color, backgroundColor: tag.bg }}
            >
              {tag.label}
            </span>
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary text-lg leading-none p-1"
            >
              ×
            </button>
          </div>
        </div>

        {/* Price trajectory chart */}
        {chartContent && (
          <div className="mb-4 rounded-lg overflow-hidden" style={{ backgroundColor: "rgba(6,10,16,0.6)" }}>
            <div className="px-3 pt-2">
              <span className="text-[10px] text-text-muted uppercase tracking-wider font-medium">
                Price Trajectory
              </span>
            </div>
            <div className="p-2">{chartContent}</div>
          </div>
        )}

        {/* Trade Levels */}
        {(signal.stop_loss || signal.bias !== "NEUTRAL") && (
          <div className="mb-4 rounded-lg p-3" style={{ backgroundColor: "rgba(6,10,16,0.5)" }}>
            <div className="text-[9px] text-text-muted uppercase tracking-wider mb-2 font-medium">
              Trade Levels
              {signal.exit_reason && (
                <span className="ml-2 text-[9px] font-data px-1.5 py-0.5 rounded"
                      style={{ color: (signal.pnl_pct ?? 0) >= 0 ? "#10b981" : "#ef4444", backgroundColor: (signal.pnl_pct ?? 0) >= 0 ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)" }}>
                  {signal.exit_reason?.replace(/_/g, " ").toUpperCase()}
                </span>
              )}
            </div>
            <div className="grid grid-cols-5 gap-1.5 text-center">
              <div>
                <div className="text-[8px] text-bear uppercase mb-0.5">SL</div>
                <div className="text-[11px] font-data font-bold text-bear">
                  {signal.stop_loss ? `$${fmtPrice(signal.stop_loss)}` : "—"}
                </div>
              </div>
              <div>
                <div className="text-[8px] text-gold uppercase mb-0.5">Entry</div>
                <div className="text-[11px] font-data font-bold text-gold">
                  ${fmtPrice(entry)}
                </div>
              </div>
              <div>
                <div className="text-[8px] text-bull uppercase mb-0.5">TP1{signal.tp1_hit === 1 ? " ✓" : ""}</div>
                <div className="text-[11px] font-data font-bold text-bull">
                  {signal.tp1 ? `$${fmtPrice(signal.tp1)}` : "—"}
                </div>
              </div>
              <div>
                <div className="text-[8px] text-cyan uppercase mb-0.5">TP2</div>
                <div className="text-[11px] font-data font-bold text-cyan">
                  {signal.tp2 ? `$${fmtPrice(signal.tp2)}` : "—"}
                </div>
              </div>
              <div>
                <div className="text-[8px] text-purple uppercase mb-0.5">TP3</div>
                <div className="text-[11px] font-data font-bold text-purple">
                  {signal.tp3 ? `$${fmtPrice(signal.tp3)}` : "trail"}
                </div>
              </div>
            </div>
            {/* R-multiple and PnL if trade was closed */}
            {signal.exit_reason && signal.pnl_pct != null && (
              <div className="flex items-center gap-4 mt-2 pt-2 border-t border-border-subtle/30">
                <div>
                  <span className="text-[8px] text-text-muted uppercase">PnL</span>
                  <span className="ml-1.5 text-xs font-data font-bold" style={{ color: signal.pnl_pct >= 0 ? "#10b981" : "#ef4444" }}>
                    {signal.pnl_pct >= 0 ? "+" : ""}{signal.pnl_pct.toFixed(2)}%
                  </span>
                </div>
                {signal.r_multiple != null && (
                  <div>
                    <span className="text-[8px] text-text-muted uppercase">R-Multiple</span>
                    <span className="ml-1.5 text-xs font-data font-bold" style={{ color: signal.r_multiple >= 0 ? "#10b981" : "#ef4444" }}>
                      {signal.r_multiple >= 0 ? "+" : ""}{signal.r_multiple.toFixed(1)}R
                    </span>
                  </div>
                )}
                {signal.trade_exit != null && (
                  <div>
                    <span className="text-[8px] text-text-muted uppercase">Exit</span>
                    <span className="ml-1.5 text-xs font-data font-bold text-text-secondary">
                      ${fmtPrice(signal.trade_exit)}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Key metrics */}
        <div className="grid grid-cols-2 gap-2 mb-4">
          <div className="rounded-lg p-2.5" style={{ backgroundColor: "rgba(6,10,16,0.5)" }}>
            <div className="text-[9px] text-text-muted uppercase tracking-wider mb-1">Signal Score</div>
            <div className="text-sm font-data font-bold" style={{ color: biasColor(signal.bias) }}>
              {signal.final_score >= 0 ? "+" : ""}{signal.final_score.toFixed(3)}
            </div>
          </div>
          <div className="rounded-lg p-2.5" style={{ backgroundColor: "rgba(6,10,16,0.5)" }}>
            <div className="text-[9px] text-text-muted uppercase tracking-wider mb-1">24h Move</div>
            <div className="text-sm font-data font-bold" style={{ color: (signal.magnitude_24h_pct ?? 0) >= 0 ? "#10b981" : "#ef4444" }}>
              {fmtPct(signal.magnitude_24h_pct)}
            </div>
          </div>
        </div>

        {/* Component scores */}
        <div className="rounded-lg p-3" style={{ backgroundColor: "rgba(6,10,16,0.5)" }}>
          <div className="text-[9px] text-text-muted uppercase tracking-wider mb-2 font-medium">
            Component Scores
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            {[
              { label: "Spot Flow", val: signal.spot_flow },
              { label: "Leverage", val: signal.leverage_pos },
              { label: "Options", val: signal.options_struct },
              { label: "Mean Rev", val: signal.mean_reversion },
            ].map(({ label, val }) => (
              <div key={label} className="flex justify-between items-center">
                <span className="text-[10px] text-text-muted">{label}</span>
                <span
                  className="text-[11px] font-data font-bold"
                  style={{ color: val > 0.05 ? "#10b981" : val < -0.05 ? "#ef4444" : "#94a3b8" }}
                >
                  {val >= 0 ? "+" : ""}{val.toFixed(3)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-3 mt-3 text-[10px] text-text-muted font-data">
          <span>Regime: {signal.regime?.replace(/_/g, " ")}</span>
          <span>·</span>
          <span>Confidence: {signal.confidence}</span>
          <span>·</span>
          <span>Event Risk: {(signal.event_risk * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
}

/* ── Trade History Table ────────────────────────────── */

function TradeHistorySection() {
  const { data: outcomes, isLoading } = useSignalOutcomes(30);
  const [selected, setSelected] = useState<SignalOutcome | null>(null);

  if (isLoading) {
    return (
      <div className="card p-5">
        <div className="text-text-muted animate-pulse text-xs font-data">Loading signal history...</div>
      </div>
    );
  }

  if (!outcomes || outcomes.length === 0) {
    return (
      <div className="card p-5 text-center text-text-muted text-xs">
        No signal history available
      </div>
    );
  }

  return (
    <>
      <div className="card p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-3">
          Signal History (30d)
        </h2>

        {/* Scrollable table */}
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-text-muted text-[9px] uppercase tracking-wider border-b border-border-subtle">
                <th className="text-left py-2 px-2 font-medium">Date</th>
                <th className="text-center py-2 px-1 font-medium">Bias</th>
                <th className="text-right py-2 px-2 font-medium">Entry</th>
                <th className="text-right py-2 px-2 font-medium">24h Price</th>
                <th className="text-right py-2 px-2 font-medium">24h Move</th>
                <th className="text-center py-2 px-2 font-medium">Result</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.map((s, i) => {
                const tag = outcomeTag(s.correct);
                return (
                  <tr
                    key={i}
                    className="border-b border-border-subtle/20 cursor-pointer transition-colors hover:bg-bg-card-hover/50"
                    onClick={() => setSelected(s)}
                  >
                    <td className="py-2 px-2 font-data text-text-secondary whitespace-nowrap">
                      <div className="text-[11px]">{fmtDate(s.timestamp)}</div>
                      <div className="text-[9px] text-text-muted">{fmtTime(s.timestamp)}</div>
                    </td>
                    <td className="text-center py-2 px-1">
                      <span className="text-sm" style={{ color: biasColor(s.bias) }}>
                        {biasIcon(s.bias)}
                      </span>
                    </td>
                    <td className="text-right py-2 px-2 font-data font-medium text-text-secondary text-[11px]">
                      ${fmtPrice(s.btc_price_at_signal)}
                    </td>
                    <td className="text-right py-2 px-2 font-data font-medium text-[11px]"
                        style={{ color: s.btc_price_24h_later ? ((s.magnitude_24h_pct ?? 0) >= 0 ? "#10b981" : "#ef4444") : "#475569" }}>
                      {s.btc_price_24h_later ? `$${fmtPrice(s.btc_price_24h_later)}` : "—"}
                    </td>
                    <td className="text-right py-2 px-2 font-data font-bold text-[11px]"
                        style={{ color: s.magnitude_24h_pct != null ? (s.magnitude_24h_pct >= 0 ? "#10b981" : "#ef4444") : "#475569" }}>
                      {fmtPct(s.magnitude_24h_pct)}
                    </td>
                    <td className="text-center py-2 px-2">
                      <span
                        className="text-[9px] font-bold font-data px-1.5 py-0.5 rounded"
                        style={{ color: tag.color, backgroundColor: tag.bg }}
                      >
                        {tag.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="mt-2 text-[10px] text-text-muted text-center">
          Click any row to view details and price trajectory
        </div>
      </div>

      {/* Detail modal */}
      {selected && <SignalDetailModal signal={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

/* ── Main Page ──────────────────────────────────────── */

export default function PerformancePage() {
  const { data: perf, isLoading: perfLoading } = usePerformance(30);
  const { data: health } = useHealth();

  if (perfLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted animate-pulse font-data text-sm">Loading performance...</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Win rate summary */}
      {perf?.win_rate && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard
            label="Win Rate"
            value={`${perf.win_rate.win_rate.toFixed(1)}%`}
            sub={`${perf.win_rate.total} total signals`}
            color={perf.win_rate.win_rate >= 55 ? "#10b981" : perf.win_rate.win_rate >= 45 ? "#f59e0b" : "#ef4444"}
          />
          <MetricCard
            label="Wins"
            value={perf.win_rate.wins}
            color="#10b981"
          />
          <MetricCard
            label="Losses"
            value={perf.win_rate.losses}
            color="#ef4444"
          />
          <MetricCard
            label="Total"
            value={perf.win_rate.total}
            color="#94a3b8"
          />
        </div>
      )}

      {/* Win rate visual */}
      {perf?.win_rate && perf.win_rate.total > 0 && (
        <div className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-3">
            Win / Loss Distribution
          </h2>
          <div className="h-5 rounded-full overflow-hidden flex">
            <div
              className="h-full transition-all duration-700 flex items-center justify-center text-[9px] font-bold font-data"
              style={{
                width: `${(perf.win_rate.wins / perf.win_rate.total) * 100}%`,
                backgroundColor: "#10b981",
                minWidth: perf.win_rate.wins > 0 ? "30px" : 0,
              }}
            >
              {perf.win_rate.wins > 0 ? `${perf.win_rate.wins}W` : ""}
            </div>
            <div
              className="h-full transition-all duration-700 flex items-center justify-center text-[9px] font-bold font-data"
              style={{
                width: `${(perf.win_rate.losses / perf.win_rate.total) * 100}%`,
                backgroundColor: "#ef4444",
                minWidth: perf.win_rate.losses > 0 ? "30px" : 0,
              }}
            >
              {perf.win_rate.losses > 0 ? `${perf.win_rate.losses}L` : ""}
            </div>
          </div>
        </div>
      )}

      {/* Signal History / Trade Log */}
      <TradeHistorySection />

      {/* Component accuracy */}
      {perf?.component_accuracy && (
        <div className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-4">
            Component Accuracy (30d)
          </h2>
          <div className="space-y-3">
            <AccuracyBar label="Spot Flow" value={perf.component_accuracy.spot_flow} />
            <AccuracyBar label="Leverage Position" value={perf.component_accuracy.leverage_pos} />
            <AccuracyBar label="Options Structure" value={perf.component_accuracy.options_struct} />
            <AccuracyBar label="Mean Reversion" value={perf.component_accuracy.mean_reversion} />
          </div>
        </div>
      )}

      {/* Regime accuracy */}
      {perf?.regime_accuracy && Object.keys(perf.regime_accuracy).length > 0 && (
        <div className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-4">
            Accuracy by Regime
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-text-muted text-[10px] uppercase tracking-wider border-b border-border-subtle">
                  <th className="text-left py-2 px-2 font-medium">Regime</th>
                  <th className="text-right py-2 px-2 font-medium">Accuracy</th>
                  <th className="text-right py-2 px-2 font-medium">Visual</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(perf.regime_accuracy)
                  .sort(([, a], [, b]) => b - a)
                  .map(([regime, accuracy]) => {
                    const pct = accuracy * 100;
                    const color =
                      pct >= 60 ? "#10b981" : pct >= 45 ? "#f59e0b" : "#ef4444";
                    return (
                      <tr key={regime} className="border-b border-border-subtle/30">
                        <td className="py-2.5 px-2 font-medium text-text-secondary capitalize">
                          {regime.replace(/_/g, " ")}
                        </td>
                        <td className="text-right py-2.5 px-2 font-data font-bold" style={{ color }}>
                          {pct.toFixed(1)}%
                        </td>
                        <td className="text-right py-2.5 px-2 w-32">
                          <div className="h-1.5 bg-bg-primary rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${pct}%`,
                                backgroundColor: color,
                                opacity: 0.8,
                              }}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* System health */}
      {health && (
        <div className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-4">
            System Health
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
            <MetricCard
              label="Status"
              value={health.status?.toUpperCase() ?? "---"}
              color={health.status === "ok" ? "#10b981" : "#ef4444"}
            />
            <MetricCard
              label="Uptime"
              value={health.uptime_seconds ? formatUptime(health.uptime_seconds) : "---"}
              color="#94a3b8"
            />
            <MetricCard
              label="Last Signal"
              value={
                health.last_signal
                  ? new Date(health.last_signal).toLocaleString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "---"
              }
              color="#94a3b8"
            />
          </div>

          {/* Collector statuses */}
          {health.collectors && Object.keys(health.collectors).length > 0 && (
            <div>
              <h3 className="text-text-muted text-[10px] uppercase tracking-wider mb-2 font-medium">
                Data Collectors
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                {Object.entries(health.collectors).map(([name, info]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between py-1.5 px-2.5 rounded bg-bg-primary/50 text-xs"
                  >
                    <span className="text-text-secondary capitalize text-[10px]">
                      {name.replace(/_/g, " ")}
                    </span>
                    <span
                      className="font-bold font-data text-[10px]"
                      style={{
                        color: info.status === "ok" ? "#10b981" : "#ef4444",
                      }}
                    >
                      {info.status?.toUpperCase() ?? "---"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* No data state */}
      {!perf && (
        <div className="flex items-center justify-center h-64">
          <div className="text-text-muted text-sm">No performance data available</div>
        </div>
      )}
    </div>
  );
}
