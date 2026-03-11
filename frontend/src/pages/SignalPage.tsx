import { useEffect, useRef } from "react";
import { createChart, type IChartApi, ColorType, LineStyle, LineSeries } from "lightweight-charts";
import SignalGauge from "../components/SignalGauge";
import ComponentBars from "../components/ComponentBars";
import MetricCard from "../components/MetricCard";
import { useLatestSignal, useSignalHistory, useDailySnapshot } from "../hooks/useSignal";

function getBiasDisplay(bias: string) {
  switch (bias?.toLowerCase()) {
    case "bullish":
      return { text: "BULLISH", color: "#00d4aa", icon: "\u25b2" };
    case "bearish":
      return { text: "BEARISH", color: "#ff4757", icon: "\u25bc" };
    default:
      return { text: "NEUTRAL", color: "#748ffc", icon: "\u25c6" };
  }
}

function getRegimeDisplay(regime: string) {
  switch (regime?.toLowerCase()) {
    case "trending":
      return { text: "TRENDING", color: "#00d4aa" };
    case "mean_reverting":
    case "mean-reverting":
      return { text: "MEAN-REV", color: "#748ffc" };
    case "volatile":
      return { text: "VOLATILE", color: "#f59e0b" };
    case "crisis":
      return { text: "CRISIS", color: "#ff4757" };
    default:
      return { text: regime?.toUpperCase() ?? "---", color: "#94a3b8" };
  }
}

function getEventRiskColor(risk: number) {
  if (risk >= 0.8) return "#ff4757";
  if (risk >= 0.5) return "#f59e0b";
  return "#00d4aa";
}

function SignalHistoryChart({ data }: { data: { timestamp: string; final_score: number }[] }) {
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
      height: 220,
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

    const lineData = sorted.map((d) => ({
      time: (new Date(d.timestamp).getTime() / 1000) as number,
      value: d.final_score,
    }));

    const lineSeries = chart.addSeries(LineSeries, {
      color: "#748ffc",
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerRadius: 4,
    });

    // Zero line
    lineSeries.createPriceLine({
      price: 0,
      color: "#475569",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: false,
    });

    lineSeries.setData(lineData as Parameters<typeof lineSeries.setData>[0]);
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

export default function SignalPage() {
  const { data: signal, isLoading: sigLoading } = useLatestSignal();
  const { data: history } = useSignalHistory(30);
  const { data: snapshot } = useDailySnapshot();

  if (sigLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted animate-pulse">Loading signals...</div>
      </div>
    );
  }

  if (!signal) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted">No signal data available</div>
      </div>
    );
  }

  const bias = getBiasDisplay(signal.bias);
  const regime = getRegimeDisplay(signal.regime);
  const eventRiskColor = getEventRiskColor(signal.event_risk);

  const componentBars = [
    { label: "Spot Flow", value: signal.spot_flow },
    { label: "Leverage", value: signal.leverage_pos },
    { label: "Options", value: signal.options_struct },
    { label: "Mean Rev", value: signal.mean_reversion },
  ];

  return (
    <div className="space-y-4">
      {/* Header row: price + snapshot */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard
          label="BTC Price"
          value={`$${signal.btc_price_at_signal?.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 }) ?? "---"}`}
          color="#e2e8f0"
        />
        <MetricCard
          label="Fear & Greed"
          value={snapshot?.fear_greed ?? "---"}
          color={
            snapshot
              ? snapshot.fear_greed >= 60
                ? "#00d4aa"
                : snapshot.fear_greed <= 40
                  ? "#ff4757"
                  : "#f59e0b"
              : undefined
          }
        />
        <MetricCard
          label="DVOL"
          value={snapshot?.dvol?.toFixed(1) ?? "---"}
          color="#f59e0b"
        />
        <MetricCard
          label="Regime"
          value={regime.text}
          color={regime.color}
        />
      </div>

      {/* Score gauge + component bars */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left: Gauge */}
        <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-text-secondary text-xs uppercase tracking-wider">
              Composite Score
            </h2>
            <span
              className="px-2.5 py-0.5 rounded text-xs font-bold"
              style={{
                backgroundColor: bias.color + "20",
                color: bias.color,
              }}
            >
              {bias.icon} {bias.text}
            </span>
          </div>
          <SignalGauge score={signal.final_score} />
          <div className="flex justify-between mt-3 text-xs text-text-muted">
            <span>
              Strength:{" "}
              <span className="text-text-secondary font-medium">
                {signal.strength?.toUpperCase() ?? "---"}
              </span>
            </span>
            <span>
              {new Date(signal.timestamp).toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        </div>

        {/* Right: Component signals + event risk */}
        <div className="space-y-4">
          <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
            <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-4">
              Component Signals
            </h2>
            <ComponentBars bars={componentBars} />
          </div>

          {/* Event Risk */}
          <div className="bg-bg-card rounded-lg border border-border-subtle p-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-text-secondary text-xs uppercase tracking-wider">
                Event Risk
              </span>
              <span
                className="text-sm font-bold"
                style={{ color: eventRiskColor }}
              >
                {signal.event_risk?.toFixed(2) ?? "---"}
                {signal.event_risk >= 0.8 ? " STAY OUT" : ""}
              </span>
            </div>
            <div className="relative h-2.5 bg-[#1e293b] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${(signal.event_risk ?? 0) * 100}%`,
                  backgroundColor: eventRiskColor,
                  opacity: 0.85,
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Signal History Chart */}
      <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
        <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-3">
          Signal History (30d)
        </h2>
        {history && history.length > 0 ? (
          <SignalHistoryChart data={history} />
        ) : (
          <div className="h-[220px] flex items-center justify-center text-text-muted text-sm">
            No history data
          </div>
        )}
      </div>
    </div>
  );
}
