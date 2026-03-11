interface BarData {
  label: string;
  value: number; // -1.0 to +1.0
}

interface ComponentBarsProps {
  bars: BarData[];
}

export default function ComponentBars({ bars }: ComponentBarsProps) {
  return (
    <div className="space-y-3">
      {bars.map((bar) => {
        const clamped = Math.max(-1, Math.min(1, bar.value));
        const isPositive = clamped >= 0;
        const color = isPositive ? "#00d4aa" : "#ff4757";
        const widthPct = Math.abs(clamped) * 50; // 50% = full bar on one side

        return (
          <div key={bar.label}>
            <div className="flex justify-between items-center mb-1">
              <span className="text-text-secondary text-xs uppercase tracking-wider">
                {bar.label}
              </span>
              <span
                className="text-xs font-semibold"
                style={{ color }}
              >
                {clamped >= 0 ? "+" : ""}
                {clamped.toFixed(3)}
              </span>
            </div>
            <div className="relative h-2.5 bg-[#1e293b] rounded-full overflow-hidden">
              {/* Center line */}
              <div className="absolute left-1/2 top-0 w-px h-full bg-text-muted/40 z-10" />
              {/* Fill bar */}
              <div
                className="absolute top-0 h-full rounded-full transition-all duration-500"
                style={{
                  backgroundColor: color,
                  width: `${widthPct}%`,
                  left: isPositive ? "50%" : `${50 - widthPct}%`,
                  opacity: 0.85,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
