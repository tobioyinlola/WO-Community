import "../styles/learn.css";

/** A circle that fills as a number goes up. The number is also written in the middle. */
export function ProgressRing({ percent, size = 56, label = "Progress" }: { percent: number; size?: number; label?: string }) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  const stroke = 5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  return (
    <span className="wo-ring" style={{ width: size, height: size }} role="progressbar" aria-label={label} aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle className="wo-ring__track" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} fill="none" />
        <circle
          className="wo-ring__bar"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="wo-ring__text" aria-hidden="true">
        {clamped}%
      </span>
    </span>
  );
}
