import { useEffect, useRef, useState } from 'react';
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
import PageHeader from '../components/PageHeader.jsx';
import AppIcon from '../components/AppIcon';
import Spinner from '../components/Spinner.jsx';
import { Alert } from '../components/Feedback.jsx';
import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB } from '../api/client.js';
import { countIssues, formatDateTime, formatFileSize, plural } from '../lib/report.js';

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
  const browseRef = useRef(null);
  const wasBusy = useRef(busy);

  // The progress panel (with its Cancel button) replaces the Browse button while
  // uploading. When it goes away after a cancel or a failed upload, put keyboard
  // focus back on Browse instead of losing it to the page.
  useEffect(() => {
    if (wasBusy.current && !busy && browseRef.current) {
      const active = document.activeElement;
      if (!active || active === document.body) browseRef.current.focus();
    }
    wasBusy.current = busy;
  }, [busy]);

  function pick(files) {
    if (!files || files.length === 0) return;
    setNote(files.length > 1 ? `Only one workbook can be uploaded at a time. Using "${files[0].name}".` : '');
    onFile(files[0]);
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    if (busy) return;
    pick(event.dataTransfer.files);
  }

  function handleDragOver(event) {
    event.preventDefault();
    if (!busy) setDragging(true);
  }

  async function handleRemove() {
    setRemoving(true);
    setRemoveError('');
    try {
      await onRemove();
    } catch (err) {
      setRemoveError(err.message);
      setRemoving(false);
    }
  }

  const counts = report ? countIssues(report.issues) : null;

  return (
    <div className="view-upload">
      <PageHeader
        eyebrow="Step 1 · Upload Excel"
        title={report ? 'Upload another workbook' : 'Upload the FMEA workbook'}
        icon={<AppIcon app="fmea" className="gt-app-icon" />}
      >
        The workbook is read and checked straight away. Nothing is changed in your file, and macros are never run.
      </PageHeader>

      <p className="memory-note">
        <ShieldCheck size={16} aria-hidden="true" />
        <span>
          Your workbook is read in memory only and never saved. It is discarded, with its report and PDF, when you sign out or
          leave the page.
        </span>
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

      {report && !busy && (
        <section className="gt-card current-file" aria-label="Current workbook">
          <span className="gt-icon-tile" aria-hidden="true">
            <FileSpreadsheet size={22} />
          </span>
          <div className="current-file-text">
            <div className="current-file-label">Current workbook</div>
            <div className="current-file-name">{report.source_filename}</div>
            <div className="current-file-meta">
              {report.station || 'Station not found'} · {report.analysis_date_text || 'Date not found'} ·{' '}
              {plural(report.uoirs.length, 'UOIR')} · read {formatDateTime(report.generated_at)}
              {counts.error > 0 && <> · {plural(counts.error, 'error')}</>}
            </div>
          </div>
          <div className="current-file-actions">
            <button type="button" className="btn-ghost" onClick={handleRemove} disabled={removing}>
              {removing ? <Spinner size={16} /> : <Trash2 size={16} aria-hidden="true" />}
              Remove
            </button>
            <button type="button" className="gt-btn-primary" onClick={onContinue}>
              Continue reviewing <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </section>
      )}
      {removeError && (
        <Alert tone="error" label="Not removed">
          {removeError}
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
        className={`dropzone ${dragging ? 'is-dragging' : ''} ${busy ? 'is-busy' : ''}`}
        onDragOver={handleDragOver}
        onDragEnter={handleDragOver}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false);
        }}
        onDrop={handleDrop}
        aria-label="Workbook upload"
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
