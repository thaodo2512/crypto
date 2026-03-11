import { useEffect, useRef } from "react";
import { createChart, type IChartApi, ColorType, LineStyle, AreaSeries } from "lightweight-charts";
import MetricCard from "../components/MetricCard";
import { useFuturesHistory } from "../hooks/useFutures";
import type { FuturesSnapshot } from "../api/client";

interface TimeSeriesChartProps {
  data: { time: number; value: number }[];
  color: string;
  height?: number;
  formatter?: (v: number) => string;
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
        fontFamily: "JetBrains Mono, SF Mono, Menlo, monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      width: container.clientWidth,
      height,
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
  if (rate > 0.01) return "#00d4aa";
  if (rate < -0.01) return "#ff4757";
  return "#748ffc";
}

export default function FuturesPage() {
  const { data: futures, isLoading } = useFuturesHistory(7);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted animate-pulse">Loading futures data...</div>
      </div>
    );
  }

  if (!futures || futures.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted">No futures data available</div>
      </div>
    );
  }

  const latest = futures[futures.length - 1];

  const fundingData = prepareTimeSeries(futures, "funding_weighted_avg");
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
          sub="Weighted Avg"
          color={fundingColor}
        />
        <MetricCard
          label="Open Interest"
          value={`$${(latest.oi_total_usd / 1e9).toFixed(2)}B`}
          sub="Total USD"
          color="#748ffc"
        />
        <MetricCard
          label="Basis"
          value={`${latest.basis_pct >= 0 ? "+" : ""}${latest.basis_pct.toFixed(3)}%`}
          sub="Futures Premium"
          color={latest.basis_pct >= 0 ? "#00d4aa" : "#ff4757"}
        />
        <MetricCard
          label="L/S Ratio"
          value={latest.top_trader_ls_ratio.toFixed(3)}
          sub={latest.top_trader_ls_ratio > 1 ? "Long bias" : "Short bias"}
          color={latest.top_trader_ls_ratio > 1 ? "#00d4aa" : "#ff4757"}
        />
      </div>

      {/* Funding Rate Chart */}
      <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
        <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-3">
          Funding Rate (7d)
        </h2>
        <TimeSeriesChart
          data={fundingData}
          color="#748ffc"
          baselineValue={0}
        />
      </div>

      {/* OI Chart */}
      <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
        <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-3">
          Open Interest USD (7d)
        </h2>
        <TimeSeriesChart data={oiData} color="#f59e0b" />
      </div>

      {/* Basis + L/S side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
          <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-3">
            Basis % (7d)
          </h2>
          <TimeSeriesChart
            data={basisData}
            color="#00d4aa"
            height={180}
            baselineValue={0}
          />
        </div>
        <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
          <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-3">
            Top Trader L/S Ratio (7d)
          </h2>
          <TimeSeriesChart
            data={lsData}
            color="#ff4757"
            height={180}
            baselineValue={1}
          />
        </div>
      </div>

      {/* Taker Buy/Sell */}
      <div className="bg-bg-card rounded-lg border border-border-subtle p-4">
        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-xs uppercase tracking-wider">
            Taker Buy/Sell Ratio
          </span>
          <span
            className="text-lg font-bold"
            style={{
              color: latest.taker_buy_sell_ratio > 1 ? "#00d4aa" : "#ff4757",
            }}
          >
            {latest.taker_buy_sell_ratio.toFixed(3)}
          </span>
        </div>
        <div className="mt-2 relative h-3 bg-[#1e293b] rounded-full overflow-hidden">
          {/* Map 0.8-1.2 range to bar width */}
          {(() => {
            const ratio = Math.max(0.5, Math.min(1.5, latest.taker_buy_sell_ratio));
            const pct = ((ratio - 0.5) / 1.0) * 100;
            return (
              <>
                <div className="absolute left-1/2 top-0 w-px h-full bg-text-muted/40 z-10" />
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${pct}%`,
                    background: `linear-gradient(to right, #ff4757, #748ffc 50%, #00d4aa)`,
                    opacity: 0.7,
                  }}
                />
              </>
            );
          })()}
        </div>
        <div className="flex justify-between text-[10px] text-text-muted mt-1">
          <span>Sellers</span>
          <span>Buyers</span>
        </div>
      </div>
    </div>
  );
}
