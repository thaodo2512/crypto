import { useEffect, useRef } from "react";
import { createChart, type IChartApi, ColorType, LineStyle, CandlestickSeries, HistogramSeries } from "lightweight-charts";
import MetricCard from "../components/MetricCard";
import { useLatestPrice, usePriceOHLCV, useTechnicals } from "../hooks/usePrice";

function CandlestickChart({ data }: { data: { timestamp: string; open: number; high: number; low: number; close: number; volume: number }[] }) {
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
        fontFamily: "JetBrains Mono, SF Mono, Menlo, monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      width: container.clientWidth,
      height: 400,
      rightPriceScale: {
        borderColor: "#1e293b",
      },
      timeScale: {
        borderColor: "#1e293b",
        timeVisible: true,
      },
      crosshair: {
        horzLine: { color: "#475569", style: LineStyle.Dashed },
        vertLine: { color: "#475569", style: LineStyle.Dashed },
      },
    });

    chartRef.current = chart;

    const sorted = [...data].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );

    const candleData = sorted.map((d) => ({
      time: (new Date(d.timestamp).getTime() / 1000) as number,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#00d4aa",
      downColor: "#ff4757",
      borderDownColor: "#ff4757",
      borderUpColor: "#00d4aa",
      wickDownColor: "#ff4757",
      wickUpColor: "#00d4aa",
    });

    candleSeries.setData(candleData as Parameters<typeof candleSeries.setData>[0]);

    // Volume as histogram
    const volumeData = sorted.map((d) => ({
      time: (new Date(d.timestamp).getTime() / 1000) as number,
      value: d.volume,
      color: d.close >= d.open ? "#00d4aa30" : "#ff475730",
    }));

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    volumeSeries.setData(volumeData as Parameters<typeof volumeSeries.setData>[0]);

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
  }, [data]);

  return <div ref={containerRef} className="w-full" />;
}

function getRsiColor(rsi: number) {
  if (rsi >= 70) return "#ff4757";
  if (rsi <= 30) return "#00d4aa";
  return "#748ffc";
}

function getAdxLabel(adx: number) {
  if (adx >= 40) return "Strong";
  if (adx >= 25) return "Moderate";
  return "Weak";
}

export default function PricePage() {
  const { data: latestPrice } = useLatestPrice();
  const { data: ohlcv, isLoading } = usePriceOHLCV(7);
  const { data: tech } = useTechnicals();

  const price = latestPrice?.close;
  const change = latestPrice ? latestPrice.close - latestPrice.open : 0;
  const changePct = latestPrice && latestPrice.open !== 0 ? (change / latestPrice.open) * 100 : 0;
  const isUp = change >= 0;

  return (
    <div className="space-y-4">
      {/* Price header */}
      <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2">
          <div>
            <div className="text-text-secondary text-xs uppercase tracking-wider mb-1">
              BTC / USDT
            </div>
            <div className="text-3xl font-bold text-text-primary">
              ${price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "---"}
            </div>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span style={{ color: isUp ? "#00d4aa" : "#ff4757" }}>
              {isUp ? "+" : ""}{change.toFixed(2)} ({isUp ? "+" : ""}{changePct.toFixed(2)}%)
            </span>
            <span className="text-text-muted">
              H: ${latestPrice?.high?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "---"}
            </span>
            <span className="text-text-muted">
              L: ${latestPrice?.low?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "---"}
            </span>
          </div>
        </div>
      </div>

      {/* Candlestick chart */}
      <div className="bg-bg-card rounded-lg border border-border-subtle p-4">
        <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-3">
          7-Day Price Chart
        </h2>
        {isLoading ? (
          <div className="h-[400px] flex items-center justify-center text-text-muted animate-pulse">
            Loading chart...
          </div>
        ) : ohlcv && ohlcv.length > 0 ? (
          <CandlestickChart data={ohlcv} />
        ) : (
          <div className="h-[400px] flex items-center justify-center text-text-muted">
            No price data
          </div>
        )}
      </div>

      {/* Technicals */}
      {tech && (
        <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
          <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-4">
            Technical Indicators
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <MetricCard
              label="RSI (14)"
              value={tech.rsi_14?.toFixed(1) ?? "---"}
              sub={tech.rsi_14 >= 70 ? "Overbought" : tech.rsi_14 <= 30 ? "Oversold" : "Neutral"}
              color={getRsiColor(tech.rsi_14)}
            />
            <MetricCard
              label="ADX (14)"
              value={tech.adx_14?.toFixed(1) ?? "---"}
              sub={getAdxLabel(tech.adx_14)}
              color={tech.adx_14 >= 25 ? "#f59e0b" : "#94a3b8"}
            />
            <MetricCard
              label="VWAP"
              value={`$${tech.vwap?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "---"}`}
              sub={price && tech.vwap ? (price > tech.vwap ? "Above" : "Below") : undefined}
              color={price && tech.vwap ? (price > tech.vwap ? "#00d4aa" : "#ff4757") : undefined}
            />
            <MetricCard
              label="BB Width"
              value={`$${((tech.bb_upper ?? 0) - (tech.bb_lower ?? 0)).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              sub={`${tech.bb_upper?.toLocaleString(undefined, { maximumFractionDigits: 0 })} / ${tech.bb_lower?.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              color="#748ffc"
            />
          </div>

          {/* EMA table */}
          <div className="mt-4 grid grid-cols-3 gap-3">
            {[
              { label: "EMA 21", value: tech.ema_21 },
              { label: "EMA 55", value: tech.ema_55 },
              { label: "EMA 200", value: tech.ema_200 },
            ].map((ema) => (
              <div key={ema.label} className="bg-bg-primary rounded p-3">
                <div className="text-text-muted text-[10px] uppercase tracking-wider">
                  {ema.label}
                </div>
                <div className="text-sm font-medium text-text-primary">
                  ${ema.value?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "---"}
                </div>
                {price && ema.value && (
                  <div
                    className="text-[10px] mt-0.5"
                    style={{ color: price > ema.value ? "#00d4aa" : "#ff4757" }}
                  >
                    {price > ema.value ? "Above" : "Below"} (
                    {(((price - ema.value) / ema.value) * 100).toFixed(2)}%)
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
