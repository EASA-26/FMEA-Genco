import { useMemo } from 'react';

// The cover's diagnostic motif (fading dot grid, concentric gauge rings, tick scale,
// arc accent and cross-hair), ported from design-preview/front_page_preview.py.
// Coordinates are in PDF points with the y axis flipped for SVG.
export default function GaugeMotif({ width = 595, height = 842, cx = 577, cy = 470, className = '', dots = true }) {
  const dotList = useMemo(() => {
    if (!dots) return [];
    const list = [];
    const step = 16;
    for (let gx = step / 2; gx < width; gx += step) {
      for (let gy = step / 2; gy < height; gy += step) {
        const d = Math.hypot(gx - cx, gy - cy);
        let a = Math.max(0, 0.26 * (1 - d / 330));
        a = Math.round(a / 0.02) * 0.02;
        if (a > 0) list.push([gx, gy, a]);
      }
    }
    return list;
  }, [width, height, cx, cy, dots]);

  const ticks = useMemo(() => {
    const list = [];
    for (let deg = 0; deg < 360; deg += 5) {
      const rad = (deg * Math.PI) / 180;
      const r0 = 118;
      const r1 = r0 + (deg % 30 === 0 ? 8 : 4);
      list.push([cx + r0 * Math.cos(rad), cy - r0 * Math.sin(rad), cx + r1 * Math.cos(rad), cy - r1 * Math.sin(rad)]);
    }
    return list;
  }, [cx, cy]);

  // Arc from 118 to 176 degrees (counter-clockwise in PDF space).
  const arc = useMemo(() => {
    const r = 176;
    const p = (deg) => {
      const rad = (deg * Math.PI) / 180;
      return [cx + r * Math.cos(rad), cy - r * Math.sin(rad)];
    };
    const [x0, y0] = p(118);
    const [x1, y1] = p(176);
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 0 0 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  }, [cx, cy]);

  return (
    <svg
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <g fill="#fff">
        {dotList.map(([x, y, a]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r="0.65" fillOpacity={a} />
        ))}
      </g>
      <g fill="none" stroke="#fff" strokeWidth="0.6">
        {[
          [62, 0.16],
          [118, 0.12],
          [176, 0.09],
          [236, 0.06],
        ].map(([r, a]) => (
          <circle key={r} cx={cx} cy={cy} r={r} strokeOpacity={a} />
        ))}
        <g strokeOpacity="0.18">
          {ticks.map(([x1, y1, x2, y2], i) => (
            <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} />
          ))}
        </g>
        <path d={arc} strokeWidth="2.2" strokeLinecap="round" strokeOpacity="0.24" />
        <g strokeWidth="0.5" strokeOpacity="0.07">
          <line x1={cx - 250} y1={cy} x2={cx + 20} y2={cy} />
          <line x1={cx} y1={cy - 250} x2={cx} y2={cy + 250} />
        </g>
      </g>
    </svg>
  );
}
