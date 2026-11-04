import GaugeMotif from './GaugeMotif.jsx';
import logoUrl from '../assets/tnb-genco-logo.png';

// HTML rendition of the approved PDF cover (design-preview/front_page_preview.py).
// Every size is expressed in PDF points through the --pt custom property, so the
// page keeps the A4 proportions of the printed cover at any width.
export default function CoverPage({ station, analysisDate }) {
  return (
    <div className="cover-frame">
      <article className="cover" aria-label="Front page preview">
        <svg className="cover-bg" viewBox="0 0 595 842" preserveAspectRatio="none" aria-hidden="true" focusable="false">
          <defs>
            <linearGradient id="cover-gradient" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="595" y2="842">
              <stop offset="0" stopColor="#1A5A9A" />
              <stop offset="0.5" stopColor="#2379B3" />
              <stop offset="1" stopColor="#52BAD8" />
            </linearGradient>
          </defs>
          <rect width="595" height="842" fill="url(#cover-gradient)" />
        </svg>
        <GaugeMotif className="cover-motif" />

        <div className="cover-brand">
          <span className="cover-pulse" aria-hidden="true">
            <svg viewBox="0 0 30 30">
              <polyline
                points="5,15 10.5,15 13,9.5 16.5,21.5 19.5,15 25,15"
                fill="none"
                stroke="#fff"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <span className="cover-brand-line">ALCM - Maintenance Strategy</span>
        </div>

        <div className="cover-logo">
          <img src={logoUrl} alt="TNB GENCO" />
        </div>

        <h2 className="cover-title">
          <span>Failure Mode Effect</span>
          <span>Analysis (FMEA)</span>
          <span>Report</span>
        </h2>

        <dl className="cover-details">
          <dt>Station</dt>
          <dd className="cover-colon" aria-hidden="true">
            :
          </dd>
          <dd className="cover-value">{station}</dd>
          <dt>Date of Analysis</dt>
          <dd className="cover-colon" aria-hidden="true">
            :
          </dd>
          <dd className="cover-value">{analysisDate}</dd>
        </dl>

        <div className="cover-signatures">
          {['PREPARED BY:', 'APPROVED BY:'].map((label) => (
            <div key={label} className="cover-sign">
              <div className="cover-sign-label">{label}</div>
              <div className="cover-sign-rule" />
            </div>
          ))}
        </div>
      </article>
    </div>
  );
}
