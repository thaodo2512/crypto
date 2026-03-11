import { useMemo } from "react";
import { useGex, useOptionsOI } from "../hooks/useOptions";
import { useLatestPrice } from "../hooks/usePrice";

// ── Helpers ─────────────────────────────────────────────

function fmt(n: number, decimals = 0) {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtK(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toFixed(0);
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
  raw: { strike: number; call_oi: number; put_oi: number; call_iv: number | null; put_iv: number | null }[]
): AggOi[] {
  const map = new Map<number, AggOi>();
  for (const r of raw) {
    const existing = map.get(r.strike);
    if (existing) {
      existing.call_oi += r.call_oi;
      existing.put_oi += r.put_oi;
      existing.total += r.call_oi + r.put_oi;
      if (r.call_iv != null) existing.call_iv = r.call_iv;
      if (r.put_iv != null) existing.put_iv = r.put_iv;
    } else {
      map.set(r.strike, {
        strike: r.strike,
        call_oi: r.call_oi,
        put_oi: r.put_oi,
        total: r.call_oi + r.put_oi,
        call_iv: r.call_iv,
        put_iv: r.put_iv,
      });
    }
  }
  return Array.from(map.values()).sort((a, b) => a.strike - b.strike);
}

function findMaxPain(oi: AggOi[]): number | null {
  if (oi.length === 0) return null;
  // Max pain = strike where total OI is highest (simplified)
  let best = oi[0];
  for (const row of oi) {
    if (row.total > best.total) best = row;
  }
  return best.strike;
}

// ── Metric Card ─────────────────────────────────────────

function Metric({
  label,
  value,
  sub,
  color,
  large,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
  large?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-text-muted font-medium">
        {label}
      </span>
      <span
        className={`font-data font-bold ${large ? "text-xl" : "text-base"}`}
        style={{ color: color ?? "#f1f5f9" }}
      >
        {value}
      </span>
      {sub && (
        <span className="text-[10px] text-text-muted font-data">{sub}</span>
      )}
    </div>
  );
}

// ── OI by Strike Chart (Butterfly/Tornado) ──────────────

function OiByStrikeChart({
  data,
  currentPrice,
  gammaFlip,
  maxPain,
}: {
  data: AggOi[];
  currentPrice: number;
  gammaFlip: number | null;
  maxPain: number | null;
}) {
  // Filter to ±15% of current price
  const filtered = useMemo(() => {
    const lo = currentPrice * 0.85;
    const hi = currentPrice * 1.15;
    return data.filter((d) => d.strike >= lo && d.strike <= hi);
  }, [data, currentPrice]);

  if (filtered.length === 0) return null;

  const maxOi = Math.max(...filtered.map((d) => Math.max(d.call_oi, d.put_oi)));
  const ROW_H = 16;
  const MARGIN = { top: 10, bottom: 10, left: 8, right: 8, center: 50 };
  const svgH = filtered.length * ROW_H + MARGIN.top + MARGIN.bottom;
  const halfW = 200;
  const svgW = halfW * 2 + MARGIN.left + MARGIN.right + MARGIN.center;
  const centerX = MARGIN.left + halfW;

  function yForStrike(strike: number) {
    const idx = filtered.findIndex((d) => d.strike === strike);
    if (idx < 0) {
      // Interpolate position
      for (let i = 0; i < filtered.length - 1; i++) {
        if (strike >= filtered[i].strike && strike <= filtered[i + 1].strike) {
          const t =
            (strike - filtered[i].strike) /
            (filtered[i + 1].strike - filtered[i].strike);
          return MARGIN.top + (i + t) * ROW_H + ROW_H / 2;
        }
      }
      return null;
    }
    return MARGIN.top + idx * ROW_H + ROW_H / 2;
  }

  function RefLine({
    price,
    label,
    color,
    dashed,
  }: {
    price: number;
    label: string;
    color: string;
    dashed?: boolean;
  }) {
    const y = yForStrike(price);
    if (y == null) return null;
    return (
      <g>
        <line
          x1={MARGIN.left}
          x2={svgW - MARGIN.right}
          y1={y}
          y2={y}
          stroke={color}
          strokeWidth={1.5}
          strokeDasharray={dashed ? "4 3" : undefined}
          opacity={0.8}
        />
        <rect
          x={svgW - MARGIN.right - 70}
          y={y - 8}
          width={62}
          height={16}
          rx={3}
          fill={color}
          opacity={0.15}
        />
        <text
          x={svgW - MARGIN.right - 39}
          y={y + 3.5}
          textAnchor="middle"
          className="level-label"
          fill={color}
        >
          {label}
        </text>
      </g>
    );
  }

  return (
    <div className="overflow-x-auto">
      <svg
        width="100%"
        viewBox={`0 0 ${svgW} ${svgH}`}
        className="min-w-[500px]"
      >
        {/* Column headers */}
        <text
          x={centerX - halfW / 2}
          y={8}
          textAnchor="middle"
          className="level-label"
          fill="#ef4444"
          opacity={0.6}
        >
          PUT OI
        </text>
        <text
          x={centerX + MARGIN.center + halfW / 2}
          y={8}
          textAnchor="middle"
          className="level-label"
          fill="#10b981"
          opacity={0.6}
        >
          CALL OI
        </text>

        {/* Bars */}
        {filtered.map((row, i) => {
          const y = MARGIN.top + i * ROW_H;
          const callW = maxOi > 0 ? (row.call_oi / maxOi) * halfW : 0;
          const putW = maxOi > 0 ? (row.put_oi / maxOi) * halfW : 0;
          const barH = ROW_H - 4;

          return (
            <g key={row.strike}>
              {/* Alternating row bg */}
              {i % 2 === 0 && (
                <rect
                  x={0}
                  y={y}
                  width={svgW}
                  height={ROW_H}
                  fill="#ffffff"
                  opacity={0.015}
                />
              )}

              {/* Put bar (left, growing from center) */}
              <rect
                x={centerX - putW}
                y={y + 2}
                width={putW}
                height={barH}
                rx={2}
                fill="#ef4444"
                opacity={0.7}
              />
              {putW > 30 && (
                <text
                  x={centerX - putW + 4}
                  y={y + ROW_H / 2 + 3}
                  className="level-label"
                  fill="#fca5a5"
                  opacity={0.8}
                >
                  {fmtK(row.put_oi)}
                </text>
              )}

              {/* Call bar (right, growing from center) */}
              <rect
                x={centerX + MARGIN.center}
                y={y + 2}
                width={callW}
                height={barH}
                rx={2}
                fill="#10b981"
                opacity={0.7}
              />
              {callW > 30 && (
                <text
                  x={centerX + MARGIN.center + callW - 4}
                  y={y + ROW_H / 2 + 3}
                  textAnchor="end"
                  className="level-label"
                  fill="#6ee7b7"
                  opacity={0.8}
                >
                  {fmtK(row.call_oi)}
                </text>
              )}

              {/* Strike label (center) */}
              <text
                x={centerX + MARGIN.center / 2}
                y={y + ROW_H / 2 + 3.5}
                textAnchor="middle"
                fill="#94a3b8"
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  fontWeight: 500,
                }}
              >
                {fmtK(row.strike)}
              </text>
            </g>
          );
        })}

        {/* Reference lines */}
        <RefLine
          price={currentPrice}
          label={`BTC $${fmtK(currentPrice)}`}
          color="#f1f5f9"
          dashed
        />
        {gammaFlip && (
          <RefLine
            price={gammaFlip}
            label={`γ FLIP`}
            color="#a78bfa"
          />
        )}
        {maxPain && (
          <RefLine
            price={maxPain}
            label={`MAX PAIN`}
            color="#f59e0b"
          />
        )}
      </svg>
    </div>
  );
}

// ── GEX by Strike Chart ─────────────────────────────────

function GexByStrikeChart({
  data,
  currentPrice,
  gammaFlip,
}: {
  data: { strike: number; call_gex: number; put_gex: number; net_gex: number }[];
  currentPrice: number;
  gammaFlip: number | null;
}) {
  const sorted = useMemo(() => {
    const lo = currentPrice * 0.80;
    const hi = currentPrice * 1.20;
    return [...data]
      .filter((d) => d.strike >= lo && d.strike <= hi)
      .sort((a, b) => a.strike - b.strike);
  }, [data, currentPrice]);

  if (sorted.length === 0) return null;

  const maxGex = Math.max(
    ...sorted.map((d) => Math.max(Math.abs(d.call_gex), Math.abs(d.put_gex)))
  );
  const maxNet = Math.max(...sorted.map((d) => Math.abs(d.net_gex)));

  const BAR_W = 16;
  const GAP = 3;
  const MARGIN = { top: 20, bottom: 40, left: 50, right: 20 };
  const chartH = 260;
  const svgW = sorted.length * (BAR_W * 2 + GAP) + MARGIN.left + MARGIN.right;
  const svgH = chartH + MARGIN.top + MARGIN.bottom;
  const zeroY = MARGIN.top + chartH / 2;

  function scaleGex(v: number) {
    if (maxGex === 0) return 0;
    return (v / maxGex) * (chartH / 2);
  }

  function scaleNet(v: number) {
    if (maxNet === 0) return 0;
    return (v / maxNet) * (chartH / 2);
  }

  function xForIdx(i: number) {
    return MARGIN.left + i * (BAR_W * 2 + GAP);
  }

  // Net GEX path
  const netPath = sorted
    .map((d, i) => {
      const x = xForIdx(i) + BAR_W;
      const y = zeroY - scaleNet(d.net_gex);
      return `${i === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  // Find vertical reference line positions
  function xForPrice(price: number) {
    for (let i = 0; i < sorted.length - 1; i++) {
      if (price >= sorted[i].strike && price <= sorted[i + 1].strike) {
        const t =
          (price - sorted[i].strike) /
          (sorted[i + 1].strike - sorted[i].strike);
        return xForIdx(i) + t * (BAR_W * 2 + GAP) + BAR_W;
      }
    }
    if (price <= sorted[0].strike) return xForIdx(0) + BAR_W;
    if (price >= sorted[sorted.length - 1].strike)
      return xForIdx(sorted.length - 1) + BAR_W;
    return null;
  }

  const priceX = xForPrice(currentPrice);
  const flipX = gammaFlip ? xForPrice(gammaFlip) : null;

  return (
    <div className="overflow-x-auto">
      <svg
        width="100%"
        viewBox={`0 0 ${svgW} ${svgH}`}
        className="min-w-[500px]"
      >
        {/* Grid lines */}
        <line
          x1={MARGIN.left}
          x2={svgW - MARGIN.right}
          y1={zeroY}
          y2={zeroY}
          stroke="#1a2236"
          strokeWidth={1}
        />
        {[-0.5, 0.5].map((frac) => (
          <line
            key={frac}
            x1={MARGIN.left}
            x2={svgW - MARGIN.right}
            y1={zeroY - frac * chartH}
            y2={zeroY - frac * chartH}
            stroke="#1a2236"
            strokeWidth={0.5}
            strokeDasharray="2 4"
          />
        ))}

        {/* Bars */}
        {sorted.map((d, i) => {
          const x = xForIdx(i);
          const callH = scaleGex(d.call_gex);
          const putH = scaleGex(Math.abs(d.put_gex));

          return (
            <g key={d.strike}>
              {/* Call GEX (above zero) */}
              <rect
                x={x}
                y={zeroY - callH}
                width={BAR_W}
                height={Math.max(callH, 0.5)}
                rx={1.5}
                fill="#10b981"
                opacity={0.7}
              />
              {/* Put GEX (below zero) */}
              <rect
                x={x + BAR_W}
                y={zeroY}
                width={BAR_W}
                height={Math.max(putH, 0.5)}
                rx={1.5}
                fill="#ef4444"
                opacity={0.7}
              />
              {/* Strike label */}
              {i % Math.ceil(sorted.length / 12) === 0 && (
                <text
                  x={x + BAR_W}
                  y={svgH - MARGIN.bottom + 14}
                  textAnchor="middle"
                  fill="#475569"
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "9px",
                  }}
                >
                  {fmtK(d.strike)}
                </text>
              )}
            </g>
          );
        })}

        {/* Net GEX line */}
        <path
          d={netPath}
          fill="none"
          stroke="#f59e0b"
          strokeWidth={2}
          strokeLinejoin="round"
        />

        {/* BTC price vertical line */}
        {priceX != null && (
          <g>
            <line
              x1={priceX}
              x2={priceX}
              y1={MARGIN.top}
              y2={MARGIN.top + chartH}
              stroke="#f1f5f9"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              opacity={0.6}
            />
            <text
              x={priceX}
              y={MARGIN.top - 4}
              textAnchor="middle"
              className="level-label"
              fill="#f1f5f9"
            >
              BTC
            </text>
          </g>
        )}

        {/* Gamma flip vertical line */}
        {flipX != null && (
          <g>
            <line
              x1={flipX}
              x2={flipX}
              y1={MARGIN.top}
              y2={MARGIN.top + chartH}
              stroke="#a78bfa"
              strokeWidth={1.5}
              opacity={0.7}
            />
            <text
              x={flipX}
              y={svgH - MARGIN.bottom + 28}
              textAnchor="middle"
              className="level-label"
              fill="#a78bfa"
            >
              γ FLIP
            </text>
          </g>
        )}

        {/* Y-axis labels */}
        <text
          x={MARGIN.left - 4}
          y={MARGIN.top + 4}
          textAnchor="end"
          fill="#475569"
          style={{ fontFamily: "var(--font-mono)", fontSize: "8px" }}
        >
          +GEX
        </text>
        <text
          x={MARGIN.left - 4}
          y={MARGIN.top + chartH}
          textAnchor="end"
          fill="#475569"
          style={{ fontFamily: "var(--font-mono)", fontSize: "8px" }}
        >
          -GEX
        </text>
      </svg>
    </div>
  );
}

// ── IV by Strike Chart ──────────────────────────────────

function IvByStrikeChart({
  data,
  currentPrice,
}: {
  data: AggOi[];
  currentPrice: number;
}) {
  const filtered = useMemo(() => {
    const lo = currentPrice * 0.80;
    const hi = currentPrice * 1.20;
    return data
      .filter(
        (d) =>
          d.strike >= lo &&
          d.strike <= hi &&
          (d.call_iv != null || d.put_iv != null)
      )
      .sort((a, b) => a.strike - b.strike);
  }, [data, currentPrice]);

  if (filtered.length < 3) return null;

  const allIv = filtered.flatMap((d) => [d.call_iv, d.put_iv].filter((v): v is number => v != null && v > 0));
  if (allIv.length === 0) return null;

  const minIv = Math.min(...allIv) * 0.9;
  const maxIv = Math.max(...allIv) * 1.1;

  const MARGIN = { top: 20, bottom: 35, left: 45, right: 15 };
  const chartH = 180;
  const chartW = 500;
  const svgW = chartW + MARGIN.left + MARGIN.right;
  const svgH = chartH + MARGIN.top + MARGIN.bottom;

  function scaleX(strike: number) {
    const lo = filtered[0].strike;
    const hi = filtered[filtered.length - 1].strike;
    if (hi === lo) return MARGIN.left;
    return MARGIN.left + ((strike - lo) / (hi - lo)) * chartW;
  }

  function scaleY(iv: number) {
    return MARGIN.top + chartH - ((iv - minIv) / (maxIv - minIv)) * chartH;
  }

  function makePath(key: "call_iv" | "put_iv") {
    const points = filtered
      .filter((d) => d[key] != null && d[key]! > 0)
      .map((d) => ({ x: scaleX(d.strike), y: scaleY(d[key]!) }));
    if (points.length < 2) return "";
    return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  }

  const priceX = scaleX(currentPrice);

  return (
    <div className="overflow-x-auto">
      <svg width="100%" viewBox={`0 0 ${svgW} ${svgH}`} className="min-w-[400px]">
        {/* Grid */}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const y = MARGIN.top + f * chartH;
          const iv = maxIv - f * (maxIv - minIv);
          return (
            <g key={f}>
              <line x1={MARGIN.left} x2={svgW - MARGIN.right} y1={y} y2={y} stroke="#1a2236" strokeWidth={0.5} />
              <text x={MARGIN.left - 4} y={y + 3} textAnchor="end" fill="#475569" style={{ fontFamily: "var(--font-mono)", fontSize: "8px" }}>
                {iv.toFixed(0)}%
              </text>
            </g>
          );
        })}

        {/* Call IV line */}
        <path d={makePath("call_iv")} fill="none" stroke="#10b981" strokeWidth={2} opacity={0.8} />
        {/* Put IV line */}
        <path d={makePath("put_iv")} fill="none" stroke="#ef4444" strokeWidth={2} opacity={0.8} />

        {/* Price line */}
        <line x1={priceX} x2={priceX} y1={MARGIN.top} y2={MARGIN.top + chartH} stroke="#f1f5f9" strokeWidth={1} strokeDasharray="3 3" opacity={0.4} />
        <text x={priceX} y={svgH - MARGIN.bottom + 14} textAnchor="middle" className="level-label" fill="#94a3b8">
          BTC
        </text>

        {/* X-axis labels */}
        {filtered
          .filter((_, i) => i % Math.ceil(filtered.length / 8) === 0)
          .map((d) => (
            <text
              key={d.strike}
              x={scaleX(d.strike)}
              y={svgH - MARGIN.bottom + 14}
              textAnchor="middle"
              fill="#475569"
              style={{ fontFamily: "var(--font-mono)", fontSize: "8px" }}
            >
              {fmtK(d.strike)}
            </text>
          ))}
      </svg>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────

export default function OptionsPage() {
  const { data: gexData, isLoading: gexLoading } = useGex();
  const { data: oiData, isLoading: oiLoading } = useOptionsOI();
  const { data: latestPrice } = useLatestPrice();

  const currentPrice = latestPrice?.close ?? 0;
  const gammaFlip =
    gexData && gexData.length > 0 ? gexData[0].gamma_flip_price : null;

  const aggregatedOi = useMemo(
    () => (oiData ? aggregateOi(oiData) : []),
    [oiData]
  );

  const maxPain = useMemo(() => findMaxPain(aggregatedOi), [aggregatedOi]);

  // Gamma territory
  const gammaDistance =
    gammaFlip && currentPrice
      ? ((currentPrice - gammaFlip) / currentPrice) * 100
      : null;
  const isPositiveGamma = gammaDistance != null && gammaDistance > 0;

  // P/C ratio
  const totalCallOi = aggregatedOi.reduce((s, r) => s + r.call_oi, 0);
  const totalPutOi = aggregatedOi.reduce((s, r) => s + r.put_oi, 0);
  const pcRatio = totalCallOi > 0 ? totalPutOi / totalCallOi : 0;

  const loading = gexLoading || oiLoading;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted animate-pulse font-data text-sm">
          Loading options data...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Gamma Territory Header ─────────────────────── */}
      <div className="card p-5">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">
            Gamma Exposure
          </h2>
          {gammaDistance != null && (
            <span
              className="px-2.5 py-1 rounded-md text-xs font-bold font-data"
              style={{
                backgroundColor: isPositiveGamma
                  ? "rgba(16,185,129,0.15)"
                  : "rgba(239,68,68,0.15)",
                color: isPositiveGamma ? "#10b981" : "#ef4444",
              }}
            >
              {isPositiveGamma ? "+γ" : "−γ"} TERRITORY
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-5">
          <Metric
            label="Gamma Flip"
            value={gammaFlip ? `$${fmt(gammaFlip)}` : "---"}
            color="#a78bfa"
            large
          />
          <Metric
            label="Distance"
            value={
              gammaDistance != null
                ? `${gammaDistance > 0 ? "+" : ""}${gammaDistance.toFixed(1)}%`
                : "---"
            }
            sub={
              isPositiveGamma
                ? "Above flip → dealers long γ"
                : "Below flip → dealers short γ"
            }
            color={isPositiveGamma ? "#10b981" : "#ef4444"}
          />
          <Metric
            label="Max Pain"
            value={maxPain ? `$${fmt(maxPain)}` : "---"}
            sub={
              maxPain && currentPrice
                ? `${((currentPrice - maxPain) / currentPrice * 100).toFixed(1)}% from spot`
                : undefined
            }
            color="#f59e0b"
          />
          <Metric
            label="P/C Ratio"
            value={pcRatio.toFixed(2)}
            sub={pcRatio > 1 ? "Put heavy (bearish)" : "Call heavy (bullish)"}
            color={pcRatio > 1 ? "#ef4444" : "#10b981"}
          />
          <Metric
            label="BTC Price"
            value={currentPrice ? `$${fmt(currentPrice)}` : "---"}
            color="#f1f5f9"
          />
        </div>
      </div>

      {/* ── OI by Strike ───────────────────────────────── */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">
            Open Interest by Strike
          </h2>
          <div className="flex gap-4 text-[10px] font-data text-text-muted">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-bear opacity-70" />
              Put OI
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-bull opacity-70" />
              Call OI
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-[2px] bg-purple inline-block" />
              γ Flip
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-[2px] bg-gold inline-block" />
              Max Pain
            </span>
          </div>
        </div>
        {aggregatedOi.length > 0 && currentPrice > 0 ? (
          <OiByStrikeChart
            data={aggregatedOi}
            currentPrice={currentPrice}
            gammaFlip={gammaFlip}
            maxPain={maxPain}
          />
        ) : (
          <div className="h-[300px] flex items-center justify-center text-text-muted text-sm">
            No open interest data
          </div>
        )}
      </div>

      {/* ── GEX by Strike ──────────────────────────────── */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">
            GEX by Strike
          </h2>
          <div className="flex gap-4 text-[10px] font-data text-text-muted">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-bull opacity-70" />
              Call GEX
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-bear opacity-70" />
              Put GEX
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-[2px] bg-gold inline-block" />
              Net GEX
            </span>
          </div>
        </div>
        {gexData && gexData.length > 0 && currentPrice > 0 ? (
          <GexByStrikeChart
            data={gexData}
            currentPrice={currentPrice}
            gammaFlip={gammaFlip}
          />
        ) : (
          <div className="h-[260px] flex items-center justify-center text-text-muted text-sm">
            No GEX data
          </div>
        )}
      </div>

      {/* ── IV Skew ────────────────────────────────────── */}
      {aggregatedOi.some((d) => d.call_iv != null || d.put_iv != null) && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">
              Implied Volatility by Strike
            </h2>
            <div className="flex gap-4 text-[10px] font-data text-text-muted">
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-[2px] bg-bull inline-block" />
                Call IV
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-[2px] bg-bear inline-block" />
                Put IV
              </span>
            </div>
          </div>
          <IvByStrikeChart data={aggregatedOi} currentPrice={currentPrice} />
        </div>
      )}

      {/* ── OI Table ───────────────────────────────────── */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary mb-4">
          Top Strikes by OI
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-data">
            <thead>
              <tr className="text-text-muted uppercase tracking-wider border-b border-border-subtle">
                <th className="text-left py-2.5 px-3">Strike</th>
                <th className="text-right py-2.5 px-3">Call OI</th>
                <th className="text-right py-2.5 px-3">Put OI</th>
                <th className="text-right py-2.5 px-3">Total</th>
                <th className="text-right py-2.5 px-3">P/C</th>
                <th className="text-right py-2.5 px-3">Call IV</th>
                <th className="text-right py-2.5 px-3">Put IV</th>
              </tr>
            </thead>
            <tbody>
              {[...aggregatedOi]
                .sort((a, b) => b.total - a.total)
                .slice(0, 15)
                .map((row) => {
                  const ratio =
                    row.call_oi > 0 ? row.put_oi / row.call_oi : 0;
                  const isMaxPain = maxPain === row.strike;
                  const isFlip = gammaFlip === row.strike;

                  return (
                    <tr
                      key={row.strike}
                      className={`border-b border-border-subtle/40 hover:bg-bg-elevated transition-colors ${
                        isMaxPain || isFlip ? "bg-bg-elevated/50" : ""
                      }`}
                    >
                      <td className="py-2 px-3 font-medium">
                        ${fmtK(row.strike)}
                        {isMaxPain && (
                          <span className="ml-1.5 text-[9px] text-gold">
                            MP
                          </span>
                        )}
                        {isFlip && (
                          <span className="ml-1.5 text-[9px] text-purple">
                            γ
                          </span>
                        )}
                      </td>
                      <td className="text-right py-2 px-3 text-bull">
                        {fmtK(row.call_oi)}
                      </td>
                      <td className="text-right py-2 px-3 text-bear">
                        {fmtK(row.put_oi)}
                      </td>
                      <td className="text-right py-2 px-3 text-text-secondary">
                        {fmtK(row.total)}
                      </td>
                      <td className="text-right py-2 px-3">
                        <span
                          style={{
                            color: ratio > 1 ? "#ef4444" : "#10b981",
                          }}
                        >
                          {ratio.toFixed(2)}
                        </span>
                      </td>
                      <td className="text-right py-2 px-3 text-text-muted">
                        {row.call_iv != null
                          ? `${row.call_iv.toFixed(1)}%`
                          : "—"}
                      </td>
                      <td className="text-right py-2 px-3 text-text-muted">
                        {row.put_iv != null
                          ? `${row.put_iv.toFixed(1)}%`
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
