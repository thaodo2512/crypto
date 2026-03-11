interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  className?: string;
}

export default function MetricCard({
  label,
  value,
  sub,
  color,
  className = "",
}: MetricCardProps) {
  return (
    <div
      className={`bg-bg-card rounded-lg border border-border-subtle p-4 ${className}`}
    >
      <div className="text-text-secondary text-[11px] uppercase tracking-wider mb-1">
        {label}
      </div>
      <div
        className="text-xl font-semibold leading-tight"
        style={color ? { color } : undefined}
      >
        {value}
      </div>
      {sub && (
        <div className="text-text-muted text-xs mt-1">{sub}</div>
      )}
    </div>
  );
}
