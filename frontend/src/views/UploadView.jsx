import { useEffect, useId, useRef, useState } from 'react';
import {
  ArrowRight,
  CloudUpload,
  FileSpreadsheet,
  FolderOpen,
  Table2,
  Trash2,
  Users,
  ListTree,
  ShieldCheck,
  X,
} from 'lucide-react';
import Spinner from '../components/Spinner.jsx';
import { Alert } from '../components/Feedback.jsx';
import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB } from '../api/client.js';
import { countIssues, formatFileSize, plural } from '../lib/report.js';

const REMOVE_FIRST_NOTE = 'Remove the current workbook first to upload a different one.';

export default function UploadView({
  report,
  upload,
  notice,
  onFile,
  onCancel,
  onDismissError,
  onDismissNotice,
  onContinue,
  onRemove,
}) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [note, setNote] = useState('');
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState('');
  const busy = upload.status === 'uploading' || upload.status === 'processing';
  const loaded = Boolean(report) && !busy;
  const browseRef = useRef(null);
  const proceedRef = useRef(null);
  const removeRef = useRef(null);
  const wasBusy = useRef(busy);
  const focusAfterRemove = useRef(null); // 'browse' after a removal, 'remove' after a failed one
  const fileNameId = useId();
  const fileMetaId = useId();

  // The progress panel (with its Cancel button) replaces the card's contents while
  // uploading. When it goes away, put keyboard focus on the next thing to do instead
  // of losing it to the page: Proceed after a successful upload, Browse after a
  // cancel or a failed one.
  useEffect(() => {
    if (wasBusy.current && !busy) {
      const active = document.activeElement;
      const target = report ? proceedRef.current : browseRef.current;
      if (target && (!active || active === document.body)) target.focus();
    }
    wasBusy.current = busy;
  }, [busy, report]);

  // Remove swaps the file panel for the drop area (or re-enables Remove after a
  // failure); focus follows once the new buttons are on screen.
  useEffect(() => {
    if (focusAfterRemove.current === 'browse' && !report && browseRef.current) {
      focusAfterRemove.current = null;
      browseRef.current.focus();
    } else if (focusAfterRemove.current === 'remove' && !removing && removeRef.current) {
      focusAfterRemove.current = null;
      removeRef.current.focus();
    }
  }, [report, removing]);

  function pick(files) {
    if (!files || files.length === 0) return;
    setNote(files.length > 1 ? `Only one workbook can be uploaded at a time. Using "${files[0].name}".` : '');
    onFile(files[0]);
  }

  // preventDefault on every drag over the card, even when it will not upload:
  // otherwise the browser opens the dropped file, leaving the page and discarding
  // the workbook that is open.
  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    if (busy) return;
    if (report) {
      if (event.dataTransfer.files.length > 0) setNote(REMOVE_FIRST_NOTE);
      return;
    }
    pick(event.dataTransfer.files);
  }

  function handleDragOver(event) {
    event.preventDefault();
    if (!busy && !report) setDragging(true);
  }

  async function handleRemove() {
    setRemoving(true);
    setRemoveError('');
    focusAfterRemove.current = 'browse';
    try {
      await onRemove();
      setNote('');
    } catch (err) {
      focusAfterRemove.current = 'remove';
      setRemoveError(err.message);
    } finally {
      setRemoving(false);
    }
  }

  const counts = report ? countIssues(report.issues) : null;

  return (
    <div className="view-upload">
      {/* No heading here: the title is in the top bar and the app icon in the sidebar. */}
      <p className="memory-note">
        <ShieldCheck size={16} aria-hidden="true" />
        <span>Nothing is saved in this app. Your workbook and report are cleared when you sign out or close this page.</span>
      </p>

      {notice && !busy && (
        <Alert
          tone="info"
          label="Workbook closed"
          actions={
            onDismissNotice && (
              <button type="button" className="gt-btn-secondary btn-sm" onClick={onDismissNotice}>
                Dismiss
              </button>
            )
          }
        >
          {notice}
        </Alert>
      )}

      {upload.status === 'error' && (
        <Alert
          tone="error"
          label="Upload failed"
          title={upload.fileName ? `“${upload.fileName}” was not uploaded` : undefined}
          actions={
            <button type="button" className="gt-btn-secondary btn-sm" onClick={onDismissError}>
              Dismiss
            </button>
          }
        >
          {upload.error}
        </Alert>
      )}
      {note && upload.status !== 'error' && (
        <Alert tone="info" label="Note">
          {note}
        </Alert>
      )}

      <section
        className={`dropzone ${dragging ? 'is-dragging' : ''} ${busy ? 'is-busy' : ''} ${loaded ? 'has-file' : ''}`}
        onDragOver={handleDragOver}
        onDragEnter={handleDragOver}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false);
        }}
        onDrop={handleDrop}
        aria-label={loaded ? 'Uploaded workbook' : 'Workbook upload'}
      >
        <div className="dropzone-grid" aria-hidden="true" />
        {busy ? (
          <div className="upload-progress" role="status" aria-live="polite">
            <span className="icon-tile icon-tile-glow" aria-hidden="true">
              <Spinner size={26} />
            </span>
            <div className="upload-progress-title">
              {upload.status === 'uploading' ? 'Uploading workbook…' : 'Reading sheets and checking the data…'}
            </div>
            <div className="upload-progress-file">
              {upload.fileName} · {formatFileSize(upload.fileSize)}
            </div>
            <div
              className={`progress ${upload.status === 'processing' ? 'is-indeterminate' : ''}`}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={upload.status === 'processing' ? undefined : Math.round(upload.progress * 100)}
              aria-label="Upload progress"
            >
              <span style={{ width: upload.status === 'processing' ? undefined : `${Math.round(upload.progress * 100)}%` }} />
            </div>
            <div className="upload-progress-hint">
              {upload.status === 'uploading'
                ? `${Math.round(upload.progress * 100)}% sent`
                : 'Large workbooks can take a little while.'}
            </div>
            <button type="button" className="btn-ghost" onClick={onCancel}>
              <X size={16} aria-hidden="true" /> Cancel
            </button>
          </div>
        ) : loaded ? (
          <div className="file-panel">
            <span className="icon-tile icon-tile-glow" aria-hidden="true">
              <FileSpreadsheet size={28} />
            </span>
            <div className="file-panel-label">Workbook uploaded</div>
            <div className="file-panel-name" id={fileNameId}>
              {report.source_filename}
            </div>
            <div className="file-panel-meta" id={fileMetaId}>
              {report.station || 'Station not found'} · {report.analysis_date_text || 'Date not found'} ·{' '}
              {plural(report.uoir_ids.length, 'UOIR')}
              {counts.error > 0 && (
                <>
                  {' '}
                  · <span className="file-panel-errors">{plural(counts.error, 'error')}</span>
                </>
              )}
            </div>
            <div className="file-panel-actions">
              <button
                ref={removeRef}
                type="button"
                className="gt-btn-secondary btn-lg"
                onClick={handleRemove}
                disabled={removing}
              >
                {removing ? <Spinner size={18} /> : <Trash2 size={18} aria-hidden="true" />}
                {removing ? 'Removing…' : 'Remove'}
              </button>
              <button
                ref={proceedRef}
                type="button"
                className="gt-btn-primary btn-lg"
                onClick={onContinue}
                disabled={removing}
                aria-describedby={`${fileNameId} ${fileMetaId}`}
              >
                Proceed to Review Data <ArrowRight size={18} aria-hidden="true" />
              </button>
            </div>
            {removeError && (
              <Alert tone="error" label="Not removed" className="file-panel-alert">
                {removeError}
              </Alert>
            )}
          </div>
        ) : (
          <div className="dropzone-body">
            <span className="icon-tile icon-tile-glow" aria-hidden="true">
              <CloudUpload size={28} />
            </span>
            <div className="dropzone-title">{dragging ? 'Drop the workbook to upload it' : 'Drag and drop your FMEA workbook here'}</div>
            <div className="dropzone-or">or</div>
            <button
              ref={browseRef}
              type="button"
              className="gt-btn-primary btn-lg"
              onClick={() => inputRef.current && inputRef.current.click()}
            >
              <FolderOpen size={18} aria-hidden="true" /> Browse files
            </button>
            <div className="dropzone-hint">
              Excel workbook ({ACCEPTED_EXTENSIONS.join(' or ')}), up to {MAX_UPLOAD_MB} MB
            </div>
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12"
              className="visually-hidden"
              tabIndex={-1}
              onChange={(e) => {
                pick(e.target.files);
                e.target.value = '';
              }}
            />
          </div>
        )}
      </section>

      <section className="gt-card requirements" aria-labelledby="requirements-title">
        <h2 id="requirements-title" className="card-title">
          What the workbook needs
        </h2>
        <ul className="requirement-list">
          <li>
            <span className="icon-tile icon-tile-soft" aria-hidden="true">
              <Users size={18} />
            </span>
            <div>
              <div className="requirement-title">Team Member sheet</div>
              <div className="requirement-text">Station in cell B2, Date of Analysis in B3, and the team list with No, Name, Staff No and Section.</div>
            </div>
          </li>
          <li>
            <span className="icon-tile icon-tile-soft" aria-hidden="true">
              <ListTree size={18} />
            </span>
            <div>
              <div className="requirement-title">UOIR sheet</div>
              <div className="requirement-text">One row per UOIR with UOIR ID, Title, Date of fault, Date of UOIR, CA, PA and Equipment.</div>
            </div>
          </li>
          <li>
            <span className="icon-tile icon-tile-soft" aria-hidden="true">
              <Table2 size={18} />
            </span>
            <div>
              <div className="requirement-title">One analysis tab per UOIR</div>
              <div className="requirement-text">
                Named like “UOIR ID 123 - Title of the UOIR”, with Failure Mode, Failure Effect, RecommendedStrategy, Task, Frequency,
                Trade, KKS and New Task columns.
              </div>
            </div>
          </li>
        </ul>
      </section>
    </div>
  );
}
