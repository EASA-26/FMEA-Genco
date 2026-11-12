// Decorative animated background (IZ's Genco Project Theme), plain-CSS port of the
// kit's AnimatedBackground.tsx. Styles live in styles/genco-theme.css (gt-bg-*).
// - "login": drifting electric glows over a faint grid, a cluster of meshing gears
//   turning in the bottom-left corner and a ghost report page building itself in the
//   top-right corner (a row is flagged amber, then ticked off, then a chart draws).
//   The sign-in page shows only the glows and grid (decorations={false}).
//   For navy pages: sign-in, session check and page error.
// - "app": two slow glows behind the page content, dark mode only. Light mode stays
//   still because any tint on gray-50 pulls gray-500 muted text below 4.5:1.
// It is hidden from screen readers, ignores the pointer, and stops moving for users
// who ask for reduced motion (the gears stand still and the report shows complete).
// Put it first inside a `position: relative; overflow: hidden` container and give the
// content after it `position: relative`.

// ------------------------------------------------------------------ Gears
// All gears share one tooth size (MODULE), so any two of them mesh when their centres
// are the sum of their pitch radii apart.
const MODULE = 8;
// Every gear turns one tooth in the same time, so meshing gears stay in step.
const SECONDS_PER_TOOTH = 2.4;

const point = (radius, angle) =>
  `${(radius * Math.cos(angle)).toFixed(2)} ${(radius * Math.sin(angle)).toFixed(2)}`;

// Outline of a gear centred on (0, 0) with a tooth centred on angle 0. Each tooth is a
// trapezoid: its flanks rise from the root circle at 0.23 of a tooth step either side
// of the tooth centre to the tip circle at 0.11. Teeth this slim leave at least 1.3
// units between meshing gears all the way round, so outlines never cross.
function gearPath(teeth) {
  const pitch = (MODULE * teeth) / 2;
  const tip = pitch + MODULE;
  const root = pitch - 1.25 * MODULE;
  const step = (2 * Math.PI) / teeth;
  let d = `M ${point(root, -0.23 * step)}`;
  for (let k = 0; k < teeth; k += 1) {
    const a = k * step;
    d += ` L ${point(tip, a - 0.11 * step)}`;
    d += ` A ${tip} ${tip} 0 0 1 ${point(tip, a + 0.11 * step)}`;
    d += ` L ${point(root, a + 0.23 * step)}`;
    d += ` A ${root} ${root} 0 0 1 ${point(root, a + 0.77 * step)}`;
  }
  return `${d} Z`;
}

// A chain of gears, each meshing with the one before it. `angle` (degrees, clockwise
// on screen) is the direction from the previous gear's centre to this one's.
const GEAR_CHAIN = [
  { teeth: 20, x: 120, y: 236 },
  { teeth: 12, angle: -42 },
  { teeth: 8, angle: 12 },
];

// Lays the chain out: centre, starting turn (degrees) and spin time of each gear. A
// gear's starting turn puts a gap of its own where the previous gear's tooth points.
function layoutGears(chain) {
  const gears = [];
  chain.forEach((spec, i) => {
    const pitch = (MODULE * spec.teeth) / 2;
    const toothStep = 360 / spec.teeth;
    let x = spec.x;
    let y = spec.y;
    let turn = 0;
    if (i > 0) {
      const prev = gears[i - 1];
      const rad = (spec.angle * Math.PI) / 180;
      x = prev.x + (prev.pitch + pitch) * Math.cos(rad);
      y = prev.y + (prev.pitch + pitch) * Math.sin(rad);
      // Where the contact point falls on the previous gear, as a fraction of its tooth
      // step (0 = a tooth centre). The two fractions must add up to half a step.
      const prevFraction = ((((spec.angle - prev.turn) / prev.toothStep) % 1) + 1) % 1;
      turn = spec.angle + 180 - (0.5 - prevFraction) * toothStep;
    }
    gears.push({
      teeth: spec.teeth,
      pitch,
      toothStep,
      x,
      y,
      turn,
      rim: pitch - 1.25 * MODULE - 8,
      path: gearPath(spec.teeth),
      duration: `${(spec.teeth * SECONDS_PER_TOOTH).toFixed(1)}s`,
      reverse: i % 2 === 1,
    });
  });
  return gears;
}

const GEARS = layoutGears(GEAR_CHAIN);

function Gears() {
  return (
    <svg className="gt-bg-gears" viewBox="0 0 420 340" focusable="false">
      {GEARS.map((g) => (
        <g key={g.teeth} transform={`translate(${g.x.toFixed(2)} ${g.y.toFixed(2)}) rotate(${g.turn.toFixed(2)})`}>
          <g
            className="gt-bg-gear"
            style={{ animationDuration: g.duration, animationDirection: g.reverse ? 'reverse' : 'normal' }}
          >
            <path className="gt-bg-gear-teeth" d={g.path} />
            <circle className="gt-bg-gear-line" r={g.rim} />
            <circle className="gt-bg-gear-line" r={Math.max(6, g.pitch * 0.18)} />
          </g>
        </g>
      ))}
    </svg>
  );
}

// ------------------------------------------------------------------ Report page
// Table rows on the ghost page: top edge and bar length. Row 3 is the one flagged.
const ROWS = [
  { y: 86, bar: 112 },
  { y: 108, bar: 94 },
  { y: 130, bar: 104 },
  { y: 152, bar: 84 },
  { y: 174, bar: 100 },
];

function ReportPage() {
  return (
    <svg className="gt-bg-report" viewBox="0 0 240 300" focusable="false">
      <g className="gt-bg-report-page">
        <rect className="gt-bg-report-sheet" x="10" y="10" width="220" height="280" rx="12" />
        <rect className="gt-bg-report-title" x="30" y="32" width="124" height="12" rx="3" />
        <rect className="gt-bg-report-sub" x="30" y="52" width="72" height="5" rx="2" />
        <line className="gt-bg-report-rule" x1="30" y1="72" x2="210" y2="72" />

        {ROWS.map((row, i) => (
          <g key={row.y} className={`gt-bg-report-row is-${i + 1}`}>
            <rect className="gt-bg-report-cell" x="30" y={row.y} width="26" height="8" rx="2" />
            <rect className="gt-bg-report-bar" x="64" y={row.y} width={row.bar} height="8" rx="2" />
          </g>
        ))}

        {/* Row 3: flagged amber (a failure found), then ticked off once it is handled. */}
        <g className="gt-bg-report-flag">
          <rect x="24" y="124" width="192" height="20" rx="5" />
          <circle cx="201" cy="134" r="4" />
        </g>
        <path className="gt-bg-report-tick" d="M 195 134 L 199 138 L 207 129" pathLength="1" />

        {/* Summary chart on the right (the side the sign-in card never covers): a ring
            that draws in two parts, 70% then 30%, with a short legend to its left. */}
        <rect className="gt-bg-report-sub" x="30" y="224" width="70" height="5" rx="2" />
        <rect className="gt-bg-report-sub" x="30" y="236" width="56" height="5" rx="2" />
        <rect className="gt-bg-report-sub" x="30" y="248" width="64" height="5" rx="2" />
        <circle className="gt-bg-report-track" cx="180" cy="238" r="24" />
        <path className="gt-bg-report-arc is-1" d="M 180 214 A 24 24 0 1 1 157.17 245.42" pathLength="1" />
        <path className="gt-bg-report-arc is-2" d="M 157.17 245.42 A 24 24 0 0 1 180 214" pathLength="1" />
      </g>
    </svg>
  );
}

// decorations (login only, default true): the gears and the ghost report page. The
// sign-in page turns them off (its blueprint drawing takes their place); the loading
// and error screens keep them.
export default function AnimatedBackground({ variant = 'app', decorations = true }) {
  if (variant === 'app') {
    return (
      <div aria-hidden="true" className="gt-bg gt-bg-app">
        <div className="gt-bg-orb-a" />
        <div className="gt-bg-orb-b" />
      </div>
    );
  }

  return (
    <div aria-hidden="true" className="gt-bg gt-bg-login">
      <div className="gt-bg-orb-a" />
      <div className="gt-bg-orb-b" />
      <div className="gt-bg-grid" />
      {decorations && <Gears />}
      {decorations && <ReportPage />}
    </div>
  );
}
