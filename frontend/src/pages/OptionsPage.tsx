import { useEffect, useRef } from "react";
import { createChart, type IChartApi, ColorType, LineStyle, HistogramSeries, LineSeries } from "lightweight-charts";
import { useGex, useOptionsOI } from "../hooks/useOptions";

function GexChart({ data }: { data: { strike: number; call_gex: number; put_gex: number; net_gex: number; gamma_flip_price: number }[] }) {
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
      height: 300,
      rightPriceScale: {
        borderColor: "#1e293b",
      },
      timeScale: {
        borderColor: "#1e293b",
        visible: false,
      },
      crosshair: {
        horzLine: { color: "#475569", style: LineStyle.Dashed },
        vertLine: { color: "#475569", style: LineStyle.Dashed },
      },
    });

    chartRef.current = chart;

    // Sort by strike
    const sorted = [...data].sort((a, b) => a.strike - b.strike);

    // Use index as time for bar chart layout
    const callData = sorted.map((d, i) => ({
      time: (i + 1) as number,
      value: d.call_gex,
      color: "#00d4aa80",
    }));

    const putData = sorted.map((d, i) => ({
      time: (i + 1) as number,
      value: Math.abs(d.put_gex),
      color: "#ff475780",
    }));

    const netData = sorted.map((d, i) => ({
      time: (i + 1) as number,
      value: d.net_gex,
    }));

    const callSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: "gex",
      title: "Call GEX",
    });
    callSeries.setData(callData as Parameters<typeof callSeries.setData>[0]);

    const putSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: "gex",
      title: "Put GEX",
    });
    putSeries.setData(putData as Parameters<typeof putSeries.setData>[0]);

    const netSeries = chart.addSeries(LineSeries, {
      color: "#f59e0b",
      lineWidth: 2,
      priceScaleId: "gex",
      title: "Net GEX",
    });
    netSeries.setData(netData as Parameters<typeof netSeries.setData>[0]);

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

function formatStrike(strike: number) {
  if (strike >= 1000) return `${(strike / 1000).toFixed(0)}K`;
  return strike.toFixed(0);
}

function OITable({ data }: { data: { strike: number; call_oi: number; put_oi: number; expiry: string }[] }) {
  const sorted = [...data].sort((a, b) => (b.call_oi + b.put_oi) - (a.call_oi + a.put_oi)).slice(0, 15);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-text-muted uppercase tracking-wider border-b border-border-subtle">
            <th className="text-left py-2 px-2">Strike</th>
            <th className="text-right py-2 px-2">Call OI</th>
            <th className="text-right py-2 px-2">Put OI</th>
            <th className="text-right py-2 px-2">P/C Ratio</th>
            <th className="text-right py-2 px-2">Expiry</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => {
            const pcRatio = row.call_oi > 0 ? row.put_oi / row.call_oi : 0;
            const maxOi = Math.max(...sorted.map((d) => d.call_oi + d.put_oi));
            const totalOi = row.call_oi + row.put_oi;
            const barWidth = maxOi > 0 ? (totalOi / maxOi) * 100 : 0;

            return (
              <tr key={`${row.strike}-${row.expiry}-${i}`} className="border-b border-border-subtle/50 hover:bg-bg-card-hover transition-colors">
                <td className="py-2 px-2 font-medium">${formatStrike(row.strike)}</td>
                <td className="text-right py-2 px-2 text-bull">
                  {row.call_oi.toLocaleString()}
                </td>
                <td className="text-right py-2 px-2 text-bear">
                  {row.put_oi.toLocaleString()}
                </td>
                <td className="text-right py-2 px-2">
                  <span style={{ color: pcRatio > 1 ? "#ff4757" : "#00d4aa" }}>
                    {pcRatio.toFixed(2)}
                  </span>
                </td>
                <td className="text-right py-2 px-2 text-text-muted relative">
                  <div
                    className="absolute inset-0 opacity-10"
                    style={{
                      background: `linear-gradient(to right, #748ffc ${barWidth}%, transparent ${barWidth}%)`,
                    }}
                  />
                  <span className="relative">
                    {new Date(row.expiry).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function OptionsPage() {
  const { data: gexData, isLoading: gexLoading } = useGex();
  const { data: oiData, isLoading: oiLoading } = useOptionsOI();

  const gammaFlip = gexData && gexData.length > 0 ? gexData[0].gamma_flip_price : null;

  return (
    <div className="space-y-4">
      {/* Gamma flip price */}
      {gammaFlip && (
        <div className="bg-bg-card rounded-lg border border-border-subtle p-4 flex items-center justify-between">
          <div>
            <span className="text-text-secondary text-xs uppercase tracking-wider">
              Gamma Flip Price
            </span>
          </div>
          <span className="text-lg font-bold text-gold">
            ${gammaFlip.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </span>
        </div>
      )}

      {/* GEX Chart */}
      <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
        <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-3">
          GEX by Strike
        </h2>
        <div className="flex gap-4 mb-2 text-[10px]">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm bg-bull/50 inline-block" />
            Call GEX
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm bg-bear/50 inline-block" />
            Put GEX
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm bg-gold inline-block" />
            Net GEX
          </span>
        </div>
        {gexLoading ? (
          <div className="h-[300px] flex items-center justify-center text-text-muted animate-pulse">
            Loading GEX data...
          </div>
        ) : gexData && gexData.length > 0 ? (
          <GexChart data={gexData} />
        ) : (
          <div className="h-[300px] flex items-center justify-center text-text-muted">
            No GEX data available
          </div>
        )}
      </div>

      {/* OI Distribution */}
      <div className="bg-bg-card rounded-lg border border-border-subtle p-5">
        <h2 className="text-text-secondary text-xs uppercase tracking-wider mb-3">
          Options Open Interest (Top 15 Strikes)
        </h2>
        {oiLoading ? (
          <div className="h-32 flex items-center justify-center text-text-muted animate-pulse">
            Loading OI data...
          </div>
        ) : oiData && oiData.length > 0 ? (
          <OITable data={oiData} />
        ) : (
          <div className="h-32 flex items-center justify-center text-text-muted">
            No open interest data
          </div>
        )}
      </div>
    </div>
  );
}
