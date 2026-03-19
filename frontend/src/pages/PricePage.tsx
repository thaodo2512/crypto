import { useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  ColorType,
  LineStyle,
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
} from "lightweight-charts";
import { useLatestPrice, useKlines, useTechnicals } from "../hooks/usePrice";
import { useSignalOutcomes } from "../hooks/usePerformance";
import type { SignalOutcome } from "../api/client";

type Timeframe = { label: string; interval: string; limit: number };

const TIMEFRAMES: Timeframe[] = [
  { label: "1m", interval: "1m", limit: 120 },
  { label: "5m", interval: "5m", limit: 200 },
  { label: "15m", interval: "15m", limit: 200 },
  { label: "30m", interval: "30m", limit: 200 },
  { label: "1H", interval: "1h", limit: 200 },
  { label: "4H", interval: "4h", limit: 200 },
  { label: "1D", interval: "1d", limit: 120 },
];

// ── Candlestick Chart with Technical Overlays + Signal Markers ──

function PriceChart({
  data,
  technicals,
  signals,
}: {
  data: {
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }[];
  technicals: {
    vwap?: number;
    ema_21?: number;
    ema_55?: number;
    ema_200?: number;
    bb_upper?: number;
    bb_lower?: number;
  } | null;
  signals?: SignalOutcome[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const container = containerRef.current;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
        fontFamily: '"JetBrains Mono", "SF Mono", monospace',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#1a223620" },
        horzLines: { color: "#1a223640" },
      },
      width: container.clientWidth,
      height: 440,
      rightPriceScale: {
        borderColor: "#1a2236",
      },
      timeScale: {
        borderColor: "#1a2236",
        timeVisible: true,
      },
      crosshair: {
        horzLine: { color: "#475569", style: LineStyle.Dashed, labelBackgroundColor: "#1a2236" },
        vertLine: { color: "#475569", style: LineStyle.Dashed, labelBackgroundColor: "#1a2236" },
      },
    });

    chartRef.current = chart;

    const sorted = [...data].sort(
      (a, b) =>
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );

    const candleData = sorted.map((d) => ({
      time: (new Date(d.timestamp).getTime() / 1000) as number,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#10b981",
      wickDownColor: "#ef444480",
      wickUpColor: "#10b98180",
    });

    candleSeries.setData(
      candleData as Parameters<typeof candleSeries.setData>[0]
    );

    // Volume histogram
    const volumeData = sorted.map((d) => ({
      time: (new Date(d.timestamp).getTime() / 1000) as number,
      value: d.volume,
      color: d.close >= d.open ? "#10b98120" : "#ef444420",
    }));

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    volumeSeries.setData(
      volumeData as Parameters<typeof volumeSeries.setData>[0]
    );

    // ── Technical level lines ──
    if (technicals) {
      const levels: { price: number; color: string; label: string; style?: number }[] = [];

      if (technicals.vwap)
        levels.push({ price: technicals.vwap, color: "#f59e0b", label: "VWAP" });
      if (technicals.ema_21)
        levels.push({ price: technicals.ema_21, color: "#06b6d4", label: "EMA 21", style: LineStyle.Dotted });
      if (technicals.ema_55)
        levels.push({ price: technicals.ema_55, color: "#8b5cf6", label: "EMA 55", style: LineStyle.Dotted });
      if (technicals.ema_200)
        levels.push({ price: technicals.ema_200, color: "#ec4899", label: "EMA 200", style: LineStyle.Dotted });
      if (technicals.bb_upper)
        levels.push({ price: technicals.bb_upper, color: "#6366f1", label: "BB Upper", style: LineStyle.Dashed });
      if (technicals.bb_lower)
        levels.push({ price: technicals.bb_lower, color: "#6366f1", label: "BB Lower", style: LineStyle.Dashed });

      for (const lv of levels) {
        candleSeries.createPriceLine({
          price: lv.price,
          color: lv.color + "80",
          lineWidth: 1,
          lineStyle: lv.style ?? LineStyle.Solid,
          axisLabelVisible: true,
          title: lv.label,
        });
      }
    }

    // ── Signal entry/outcome markers ──
    if (signals && signals.length > 0) {
      const markers: {
        time: number;
        position: "aboveBar" | "belowBar";
        color: string;
        shape: "arrowUp" | "arrowDown" | "circle";
        text: string;
        price: number;
      }[] = [];

      for (const sig of signals) {
        // Only show MODERATE+ signals (passed entry gates)
        if (sig.strength !== "MODERATE" && sig.strength !== "STRONG") continue;

        const entryTime = Math.floor(new Date(sig.timestamp).getTime() / 1000);
        const isLong = sig.bias === "LONG";
        const entryPrice = sig.btc_price_at_signal;

        // Entry marker
        markers.push({
          time: entryTime,
          position: isLong ? "belowBar" : "aboveBar",
          color: isLong ? "#10b981" : "#ef4444",
          shape: isLong ? "arrowUp" : "arrowDown",
          text: `${isLong ? "L" : "S"} ${sig.strength === "STRONG" ? "★" : ""}`,
          price: entryPrice,
        });

        // Outcome marker at +24h if available
        if (sig.btc_price_24h_later != null && sig.correct != null) {
          const exitTime = entryTime + 24 * 3600;
          const isWin = sig.correct === 1;
          markers.push({
            time: exitTime,
            position: isLong ? "aboveBar" : "belowBar",
            color: isWin ? "#10b981" : "#ef4444",
            shape: "circle",
            text: isWin ? "✓" : "✗",
            price: sig.btc_price_24h_later,
          });
        }
      }

      // Sort markers by time (required by lightweight-charts)
      markers.sort((a, b) => a.time - b.time);

      if (markers.length > 0) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        createSeriesMarkers(candleSeries as any, markers as any);
      }
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (container && chartRef.current) {
        chartRef.current.applyOptions({ width: container.clientWidth });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [data, technicals, signals]);

  return <div ref={containerRef} className="w-full" />;
}

// ── Technical Metric ────────────────────────────────────

function TechMetric({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="bg-bg-primary/50 rounded-lg p-3 border border-border-subtle/30">
      <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
        {label}
      </div>
      <div
        className="text-base font-bold font-data"
        style={{ color: color ?? "#f1f5f9" }}
      >
        {value}
      </div>
      {sub && (
        <div className="text-[10px] text-text-muted mt-0.5 font-data">{sub}</div>
      )}
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────

export default function PricePage({ symbol }: { symbol?: string }) {
  const [tf, setTf] = useState(TIMEFRAMES[4]); // default 1H
  const { data: latestPrice } = useLatestPrice(symbol);
  const { data: ohlcv, isLoading } = useKlines(tf.interval, tf.limit, symbol);
  const { data: tech } = useTechnicals(symbol);
  const { data: signalOutcomes } = useSignalOutcomes(7, symbol);

  const price = latestPrice?.close;
  const change = latestPrice ? latestPrice.close - latestPrice.open : 0;
  const changePct =
    latestPrice && latestPrice.open !== 0
      ? (change / latestPrice.open) * 100
      : 0;
  const isUp = change >= 0;

  return (
    <div className="space-y-4">
      {/* ── Price Header ───────────────────────────────── */}
      <div className="card p-5">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1 font-medium">
              {symbol ?? "BTC"} / USDT
            </div>
            <div className="text-4xl font-bold font-data text-text-primary">
              $
              {price?.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }) ?? "---"}
            </div>
          </div>
          <div className="flex items-center gap-5 text-sm font-data">
            <span
              className="text-base font-bold"
              style={{ color: isUp ? "#10b981" : "#ef4444" }}
            >
              {isUp ? "+" : ""}
              {change.toFixed(2)} ({isUp ? "+" : ""}
              {changePct.toFixed(2)}%)
            </span>
            <span className="text-text-muted text-xs">
              H{" "}
              <span className="text-text-secondary">
                $
                {latestPrice?.high?.toLocaleString(undefined, {
                  maximumFractionDigits: 0,
                }) ?? "---"}
              </span>
            </span>
            <span className="text-text-muted text-xs">
              L{" "}
              <span className="text-text-secondary">
                $
                {latestPrice?.low?.toLocaleString(undefined, {
                  maximumFractionDigits: 0,
                }) ?? "---"}
              </span>
            </span>
          </div>
        </div>
      </div>

      {/* ── Chart with levels ──────────────────────────── */}
      <div className="card p-4">
        {/* Timeframe selector */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1">
            {TIMEFRAMES.map((t) => (
              <button
                key={t.interval}
                onClick={() => setTf(t)}
                className="px-2 py-1 rounded text-[10px] font-data font-bold uppercase transition-all duration-150"
                style={{
                  backgroundColor: tf.interval === t.interval ? "#1a2236" : "transparent",
                  color: tf.interval === t.interval ? "#f1f5f9" : "#475569",
                  border: tf.interval === t.interval ? "1px solid #2a3654" : "1px solid transparent",
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex gap-3 text-[9px] font-data text-text-muted">
            {tech && (
              <>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-[2px] bg-gold inline-block" />
                  VWAP
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-[2px] bg-cyan inline-block" />
                  EMA
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-[2px] bg-neutral inline-block opacity-60" />
                  BB
                </span>
              </>
            )}
            <span className="text-text-muted">│</span>
            <span className="flex items-center gap-1">
              <span style={{ color: "#10b981" }}>▲</span>
              Long
            </span>
            <span className="flex items-center gap-1">
              <span style={{ color: "#ef4444" }}>▼</span>
              Short
            </span>
          </div>
        </div>
        {isLoading ? (
          <div className="h-[440px] flex items-center justify-center text-text-muted animate-pulse font-data text-sm">
            Loading chart...
          </div>
        ) : ohlcv && ohlcv.length > 0 ? (
          <PriceChart data={ohlcv} technicals={tech ?? null} signals={signalOutcomes} />
        ) : (
          <div className="h-[440px] flex items-center justify-center text-text-muted text-sm">
            No price data
          </div>
        )}
      </div>

      {/* ── Technical Indicators Grid ──────────────────── */}
      {tech && (
        <div className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-4">
            Technical Indicators
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <TechMetric
              label="RSI (14)"
              value={tech.rsi_14?.toFixed(1) ?? "---"}
              sub={
                tech.rsi_14 >= 70
                  ? "Overbought"
                  : tech.rsi_14 <= 30
                    ? "Oversold"
                    : "Neutral"
              }
              color={
                tech.rsi_14 >= 70
                  ? "#ef4444"
                  : tech.rsi_14 <= 30
                    ? "#10b981"
                    : "#6366f1"
              }
            />
            <TechMetric
              label="ADX (14)"
              value={tech.adx_14?.toFixed(1) ?? "---"}
              sub={
                tech.adx_14 >= 40
                  ? "Strong trend"
                  : tech.adx_14 >= 25
                    ? "Moderate"
                    : "Weak/Range"
              }
              color={tech.adx_14 >= 25 ? "#f59e0b" : "#94a3b8"}
            />
            <TechMetric
              label="VWAP"
              value={`$${tech.vwap?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "---"}`}
              sub={
                price && tech.vwap
                  ? `${price > tech.vwap ? "Above" : "Below"} (${(((price - tech.vwap) / tech.vwap) * 100).toFixed(2)}%)`
                  : undefined
              }
              color={
                price && tech.vwap
                  ? price > tech.vwap
                    ? "#10b981"
                    : "#ef4444"
                  : undefined
              }
            />
            <TechMetric
              label="BB Width"
              value={`$${((tech.bb_upper ?? 0) - (tech.bb_lower ?? 0)).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              sub={`${tech.bb_upper?.toLocaleString(undefined, { maximumFractionDigits: 0 })} / ${tech.bb_lower?.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              color="#6366f1"
            />
          </div>

          {/* EMA cards */}
          <div className="mt-3 grid grid-cols-3 gap-3">
            {[
              { label: "EMA 21", value: tech.ema_21, color: "#06b6d4" },
              { label: "EMA 55", value: tech.ema_55, color: "#8b5cf6" },
              { label: "EMA 200", value: tech.ema_200, color: "#ec4899" },
            ].map((ema) => (
              <div
                key={ema.label}
                className="bg-bg-primary/50 rounded-lg p-3 border border-border-subtle/30"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: ema.color }}
                  />
                  <span className="text-[10px] uppercase tracking-wider text-text-muted">
                    {ema.label}
                  </span>
                </div>
                <div className="text-sm font-bold font-data text-text-primary">
                  $
                  {ema.value?.toLocaleString(undefined, {
                    maximumFractionDigits: 0,
                  }) ?? "---"}
                </div>
                {price && ema.value && (
                  <div
                    className="text-[10px] mt-0.5 font-data"
                    style={{
                      color: price > ema.value ? "#10b981" : "#ef4444",
                    }}
                  >
                    {price > ema.value ? "Above" : "Below"} (
                    {(((price - ema.value) / ema.value) * 100).toFixed(2)}
                    %)
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
