import { CircleCheck, Upload } from 'lucide-react';

// Shown after Finish on Export PDF: the workbook and report are already discarded
// (one-time use). The engineer stays signed in and can start the next report here.
// The title "Report complete" is in the top bar (the page's only h1), and the
// workspace moves keyboard focus there when this screen opens, so the card has no
// heading of its own.
export default function CompleteView({ onStartNew }) {
  return (
    <div className="complete">
      <section className="gt-card complete-card" aria-label="Report complete">
        <span className="gt-icon-tile complete-icon" aria-hidden="true">
          <CircleCheck size={24} />
        </span>
        {/* The top bar's subtitle already says the workbook and report were cleared. */}
        <p className="complete-text">Upload the next workbook whenever you&apos;re ready.</p>
        <button type="button" className="gt-btn-primary complete-action" onClick={onStartNew}>
          <Upload size={18} aria-hidden="true" />
          Start a new report
        </button>
      </section>
    </div>
  );
}
