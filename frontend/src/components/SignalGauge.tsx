interface SignalGaugeProps {
  score: number; // -1.0 to +1.0
  size?: number;
}

export default function SignalGauge({ score, size = 180 }: SignalGaugeProps) {
  const clampedScore = Math.max(-1, Math.min(1, score));

  // Map -1..+1 to 0..1 for the arc
  const normalized = (clampedScore + 1) / 2;

  // Arc goes from 135deg to 405deg (270deg sweep)
  const startAngle = 135;
  const sweepAngle = 270;
  const currentAngle = startAngle + normalized * sweepAngle;

  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 16;

  // Convert angle to radians for SVG
  const toRad = (deg: number) => (deg * Math.PI) / 180;

  // Arc path for the background
  const arcPath = (start: number, end: number) => {
    const s = toRad(start);
    const e = toRad(end);
    const x1 = cx + radius * Math.cos(s);
    const y1 = cy + radius * Math.sin(s);
    const x2 = cx + radius * Math.cos(e);
    const y2 = cy + radius * Math.sin(e);
    const largeArc = end - start > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`;
  };

  // Needle endpoint
  const needleAngle = toRad(currentAngle);
  const needleLen = radius - 10;
  const nx = cx + needleLen * Math.cos(needleAngle);
  const ny = cy + needleLen * Math.sin(needleAngle);

  // Color based on score
  const getColor = () => {
    if (clampedScore > 0.2) return "#10b981";
    if (clampedScore < -0.2) return "#ef4444";
    return "#6366f1";
  };

  const color = getColor();

  // Determine the arc fill, splitting at mid-point for negative/positive
  const midAngle = startAngle + sweepAngle / 2;

  // Active arc from the center outward toward the score direction
  const activeArcStart = clampedScore >= 0 ? midAngle : currentAngle;
  const activeArcEnd = clampedScore >= 0 ? currentAngle : midAngle;

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size * 0.7} viewBox={`0 0 ${size} ${size * 0.75}`}>
        {/* Background arc */}
        <path
          d={arcPath(startAngle, startAngle + sweepAngle)}
          fill="none"
          stroke="#1a2236"
          strokeWidth={10}
          strokeLinecap="round"
        />

        {/* Active arc */}
        {Math.abs(clampedScore) > 0.01 && (
          <path
            d={arcPath(activeArcStart, activeArcEnd)}
            fill="none"
            stroke={color}
            strokeWidth={10}
            strokeLinecap="round"
            opacity={0.8}
          />
        )}

        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={nx}
          y2={ny}
          stroke={color}
          strokeWidth={2.5}
          strokeLinecap="round"
        />

        {/* Center dot */}
        <circle cx={cx} cy={cy} r={5} fill={color} />

        {/* Labels */}
        <text
          x={cx - radius + 4}
          y={cy + 20}
          fill="#475569"
          fontSize="10"
          fontFamily='"JetBrains Mono", monospace'
        >
          -1.0
        </text>
        <text
          x={cx + radius - 20}
          y={cy + 20}
          fill="#475569"
          fontSize="10"
          fontFamily='"JetBrains Mono", monospace'
        >
          +1.0
        </text>
      </svg>

      <div className="text-center -mt-2">
        <span className="text-3xl font-bold font-data" style={{ color }}>
          {clampedScore >= 0 ? "+" : ""}
          {clampedScore.toFixed(3)}
        </span>
      </div>
    </div>
  );
}
