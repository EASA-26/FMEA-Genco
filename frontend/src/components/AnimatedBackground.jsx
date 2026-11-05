// Decorative animated background (IZ's Genco Project Theme), plain-CSS port of the
// kit's AnimatedBackground.tsx. Styles live in styles/genco-theme.css (gt-bg-*).
// - "login": drifting electric glows over a faint grid, with small pulses of light
//   running along grid lines like current on a line. For navy pages.
// - "app": two slow glows behind the page content, dark mode only. Light mode stays
//   still because any tint on gray-50 pulls gray-500 muted text below 4.5:1.
// It is hidden from screen readers, ignores the pointer, and stops moving for users
// who ask for reduced motion. Put it first inside a `position: relative;
// overflow: hidden` container and give the content after it `position: relative`.

// Grid rows (48px cells) that carry a pulse on the login page, with their timing.
const PULSES = [
  { row: 3, duration: '9s', delay: '0s' },
  { row: 8, duration: '12s', delay: '4s' },
  { row: 13, duration: '10s', delay: '7s' },
];

export default function AnimatedBackground({ variant = 'app' }) {
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
      {/* Grid lines sit at every 48px from the top, so a pulse at row * 48 rides a line. */}
      <div className="gt-bg-grid">
        {PULSES.map((p) => (
          <span
            key={p.row}
            className="gt-bg-pulse"
            style={{ top: p.row * 48, animationDuration: p.duration, animationDelay: p.delay }}
          />
        ))}
      </div>
    </div>
  );
}
