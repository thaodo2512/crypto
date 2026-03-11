import MetricCard from "../components/MetricCard";
import { usePerformance, useHealth } from "../hooks/usePerformance";

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
            value={`${(perf.win_rate.win_rate * 100).toFixed(1)}%`}
            sub={`${perf.win_rate.total} total signals`}
            color={perf.win_rate.win_rate >= 0.55 ? "#10b981" : perf.win_rate.win_rate >= 0.45 ? "#f59e0b" : "#ef4444"}
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
