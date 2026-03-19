import { useEffect, useRef } from "react";
import { createChart, type IChartApi, ColorType, LineStyle, AreaSeries, LineSeries } from "lightweight-charts";
import MetricCard from "../components/MetricCard";
import { useFuturesHistory } from "../hooks/useFutures";
import type { FuturesSnapshot } from "../api/client";

interface TimeSeriesChartProps {
  data: { time: number; value: number }[];
  color: string;
  height?: number;
  baselineValue?: number;
}

function TimeSeriesChart({
  data,
  color,
  height = 200,
  baselineValue,
}: TimeSeriesChartProps) {
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
      height,
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

    const series = chart.addSeries(AreaSeries, {
      lineColor: color,
      topColor: color + "40",
      bottomColor: color + "05",
      lineWidth: 2,
      priceLineVisible: false,
    });

    series.setData(data as Parameters<typeof series.setData>[0]);

    if (baselineValue !== undefined) {
      series.createPriceLine({
        price: baselineValue,
        color: "#475569",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
      });
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
  }, [data, color, height, baselineValue]);

  return <div ref={containerRef} className="w-full" />;
}

function prepareTimeSeries(
  snapshots: FuturesSnapshot[],
  field: keyof FuturesSnapshot
) {
  const sorted = [...snapshots].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );
  return sorted.map((d) => ({
    time: new Date(d.timestamp).getTime() / 1000,
    value: d[field] as number,
  }));
}

function getFundingColor(rate: number) {
  if (rate > 0.01) return "#10b981";
  if (rate < -0.01) return "#ef4444";
  return "#6366f1";
}

const FUNDING_LINES = [
  { field: "funding_binance" as keyof FuturesSnapshot, label: "Binance", color: "#f59e0b" },
  { field: "funding_bybit" as keyof FuturesSnapshot, label: "Bybit", color: "#06b6d4" },
  { field: "funding_okx" as keyof FuturesSnapshot, label: "OKX", color: "#a78bfa" },
  { field: "funding_weighted_avg" as keyof FuturesSnapshot, label: "Weighted Avg", color: "#f1f5f9" },
];

function FundingRateChart({ snapshots }: { snapshots: FuturesSnapshot[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || snapshots.length === 0) return;

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
      height: 240,
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

    const sorted = [...snapshots].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );

    for (const line of FUNDING_LINES) {
      const isAvg = line.field === "funding_weighted_avg";
      const series = chart.addSeries(LineSeries, {
        color: line.color,
        lineWidth: isAvg ? 2 : 1,
        lineStyle: isAvg ? LineStyle.Solid : LineStyle.Dotted,
        priceLineVisible: false,
        crosshairMarkerRadius: 3,
        title: line.label,
      });

      const data = sorted.map((d) => ({
        time: (new Date(d.timestamp).getTime() / 1000) as number,
        value: ((d[line.field] as number) ?? 0) * 100,
      }));

      series.setData(data as Parameters<typeof series.setData>[0]);

      if (isAvg) {
        series.createPriceLine({
          price: 0,
          color: "#475569",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: false,
        });
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
  }, [snapshots]);

  return <div ref={containerRef} className="w-full" />;
}

export default function FuturesPage({ symbol }: { symbol?: string }) {
  const { data: futures, isLoading } = useFuturesHistory(7, symbol);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted animate-pulse font-data text-sm">Loading futures data...</div>
      </div>
    );
  }

  if (!futures || futures.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted text-sm">No futures data available</div>
      </div>
    );
  }

  const latest = futures[futures.length - 1];

  const oiData = prepareTimeSeries(futures, "oi_total_usd");
  const basisData = prepareTimeSeries(futures, "basis_pct");
  const lsData = prepareTimeSeries(futures, "top_trader_ls_ratio");

  const fundingColor = getFundingColor(latest.funding_weighted_avg);

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard
          label="Funding Rate"
          value={`${latest.funding_weighted_avg >= 0 ? "+" : ""}${(latest.funding_weighted_avg * 100).toFixed(4)}%`}
          sub="OI-Weighted Avg"
          color={fundingColor}
        />
        <MetricCard
          label="Open Interest"
          value={`$${(latest.oi_total_usd / 1e9).toFixed(2)}B`}
          sub="Total USD"
          color="#6366f1"
        />
        <MetricCard
          label="Basis"
          value={`${latest.basis_pct >= 0 ? "+" : ""}${latest.basis_pct.toFixed(3)}%`}
          sub="Futures Premium"
          color={latest.basis_pct >= 0 ? "#10b981" : "#ef4444"}
        />
        <MetricCard
          label="L/S Ratio"
          value={latest.top_trader_ls_ratio.toFixed(3)}
          sub={latest.top_trader_ls_ratio > 1 ? "Long bias" : "Short bias"}
          color={latest.top_trader_ls_ratio > 1 ? "#10b981" : "#ef4444"}
        />
      </div>

      {/* Per-exchange funding rates */}
      <div className="card p-4">
        <h2 className="text-[10px] uppercase tracking-wider text-text-muted font-medium mb-3">
          Funding Rate by Exchange
        </h2>
        <div className="grid grid-cols-3 gap-3">
          {[
            { name: "Binance", rate: latest.funding_binance },
            { name: "Bybit", rate: latest.funding_bybit },
            { name: "OKX", rate: latest.funding_okx },
          ].map((ex) => {
            const r = ex.rate ?? 0;
            const c = getFundingColor(r);
            return (
              <div key={ex.name} className="flex items-center justify-between py-1.5 px-2.5 rounded bg-bg-primary/50">
                <span className="text-[10px] text-text-secondary font-medium">{ex.name}</span>
                <span className="text-[11px] font-bold font-data" style={{ color: c }}>
                  {r >= 0 ? "+" : ""}{(r * 100).toFixed(4)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Funding Rate Chart — multi-line */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
            Funding Rate % (7d)
          </h2>
          <div className="flex gap-3 text-[9px] font-data text-text-muted">
            {FUNDING_LINES.map((l) => (
              <span key={l.label} className="flex items-center gap-1">
                <span
                  className="w-2.5 h-[2px] inline-block"
                  style={{
                    backgroundColor: l.color,
                    borderStyle: l.field === "funding_weighted_avg" ? "solid" : "dotted",
                  }}
                />
                {l.label}
              </span>
            ))}
          </div>
        </div>
        <FundingRateChart snapshots={futures} />
      </div>

      {/* OI Chart */}
      <div className="card p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-3">
          Open Interest USD (7d)
        </h2>
        <TimeSeriesChart data={oiData} color="#f59e0b" />
      </div>

      {/* Basis + L/S side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-3">
            Basis % (7d)
          </h2>
          <TimeSeriesChart
            data={basisData}
            color="#10b981"
            height={180}
            baselineValue={0}
          />
        </div>
        <div className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-3">
            Top Trader L/S Ratio (7d)
          </h2>
          <TimeSeriesChart
            data={lsData}
            color="#ef4444"
            height={180}
            baselineValue={1}
          />
        </div>
      </div>

      {/* Taker Buy/Sell */}
      <div className="card p-4">
        <div className="flex justify-between items-center">
          <span className="text-[10px] uppercase tracking-wider text-text-muted font-medium">
            Taker Buy/Sell Ratio
          </span>
          <span
            className="text-lg font-bold font-data"
            style={{
              color: latest.taker_buy_sell_ratio > 1 ? "#10b981" : "#ef4444",
            }}
          >
            {latest.taker_buy_sell_ratio.toFixed(3)}
          </span>
        </div>
        <div className="mt-2 relative h-2.5 bg-bg-primary rounded-full overflow-hidden">
          {/* Map 0.8-1.2 range to bar width */}
          {(() => {
            const ratio = Math.max(0.5, Math.min(1.5, latest.taker_buy_sell_ratio));
            const pct = ((ratio - 0.5) / 1.0) * 100;
            return (
              <>
                <div className="absolute left-1/2 top-0 w-px h-full bg-text-muted/30 z-10" />
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${pct}%`,
                    background: `linear-gradient(to right, #ef4444, #6366f1 50%, #10b981)`,
                    opacity: 0.7,
                  }}
                />
              </>
            );
          })()}
        </div>
        <div className="flex justify-between text-[9px] text-text-muted mt-1 font-data">
          <span>Sellers</span>
          <span>Buyers</span>
        </div>
      </div>
    </div>
  );
}
