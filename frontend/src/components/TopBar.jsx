import { CircleCheck, Download, FileSpreadsheet, Lock, Menu, OctagonAlert, TriangleAlert, Upload } from 'lucide-react';
import { plural } from '../lib/report.js';

export default function TopBar({ report, counts, uploadBusy, onMenu, onShowChecks, onUploadAnother, onExport }) {
  let exportReason = '';
  if (!report) exportReason = 'Upload a workbook first';
  else if (counts.error) exportReason = `Fix ${plural(counts.error, 'error')} to export`;
  else if (uploadBusy) exportReason = 'Wait for the upload to finish';
  const exportDisabled = Boolean(exportReason);
  // Station and date can be long; the full text stays available on hover when it is cut off.
  const fileMeta = report
    ? [report.station, report.analysis_date_text].filter(Boolean).join(' · ') || 'Station and date not found'
    : '';

  return (
    <header className="topbar">
      <button type="button" className="icon-btn topbar-menu" onClick={onMenu} aria-label="Open menu">
        <Menu size={20} />
      </button>

      <div className="topbar-file">
        <span className="file-icon" aria-hidden="true">
          <FileSpreadsheet size={18} />
        </span>
        {report ? (
          <div className="topbar-file-text">
            <div className="topbar-file-name" title={report.source_filename}>
              {report.source_filename}
            </div>
            <div className="topbar-file-meta" title={fileMeta}>
              {fileMeta}
            </div>
          </div>
        ) : (
          <div className="topbar-file-text">
            <div className="topbar-file-name">No workbook uploaded</div>
            <div className="topbar-file-meta">Upload a workbook to begin</div>
          </div>
        )}
      </div>

      {report && (
        <div className="topbar-chips" aria-label="Data check status">
          {counts.error > 0 && (
            <button type="button" className="chip chip-error" onClick={onShowChecks}>
              <OctagonAlert size={15} aria-hidden="true" />
              {plural(counts.error, 'error')}
            </button>
          )}
          {counts.warning > 0 && (
            <button type="button" className="chip chip-warning" onClick={onShowChecks}>
              <TriangleAlert size={15} aria-hidden="true" />
              {plural(counts.warning, 'warning')}
            </button>
          )}
          {counts.error === 0 && (
            <button type="button" className="chip chip-ok" onClick={onShowChecks}>
              <CircleCheck size={15} aria-hidden="true" />
              Ready to export
            </button>
          )}
        </div>
      )}

      <div className="topbar-actions">
        {report && (
          <button type="button" className="btn btn-secondary" onClick={onUploadAnother} disabled={uploadBusy}>
            <Upload size={16} aria-hidden="true" />
            Upload another
          </button>
        )}
        <div className="export-cta">
          {exportDisabled && (
            <span id="export-reason" className={`export-reason ${counts.error ? 'is-error' : ''}`}>
              {exportReason}
            </span>
          )}
          <button
            type="button"
            className="btn btn-primary btn-export"
            onClick={onExport}
            disabled={exportDisabled}
            aria-describedby={exportDisabled ? 'export-reason' : undefined}
          >
            {exportDisabled ? <Lock size={16} aria-hidden="true" /> : <Download size={16} aria-hidden="true" />}
            Export PDF
          </button>
        </div>
      </div>
    </header>
  );
}
