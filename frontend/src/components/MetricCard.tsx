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
      className={`bg-bg-primary/50 rounded-lg border border-border-subtle/30 p-4 ${className}`}
    >
      <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1 font-medium">
        {label}
      </div>
      <div
        className="text-xl font-bold leading-tight font-data"
        style={color ? { color } : undefined}
      >
        {value}
      </div>
      {sub && (
        <div className="text-text-muted text-[10px] mt-0.5 font-data">{sub}</div>
      )}
    </div>
  );
}
