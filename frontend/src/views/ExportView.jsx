import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, CircleCheck, ClipboardList, Download, Factory, Mail, RefreshCw, Upload, Wrench } from 'lucide-react';
import * as api from '../api/client.js';
import StepNav from '../components/StepNav.jsx';
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
 * "Email the PDF" (optional). Two ways, chosen by what this computer offers:
 * - Outlook draft (features.outlook_email): the server opens a new classic-Outlook email
 *   with the PDF attached.
 * - Mail app (new Outlook, or the app is not on this PC): the browser opens a new email
 *   in the default mail app with recipients, subject and text filled in, and downloads
 *   the PDF. A mail link cannot attach files, so the user attaches the PDF by hand.
 * Nothing is sent from here; the user checks the email and presses Send.
 * onWorking(busy) and onDelivered() let the page know, for its Finish / Upload another guard.
 * `locked`: the report is being cleared (Finish / Upload another), so nothing new starts.
 */
function EmailCard({ report, outlookDraft, locked, onWorkbookClosed, onWorking, onDelivered }) {
  const [to, setTo] = useState('');
  const [state, setState] = useState(EMAIL_IDLE);
  const inputRef = useRef(null);
  const working = state.phase === 'working';
  const hasText = to.trim() !== '';

  useEffect(() => {
    onWorking(working);
  }, [working, onWorking]);

  function checkedRecipients() {
    const { recipients, error } = parseRecipients(to, { required: true });
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
      onDelivered();
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
      onDelivered();
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
    if (working || locked || !hasText) return;
    const recipients = checkedRecipients();
    if (recipients === null) return;
    if (outlookDraft) sendWithOutlook(recipients);
    else sendWithMailApp(recipients);
  }

  function handleMailAppInstead() {
    if (working || locked) return;
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
            Email the PDF <span className="card-title-optional">(optional)</span>
          </h2>
          <p className="card-meta">
            {outlookDraft
              ? 'Opens a new email in Outlook with the PDF attached and the recipients filled in. Nothing is sent until you press Send in Outlook.'
              : "This computer can't attach the PDF to a new email automatically. The PDF is downloaded and a new email opens with the recipients filled in; attach the PDF, then press Send."}
          </p>
        </div>
      </div>

      <form className="export-email-form" onSubmit={handleSubmit} noValidate>
        <div className="field">
          <label className="gt-label" htmlFor="email-to">
            Recipients
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
            readOnly={working || locked}
            aria-invalid={state.invalid || undefined}
            aria-describedby={describedBy}
          />
          {/* Also says why the button below stays disabled while the box is empty
              (a disabled button cannot take focus, so the hint lives on the field). */}
          <span id="email-to-hint" className="field-hint">
            Enter at least one address to send. Separate several with a semicolon.
          </span>
        </div>

        <div className="export-actions">
          {/* Disabled until something is typed: there is nobody to send to yet. */}
          <button type="submit" className="gt-btn-secondary" disabled={working || locked || !hasText}>
            {working ? (
              <>
                <Spinner size={16} /> {workingText}
              </>
            ) : outlookDraft ? (
              <>
                <Mail size={16} aria-hidden="true" /> Send via Outlook
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
              Outlook opened a new email with {report.pdf_filename} attached. Check it, then press Send in Outlook.
            </Alert>
          )}
          {state.phase === 'doneMailApp' && (
            <Alert tone="success" label="Email opened">
              A new email opened in your mail app and {report.pdf_filename} was saved to your Downloads folder. The PDF is
              not attached yet: attach it to the email, then press Send.
            </Alert>
          )}
          {state.phase === 'error' && (
            <Alert
              id="email-error"
              tone="error"
              label="Email not opened"
              actions={
                state.offerMailApp ? (
                  <button type="button" className="gt-btn-secondary" onClick={handleMailAppInstead} disabled={locked}>
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

const LEAVE_ACTIONS = {
  finish: { label: 'Finish', anyway: 'Finish anyway', working: 'Finishing…' },
  upload: { label: 'Upload another', anyway: 'Upload another anyway', working: 'Clearing the report…' },
};

/**
 * "Upload another" and "Finish" at the bottom of the page. Both clear the report for good,
 * so if the PDF was neither downloaded nor emailed yet, the first click asks first.
 * With blocking errors there is no PDF to lose, so Upload another acts straight away and
 * Finish is not offered (there is no finished report to complete).
 * `leaving` ('finish' | 'upload' | null) is kept by the page, which locks its other
 * buttons while the report is being cleared.
 */
function FinishRow({ askFirst, busy, leaving, setLeaving, showFinish, onUploadAnother, onFinish, onWorkbookClosed }) {
  const [confirming, setConfirming] = useState(null);
  const [error, setError] = useState('');
  // After a failed clear, focus goes back to the button of that action once it is
  // enabled again (the "anyway" button that had focus has gone with the warning).
  const [refocus, setRefocus] = useState(null);
  const anywayRef = useRef(null);
  const buttonRefs = { upload: useRef(null), finish: useRef(null) };

  // The warning is only about a PDF not yet saved: it goes once the PDF is downloaded or emailed.
  useEffect(() => {
    if (!askFirst) setConfirming(null);
  }, [askFirst]);

  useEffect(() => {
    if (!refocus || leaving) return;
    const button = buttonRefs[refocus] && buttonRefs[refocus].current;
    if (button) button.focus();
    setRefocus(null);
  }, [refocus, leaving]); // eslint-disable-line react-hooks/exhaustive-deps -- refs are stable

  // Keyboard and screen-reader users land on the choice the warning asks for.
  useEffect(() => {
    if (confirming && anywayRef.current) anywayRef.current.focus();
  }, [confirming]);

  async function leave(action) {
    setConfirming(null);
    setError('');
    setLeaving(action);
    try {
      await (action === 'finish' ? onFinish() : onUploadAnother());
      setLeaving(null);
    } catch (err) {
      // The server no longer holds this workbook (signed out, refreshed, another tab).
      if (api.isWorkbookClosed(err) && onWorkbookClosed) {
        onWorkbookClosed();
        return;
      }
      setLeaving(null);
      setError(err.message || 'The report could not be cleared. Please try again.');
      setRefocus(action);
    }
  }

  function handleClick(action) {
    if (leaving) return;
    if (askFirst) {
      setError('');
      setConfirming(action);
      return;
    }
    leave(action);
  }

  /** Close the warning and give focus back to the button that opened it. */
  function cancel() {
    const button = buttonRefs[confirming] && buttonRefs[confirming].current;
    setConfirming(null);
    if (button) button.focus();
  }

  const disabled = Boolean(leaving) || busy;

  function buttonContent(action, Icon) {
    if (leaving === action) {
      return (
        <>
          <Spinner size={16} /> {LEAVE_ACTIONS[action].working}
        </>
      );
    }
    return (
      <>
        <Icon size={18} aria-hidden="true" /> {LEAVE_ACTIONS[action].label}
      </>
    );
  }

  return (
    <div className="export-finish">
      <div className="export-finish-status" aria-live="polite">
        {leaving && <span className="visually-hidden">{LEAVE_ACTIONS[leaving].working}</span>}
        {confirming && (
          <Alert
            tone="warning"
            label="Not saved yet"
            actions={
              <>
                <button
                  ref={anywayRef}
                  type="button"
                  className="gt-btn-primary btn-sm"
                  onClick={() => leave(confirming)}
                  disabled={busy}
                  aria-describedby="finish-warning-text"
                >
                  {LEAVE_ACTIONS[confirming].anyway}
                </button>
                <button type="button" className="gt-btn-secondary btn-sm" onClick={cancel}>
                  Cancel
                </button>
              </>
            }
          >
            <span id="finish-warning-text">
              The PDF hasn&apos;t been downloaded or emailed yet. When you continue, the report is cleared and can&apos;t be
              opened again.
            </span>
          </Alert>
        )}
        {error && (
          <Alert tone="error" label="Not cleared">
            {error}
          </Alert>
        )}
      </div>
      <div className="export-finish-actions">
        <button
          ref={buttonRefs.upload}
          type="button"
          className="gt-btn-secondary"
          onClick={() => handleClick('upload')}
          disabled={disabled}
        >
          {buttonContent('upload', Upload)}
        </button>
        {showFinish && (
          <button
            ref={buttonRefs.finish}
            type="button"
            className="gt-btn-primary"
            onClick={() => handleClick('finish')}
            disabled={disabled}
          >
            {buttonContent('finish', CircleCheck)}
          </button>
        )}
      </div>
    </div>
  );
}

// `delivered` (the PDF was downloaded or an email opened for this report) is kept by the
// workspace, so it survives going Back to Preview and Next again; onDelivered sets it.
export default function ExportView({
  report,
  counts,
  features,
  delivered,
  onDelivered,
  onShowChecks,
  onBack,
  onWorkbookClosed,
  onUploadAnother,
  onFinish,
}) {
  const [state, setState] = useState({ phase: 'idle', error: '' });
  const [emailWorking, setEmailWorking] = useState(false);
  // Finish / Upload another in progress: nothing else may start while the report is cleared.
  const [leaving, setLeaving] = useState(null);
  const mounted = useRef(true);
  const outlookEmail = Boolean(features && features.outlook_email);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // A request that was still running when Finish / Upload another cleared the report
  // comes back "workbook closed"; by then this page is gone and the workspace has
  // already moved on, so only a page still on screen reports it.
  const workbookClosedIfShown = useCallback(() => {
    if (mounted.current && onWorkbookClosed) onWorkbookClosed();
  }, [onWorkbookClosed]);

  async function download() {
    if (leaving) return;
    setState({ phase: 'working', error: '' });
    try {
      await api.downloadPdf(report.pdf_filename);
      setState({ phase: 'done', error: '' });
      onDelivered();
    } catch (err) {
      // The server no longer holds this workbook (signed out, refreshed, another tab).
      if (api.isWorkbookClosed(err)) {
        workbookClosedIfShown();
        return;
      }
      setState({ phase: 'error', error: err.message || 'The PDF could not be downloaded. Please try again.' });
    }
  }

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
      {/* The title and subtitle are in the top bar; this row holds the page's buttons only. */}
      <div className="page-actions">
        <StepNav back={{ label: 'Preview Report', onClick: onBack, disabled: Boolean(leaving) }} />
      </div>

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
                <button
                  type="button"
                  className="gt-btn-primary btn-lg"
                  onClick={download}
                  disabled={state.phase === 'working' || Boolean(leaving)}
                >
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
              </div>
            </section>

            <EmailCard
              report={report}
              outlookDraft={outlookEmail}
              locked={Boolean(leaving)}
              onWorkbookClosed={workbookClosedIfShown}
              onWorking={setEmailWorking}
              onDelivered={onDelivered}
            />
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

      <FinishRow
        askFirst={report.can_export && !delivered}
        busy={state.phase === 'working' || emailWorking}
        leaving={leaving}
        setLeaving={setLeaving}
        showFinish={report.can_export}
        onUploadAnother={onUploadAnother}
        onFinish={onFinish}
        onWorkbookClosed={workbookClosedIfShown}
      />
    </div>
  );
}
