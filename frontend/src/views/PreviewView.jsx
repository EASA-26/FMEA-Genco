import { useEffect, useState } from 'react';
import { Download, ExternalLink, FileSearch, OctagonAlert, RefreshCw } from 'lucide-react';
import * as api from '../api/client.js';
import PageHeader from '../components/PageHeader.jsx';
import Spinner from '../components/Spinner.jsx';
import { Alert, EmptyState } from '../components/Feedback.jsx';
import { plural } from '../lib/report.js';

export function BlockedByErrors({ report, counts, onShowChecks, action }) {
  const errors = report.issues.filter((issue) => issue.severity === 'error');
  return (
    <section className="gt-card blocked" aria-labelledby="blocked-title">
      <span className="icon-tile icon-tile-error" aria-hidden="true">
        <OctagonAlert size={24} />
      </span>
      <div className="blocked-body">
        <div className="blocked-label">{action === 'Export' ? 'Export blocked' : 'Preview blocked'}</div>
        <h2 id="blocked-title" className="blocked-title">
          {action} is not available until {plural(counts.error, 'error')} {counts.error === 1 ? 'is' : 'are'} fixed
        </h2>
        <p className="blocked-text">Fix these in the workbook, save it and upload it again.</p>
        <ul className="blocked-list">
          {errors.slice(0, 5).map((issue, index) => (
            <li key={`${issue.code}-${index}`}>
              <OctagonAlert size={15} className="sev-error" aria-hidden="true" />
              <span>{issue.message}</span>
            </li>
          ))}
        </ul>
        {errors.length > 5 && <p className="blocked-more">and {plural(errors.length - 5, 'more error')}.</p>}
        <button type="button" className="gt-btn-primary" onClick={onShowChecks}>
          Open Data checks
        </button>
      </div>
    </section>
  );
}

export default function PreviewView({ report, counts, onShowChecks, onExport, onWorkbookClosed }) {
  const [state, setState] = useState({ phase: 'preparing', src: null, error: '' });
  const [attempt, setAttempt] = useState(0);

  // Ask the server for the PDF first, so problems show as a message rather than
  // inside the frame; then load the frame from the server's cached copy.
  useEffect(() => {
    if (!report.can_export) return undefined;
    let cancelled = false;
    setState({ phase: 'preparing', src: null, error: '' });
    (async () => {
      try {
        await api.preparePdf();
        const src = await api.previewSource();
        if (!cancelled) setState({ phase: 'loading', src, error: '' });
      } catch (err) {
        if (cancelled || (err && err.name === 'AbortError')) return;
        // The server no longer holds this workbook (signed out, refreshed, another tab).
        if (api.isWorkbookClosed(err) && onWorkbookClosed) {
          onWorkbookClosed();
          return;
        }
        setState({ phase: 'error', src: null, error: err.message || 'The preview could not be created.' });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [report, attempt, onWorkbookClosed]);

  // Not every browser reports when a PDF frame has loaded; never leave the spinner up for good.
  useEffect(() => {
    if (state.phase !== 'loading') return undefined;
    const timer = setTimeout(() => setState((s) => (s.phase === 'loading' ? { ...s, phase: 'ready' } : s)), 12000);
    return () => clearTimeout(timer);
  }, [state.phase]);

  const header = (
    <PageHeader
      eyebrow="Step 3 · Preview Report"
      title="Preview report"
      actions={
        report.can_export && (
          <>
            <button type="button" className="btn-ghost" onClick={() => setAttempt((n) => n + 1)} disabled={state.phase === 'preparing'}>
              <RefreshCw size={16} aria-hidden="true" /> Reload
            </button>
            {state.src && (
              <a className="gt-btn-secondary" href={state.src} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={16} aria-hidden="true" /> Open in new tab
              </a>
            )}
            <button type="button" className="gt-btn-primary" onClick={onExport}>
              <Download size={16} aria-hidden="true" /> Export PDF
            </button>
          </>
        )
      }
    >
      The PDF exactly as it will be exported: {report.pdf_filename}
    </PageHeader>
  );

  if (!report.can_export) {
    return (
      <div className="view-preview">
        {header}
        <BlockedByErrors report={report} counts={counts} onShowChecks={onShowChecks} action="The preview" />
      </div>
    );
  }

  return (
    <div className="view-preview">
      {header}
      {state.phase === 'error' ? (
        <Alert
          tone="error"
          label="Preview failed"
          title="The preview could not be shown"
          actions={
            <button type="button" className="gt-btn-secondary btn-sm" onClick={() => setAttempt((n) => n + 1)}>
              <RefreshCw size={15} aria-hidden="true" /> Try again
            </button>
          }
        >
          {state.error}
        </Alert>
      ) : (
        <div className="pdf-frame">
          {state.src && (
            <iframe
              key={`${attempt}-${state.src}`}
              title={`PDF preview of ${report.pdf_filename}`}
              src={state.src}
              onLoad={() => setState((s) => (s.phase === 'loading' ? { ...s, phase: 'ready' } : s))}
            />
          )}
          {state.phase !== 'ready' && (
            <div className="pdf-overlay" role="status" aria-live="polite">
              {state.phase === 'preparing' ? (
                <EmptyState icon={FileSearch} title="Preparing the PDF…">
                  <span className="inline-spinner">
                    <Spinner size={16} /> Building every page from your workbook. This can take a few seconds.
                  </span>
                </EmptyState>
              ) : (
                <EmptyState icon={FileSearch} title="Opening the preview…">
                  <span className="inline-spinner">
                    <Spinner size={16} /> Almost there.
                  </span>
                </EmptyState>
              )}
            </div>
          )}
        </div>
      )}
      {state.phase !== 'error' && (
        <p className="preview-hint">
          If the preview stays blank, your browser may not show PDFs inside the page. Use “Open in new tab” or Export PDF instead.
        </p>
      )}
    </div>
  );
}
