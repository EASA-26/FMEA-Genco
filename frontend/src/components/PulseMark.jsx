// The ALCM diagnostic pulse mark used on the PDF cover, drawn as a rounded tile.
export default function PulseMark({ size = 36, tone = 'dark', className = '' }) {
  return (
    <span
      className={`pulse-mark pulse-mark-${tone} ${className}`}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.24) }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 30 30" width={size * 0.72} height={size * 0.72}>
        <polyline
          points="5,15 10.5,15 13,9.5 16.5,21.5 19.5,15 25,15"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
