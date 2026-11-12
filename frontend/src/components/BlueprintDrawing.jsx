import { useId } from 'react';

// The sign-in page's engineering drawing (styles: styles/login-blueprint.css, bp-*).
// A drawing frame with zone letters and numbers around a 24px grid, holding one
// composition: a 12-tooth spur gear drawn as a technical drawing (centerlines, hub,
// lightening holes, keyed bore, diameter dimension), a fatigue crack, the Detail A
// callout of the crack origin with beach marks, a GENERATE arrow and a report with a
// ROOT CAUSE FOUND stamp.
//
// Motion is CSS only: the gear draws itself once and stays; the failure story (crack to
// stamp) loops slowly inside .bp-cycle. With reduced motion the finished drawing shows.
// Purely decorative: hidden from screen readers, and it never takes the pointer.
//
// Props: pulseKey (a number that goes up on every sign-in submit; each new value
// flashes the GENERATE arrow once).

const ZONES_TOP = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];
const ZONES_SIDE = ['1', '2', '3', '4', '5', '6'];

// 12-tooth spur gear, centre (200, 200): tip radius 124, root radius 103.
const GEAR =
  'M296.2,236.9 L311.5,254.4 A124,124 0 0 1 302.8,269.3 L280.0,264.8 A103,103 0 0 1 264.8,280.0 ' +
  'L269.3,302.8 A124,124 0 0 1 254.4,311.5 L236.9,296.2 A103,103 0 0 1 216.1,301.7 L208.6,323.7 ' +
  'A124,124 0 0 1 191.4,323.7 L183.9,301.7 A103,103 0 0 1 163.1,296.2 L145.6,311.5 A124,124 0 0 1 130.7,302.8 ' +
  'L135.2,280.0 A103,103 0 0 1 120.0,264.8 L97.2,269.3 A124,124 0 0 1 88.5,254.4 L103.8,236.9 ' +
  'A103,103 0 0 1 98.3,216.1 L76.3,208.6 A124,124 0 0 1 76.3,191.4 L98.3,183.9 A103,103 0 0 1 103.8,163.1 ' +
  'L88.5,145.6 A124,124 0 0 1 97.2,130.7 L120.0,135.2 A103,103 0 0 1 135.2,120.0 L130.7,97.2 ' +
  'A124,124 0 0 1 145.6,88.5 L163.1,103.8 A103,103 0 0 1 183.9,98.3 L191.4,76.3 A124,124 0 0 1 208.6,76.3 ' +
  'L216.1,98.3 A103,103 0 0 1 236.9,103.8 L254.4,88.5 A124,124 0 0 1 269.3,97.2 L264.8,120.0 ' +
  'A103,103 0 0 1 280.0,135.2 L302.8,130.7 A124,124 0 0 1 311.5,145.6 L296.2,163.1 A103,103 0 0 1 301.7,183.9 ' +
  'L323.7,191.4 A124,124 0 0 1 323.7,208.6 L301.7,216.1 A103,103 0 0 1 296.2,236.9 Z';

// Circles drawn as paths so they can draw themselves (pathLength on <path> works everywhere).
const circle = (cx, cy, r) => `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
const HOLES = [circle(278, 200, 13), circle(200, 278, 13), circle(122, 200, 13), circle(200, 122, 13)];

// Detail A: the fracture surface under the tooth edge, and its beach marks.
const SURFACE = 'M396 58C440 58 452 118 480 118C508 118 520 58 564 58L564 204L396 204Z';
const BEACH_MARKS = [16, 28, 40, 52, 64].map((r) => `M${480 - r} 118A${r} ${r} 0 0 0 ${480 + r} 118`);

// The report's field rules and filled-in values (drawn in one by one, left to right).
const FIELDS = [
  { kind: 'line', x: 398, y: 297.5, w: 174 },
  { kind: 'value', x: 466, y: 283, w: 96 },
  { kind: 'line', x: 398, y: 327.5, w: 174 },
  { kind: 'value', x: 456, y: 313, w: 78 },
  { kind: 'line', x: 398, y: 357.5, w: 174 },
  { kind: 'value', x: 492, y: 343, w: 70 },
];

export default function BlueprintDrawing({ pulseKey = 0 }) {
  // Clip-path ids must be unique on the page and safe inside url(#...).
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const detailClip = `bp-detail-${uid}`;
  const surfaceClip = `bp-surface-${uid}`;

  return (
    <div className="bp-sheet" aria-hidden="true">
      <div className="bp-sheet-corner" />
      <div className="bp-zones-top">
        {ZONES_TOP.map((zone) => (
          <span key={zone}>{zone}</span>
        ))}
      </div>
      <div className="bp-zones-side">
        {ZONES_SIDE.map((zone) => (
          <span key={zone}>{zone}</span>
        ))}
      </div>

      <div className="bp-sheet-body">
        <svg className="bp-art" viewBox="48 20 560 380" preserveAspectRatio="xMidYMid meet" focusable="false">
          <defs>
            <clipPath id={detailClip}>
              <circle cx="480" cy="112" r="82" />
            </clipPath>
            <clipPath id={surfaceClip}>
              <path d={SURFACE} />
            </clipPath>
          </defs>

          {/* The gear drawing: draws itself once and stays. */}
          <path className="bp-anim bp-gear-fill" d={GEAR} />
          <path className="bp-anim bp-cl-h bp-from-center bp-muted" strokeWidth="1" strokeDasharray="14 4 3 4" d="M56 200H344" />
          <path className="bp-anim bp-cl-v bp-from-center bp-muted" strokeWidth="1" strokeDasharray="14 4 3 4" d="M200 56V344" />
          <path className="bp-anim bp-gear-line bp-draw bp-line" strokeWidth="2" pathLength="1" d={GEAR} />
          <path className="bp-anim bp-hub bp-from-center bp-muted" strokeWidth="1" strokeDasharray="4 3" d={circle(200, 200, 52)} />
          {HOLES.map((d) => (
            <path key={d} className="bp-anim bp-hole bp-draw" strokeWidth="1.5" pathLength="1" d={d} />
          ))}
          <path
            className="bp-anim bp-bore bp-draw"
            strokeWidth="2"
            strokeLinejoin="round"
            pathLength="1"
            d="M194 170.6L194 163L206 163L206 170.6A30 30 0 1 1 194 170.6Z"
          />
          <path className="bp-anim bp-ext bp-draw bp-muted" strokeWidth="1" pathLength="1" d="M76 214V384M324 214V384" />
          <path className="bp-anim bp-dim bp-from-center bp-line" strokeWidth="1" d="M86 374H314" />
          <path className="bp-anim bp-dim-end bp-ink" d="M77 374l10-3.8v7.6z M323 374l-10-3.8v7.6z" />
          <text className="bp-anim bp-dim-text bp-ink" x="200" y="366" textAnchor="middle" fontSize="12">
            Ø 248
          </text>

          {/* The failure story: loops slowly (crack, Detail A, GENERATE, report, stamp). */}
          <g className="bp-cycle">
            <path
              className="bp-anim bp-crack bp-draw bp-marker"
              strokeWidth="3"
              pathLength="1"
              d="M272.8 127.2L266 136L268 143L258 150L260 158L249 163L246 172"
            />
            <circle className="bp-anim bp-detail bp-from-center bp-marker" cx="266" cy="138" r="26" strokeWidth="1.5" strokeDasharray="5 4" />
            <text className="bp-anim bp-detail-label bp-ink" x="236" y="106" fontSize="12" fontWeight="700">
              A
            </text>
            <path className="bp-anim bp-leader bp-marker" strokeWidth="1.5" strokeDasharray="5 4" d="M291.8 134.9L396.6 122.1" />

            <g className="bp-anim bp-callout bp-from-center">
              <circle className="bp-callout-bg" cx="480" cy="112" r="84" />
              <g clipPath={`url(#${detailClip})`}>
                <path className="bp-surface" d={SURFACE} />
                <g className="bp-muted" strokeWidth="1.2">
                  {BEACH_MARKS.map((d) => (
                    <path key={d} d={d} />
                  ))}
                </g>
                <g clipPath={`url(#${surfaceClip})`}>
                  <circle className="bp-anim bp-ripple bp-from-center" cx="480" cy="118" r="14" strokeWidth="1.5" />
                  <circle className="bp-anim bp-ripple is-2 bp-from-center" cx="480" cy="118" r="14" strokeWidth="1.5" />
                </g>
                <path className="bp-line" strokeWidth="2" d="M396 58C440 58 452 118 480 118C508 118 520 58 564 58" />
                <path className="bp-marker" strokeWidth="3.5" d="M480 118L476 132L483 144L477 157L484 172L479 196" />
                <circle className="bp-anim bp-origin bp-from-center" cx="480" cy="118" r="4" />
              </g>
              <circle className="bp-marker" cx="480" cy="112" r="84" strokeWidth="2" />
            </g>
            <text className="bp-anim bp-callout-label bp-label" x="480" y="218" textAnchor="middle" fontSize="10.5">
              DETAIL A — FATIGUE ORIGIN · 5:1
            </text>

            <text className="bp-anim bp-arrow-label bp-label" x="326" y="293" textAnchor="middle" fontSize="10" letterSpacing="1">
              GENERATE
            </text>
            <path className="bp-anim bp-arrow-shaft bp-from-left bp-line" strokeWidth="1.5" d="M284 304H368" />
            <path className="bp-anim bp-arrow-head bp-ink" d="M378 304l-11-4.4v8.8z" />

            <g className="bp-anim bp-sheet-back">
              <rect className="bp-paper-back" x="400" y="252" width="196" height="136" transform="rotate(5 498 320)" />
            </g>
            <g transform="rotate(-3 486 316)">
              <g className="bp-anim bp-sheet-front">
                <rect className="bp-paper" x="388" y="246" width="196" height="140" />
                <rect className="bp-paper-head" x="388" y="246" width="196" height="26" />
                <text className="bp-paper-title" x="398" y="263" fontSize="9.5" fontWeight="700">
                  FAILURE ANALYSIS REPORT
                </text>
                <g className="bp-paper-label" fontSize="8.5" fontWeight="700">
                  <text x="398" y="290">FAILURE MODE</text>
                  <text x="398" y="320">ROOT CAUSE</text>
                  <text x="398" y="350">CORRECTIVE ACTION</text>
                </g>
                {FIELDS.map((f, i) => (
                  <rect
                    key={`${f.x}-${f.y}`}
                    className={`bp-anim bp-field is-${i + 1} bp-from-left bp-field-${f.kind}`}
                    x={f.x}
                    y={f.y}
                    width={f.w}
                    height={f.kind === 'line' ? 1 : 5}
                    rx={f.kind === 'line' ? 0 : 2}
                  />
                ))}
                <g transform="rotate(-12 522 335)">
                  <g className="bp-anim bp-stamp bp-from-center">
                    <rect className="bp-stamp-box" x="464" y="320" width="116" height="30" rx="3" strokeWidth="2.5" />
                    <text className="bp-stamp-text" x="522" y="340" textAnchor="middle" fontSize="10.5" fontWeight="700">
                      ROOT CAUSE FOUND
                    </text>
                  </g>
                </g>
              </g>
            </g>
          </g>

          {/* On submit: the GENERATE arrow flashes amber and nudges forward once. Kept outside
              the loop, and remounted by its key, so it never disturbs the loop's timing. */}
          {pulseKey > 0 && (
            <g key={pulseKey} className="bp-anim bp-generate-pulse">
              <path className="bp-generate-pulse-shaft" strokeWidth="3" strokeLinecap="round" d="M284 304H368" />
              <path d="M378 304l-11-4.4v8.8z" />
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}
