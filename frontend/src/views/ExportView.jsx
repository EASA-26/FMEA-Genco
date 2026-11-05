import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, CircleCheck, ClipboardList, Download, Eye, Factory, Mail, RefreshCw, Wrench } from 'lucide-react';
import * as api from '../api/client.js';
import PageHeader from '../components/PageHeader.jsx';
import Spinner from '../components/Spinner.jsx';
import { Alert } from '../components/Feedback.jsx';
import { BlockedByErrors } from './PreviewView.jsx';
import { plural } from '../lib/report.js';
import { MAX_RECIPIENTS_TEXT, mailtoLink, parseRecipients, recipientsText } from '../lib/email.js';

const EMAIL_IDLE = { phase: 'idle', error: '', invalid: false, offerMailApp: false };

/** Open a mailto: link in the default mail app. Called straight from a click, so the
 * browser treats it as the user's own action. */
function openMailApp(link) {
  const anchor = document.createElement('a');
  anchor.href = link;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

/**
 * "Email the PDF". Two ways, chosen by what this computer offers:
 * - Outlook draft (features.outlook_email): the server opens a new classic-Outlook email
 *   with the PDF attached.
 * - Mail app (new Outlook, or the app is not on this PC): the browser opens a new email
 *   in the default mail app with recipients, subject and text filled in, and downloads
 *   the PDF for the user to attach.
 * Nothing is sent from here; the user checks the email and presses Send.
 */
function EmailCard({ report, outlookDraft, onWorkbookClosed }) {
  const [to, setTo] = useState('');
  const [state, setState] = useState(EMAIL_IDLE);
  const inputRef = useRef(null);
  const working = state.phase === 'working';

  function checkedRecipients() {
    const { recipients, error } = parseRecipients(to);
    if (error) {
      setState({ ...EMAIL_IDLE, phase: 'error', error, invalid: true });
      if (inputRef.current) inputRef.current.focus();
      return null;
    }
    return recipients;
  }

  function handleWorkbookClosed(err) {
    if (api.isWorkbookClosed(err) && onWorkbookClosed) {
      onWorkbookClosed();
      return true;
    }
    return false;
  }

  async function sendWithMailApp(recipients) {
    // Open the email first, while this still counts as the user's click; then download.
    openMailApp(mailtoLink(recipients, report.station, report.analysis_date_text));
    setState({ ...EMAIL_IDLE, phase: 'working' });
    try {
      await api.downloadPdf(report.pdf_filename);
      setState({ ...EMAIL_IDLE, phase: 'doneMailApp' });
    } catch (err) {
      if (handleWorkbookClosed(err)) return;
      setState({
        ...EMAIL_IDLE,
        phase: 'error',
        error: err.message || 'The PDF could not be downloaded. Please try again.',
      });
    }
  }

  async function sendWithOutlook(recipients) {
    setState({ ...EMAIL_IDLE, phase: 'working' });
    try {
      await api.emailPdf(recipientsText(recipients));
      setState({ ...EMAIL_IDLE, phase: 'done' });
    } catch (err) {
      if (handleWorkbookClosed(err)) return;
      const status = err instanceof api.ApiError ? err.status : 0;
      setState({
        ...EMAIL_IDLE,
        phase: 'error',
        error: err.message || 'Outlook could not open a new email.',
        invalid: status === 400,
        // Outlook could not do it (failed, or not available after all): offer the mail app.
        offerMailApp: status === 502 || status === 501,
      });
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (working) return;
    const recipients = checkedRecipients();
    if (recipients === null) return;
    if (outlookDraft) sendWithOutlook(recipients);
    else sendWithMailApp(recipients);
  }

  function handleMailAppInstead() {
    if (working) return;
    const recipients = checkedRecipients();
    if (recipients !== null) sendWithMailApp(recipients);
  }

  function handleChange(event) {
    setTo(event.target.value);
    // A result or message about the previous recipients no longer applies.
    if (state.phase !== 'idle' && state.phase !== 'working') setState(EMAIL_IDLE);
  }

  const describedBy = state.phase === 'error' ? 'email-to-hint email-error' : 'email-to-hint';
  const workingText = outlookDraft ? 'Opening Outlook…' : 'Downloading PDF…';

  return (
    <section className="gt-card export-email" aria-labelledby="email-title">
      <div className="export-email-head">
        <span className="icon-tile icon-tile-soft" aria-hidden="true">
          <Mail size={18} />
        </span>
        <div className="export-email-head-text">
          <h2 id="email-title" className="card-title">
            Email the PDF
          </h2>
          <p className="card-meta">
            {outlookDraft
              ? 'Opens a new email in Outlook on this computer with the PDF attached. Nothing is sent until you press Send in Outlook.'
              : 'Opens a new email in your mail app with the recipients and subject filled in, and downloads the PDF for you to attach. Nothing is sent until you press Send.'}
          </p>
        </div>
      </div>

      <form className="export-email-form" onSubmit={handleSubmit} noValidate>
        <div className="field">
          <label className="gt-label" htmlFor="email-to">
            Recipients (optional)
          </label>
          <input
            ref={inputRef}
            id="email-to"
            name="email-to"
            className="gt-input"
            type="text"
            inputMode="email"
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            maxLength={MAX_RECIPIENTS_TEXT}
            value={to}
            onChange={handleChange}
            readOnly={working}
            aria-invalid={state.invalid || undefined}
            aria-describedby={describedBy}
          />
          <span id="email-to-hint" className="field-hint">
            {outlookDraft
              ? 'Separate several addresses with a semicolon. Leave empty to choose recipients in Outlook.'
              : 'Separate several addresses with a semicolon. Leave empty to choose recipients in your mail app.'}
          </span>
        </div>

        <div className="export-actions">
          <button type="submit" className="gt-btn-secondary" disabled={working}>
            {working ? (
              <>
                <Spinner size={16} /> {workingText}
              </>
            ) : outlookDraft ? (
              <>
                <Mail size={16} aria-hidden="true" /> Open in Outlook
              </>
            ) : (
              <>
                <Mail size={16} aria-hidden="true" /> Download PDF &amp; open email
              </>
            )}
          </button>
        </div>

        <div className="export-email-status" aria-live="polite">
          {working && <span className="visually-hidden">{workingText}</span>}
          {state.phase === 'done' && (
            <Alert tone="success" label="Email ready">
              Outlook opened a new email with the PDF attached. Check it, then press Send in Outlook.
            </Alert>
          )}
          {state.phase === 'doneMailApp' && (
            <Alert tone="success" label="Email opened">
              A new email was opened in your mail app and {report.pdf_filename} was saved to your Downloads folder. Attach
              the PDF to the email, then press Send.
            </Alert>
          )}
          {state.phase === 'error' && (
            <Alert
              id="email-error"
              tone="error"
              label="Email not opened"
              actions={
                state.offerMailApp ? (
                  <button type="button" className="gt-btn-secondary" onClick={handleMailAppInstead}>
                    <Mail size={16} aria-hidden="true" /> Download PDF &amp; open email instead
                  </button>
                ) : null
              }
            >
              {state.error}
            </Alert>
          )}
        </div>
      </form>
    </section>
  );
}

export default function ExportView({
  report,
  counts,
  features,
  autoStart,
  onAutoStartDone,
  onShowChecks,
  onPreview,
  onWorkbookClosed,
}) {
  const [state, setState] = useState({ phase: 'idle', error: '' });
  const autoStarted = useRef(false);
  const outlookEmail = Boolean(features && features.outlook_email);

  const download = useCallback(async () => {
    setState({ phase: 'working', error: '' });
    try {
      await api.downloadPdf(report.pdf_filename);
      setState({ phase: 'done', error: '' });
    } catch (err) {
      // The server no longer holds this workbook (signed out, refreshed, another tab).
      if (api.isWorkbookClosed(err) && onWorkbookClosed) {
        onWorkbookClosed();
        return;
      }
      setState({ phase: 'error', error: err.message || 'The PDF could not be downloaded. Please try again.' });
    }
  }, [report, onWorkbookClosed]);

  // "Export PDF" in the top bar opens this step and starts the download once.
  useEffect(() => {
    if (!autoStart) {
      autoStarted.current = false;
      return;
    }
    if (autoStarted.current) return;
    autoStarted.current = true;
    onAutoStartDone();
    if (report.can_export) download();
  }, [autoStart, onAutoStartDone, report, download]);

  const contents = [
    { icon: Factory, title: 'Front Page', text: `${report.station || 'Station'} · ${report.analysis_date_text || 'Date of Analysis'}` },
    {
      icon: ClipboardList,
      title: 'Introduction',
      text: `Failure Details (${plural(report.failure_details.length, 'row')}) and Team Members (${report.team.length})`,
    },
    {
      icon: Activity,
      title: 'Analysis',
      text: `${plural(report.uoirs.length, 'UOIR')}: FMEA Analysis on A3 landscape and FMEA Summary on A4`,
    },
    { icon: Wrench, title: 'Recommendation', text: 'Tasks grouped by Equipment and KKS for every UOIR' },
  ];

  return (
    <div className="view-export">
      <PageHeader eyebrow="Step 4 · Export PDF" title="Export PDF">
        Download the finished report to share, print or sign, or email it.
      </PageHeader>

      {!report.can_export ? (
        <BlockedByErrors report={report} counts={counts} onShowChecks={onShowChecks} action="Export" />
      ) : (
        <div className="export-layout">
          <div className="export-main">
            <section className="gt-card export-card" aria-labelledby="export-title">
              <div className="export-file">
                <span className="pdf-badge" aria-hidden="true">
                  PDF
                </span>
                <div className="export-file-text">
                  <h2 id="export-title" className="export-file-name">
                    {report.pdf_filename}
                  </h2>
                  <div className="export-file-meta">Failure Mode Effect Analysis (FMEA) Report</div>
                </div>
              </div>

              {state.phase === 'error' && (
                <Alert tone="error" label="Download failed">
                  {state.error}
                </Alert>
              )}
              {state.phase === 'done' && (
                <Alert tone="success" label="Downloaded">
                  The PDF was saved by your browser. Check your Downloads folder.
                </Alert>
              )}
              {counts.warning > 0 && state.phase !== 'done' && (
                <Alert tone="warning" label="Please check">
                  {plural(counts.warning, 'warning')} did not block the export. Make sure the report reads correctly before sharing it.
                </Alert>
              )}

              <div className="export-actions">
                <button type="button" className="gt-btn-primary btn-lg" onClick={download} disabled={state.phase === 'working'}>
                  {state.phase === 'working' ? (
                    <>
                      <Spinner size={18} /> Preparing PDF…
                    </>
                  ) : state.phase === 'error' ? (
                    <>
                      <RefreshCw size={18} aria-hidden="true" /> Try again
                    </>
                  ) : (
                    <>
                      <Download size={18} aria-hidden="true" /> {state.phase === 'done' ? 'Download again' : 'Download PDF'}
                    </>
                  )}
                </button>
                <button type="button" className="gt-btn-secondary btn-lg" onClick={onPreview}>
                  <Eye size={18} aria-hidden="true" /> Preview first
                </button>
              </div>
            </section>

            <EmailCard report={report} outlookDraft={outlookEmail} onWorkbookClosed={onWorkbookClosed} />
          </div>

          <section className="gt-card export-contents" aria-labelledby="contents-title">
            <h2 id="contents-title" className="card-title">
              In this report
            </h2>
            <ol className="contents-list">
              {contents.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.title}>
                    <span className="icon-tile icon-tile-soft" aria-hidden="true">
                      <Icon size={17} />
                    </span>
                    <div>
                      <div className="contents-title">{item.title}</div>
                      <div className="contents-text">{item.text}</div>
                    </div>
                    <CircleCheck size={17} className="contents-check" aria-hidden="true" />
                  </li>
                );
              })}
            </ol>
          </section>
        </div>
      )}
    </div>
  );
}
