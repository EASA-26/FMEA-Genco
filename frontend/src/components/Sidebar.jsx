import {
  BookOpen,
  Check,
  ClipboardCheck,
  FileText,
  Lock,
  LogOut,
  OctagonAlert,
  Table2,
  TriangleAlert,
  Wrench,
  X,
} from 'lucide-react';
import PulseMark from './PulseMark.jsx';
import { issuesForUoir, countIssues, plural } from '../lib/report.js';

const STEPS = [
  { id: 'upload', label: 'Upload Excel' },
  { id: 'review', label: 'Review Data' },
  { id: 'preview', label: 'Preview Report' },
  { id: 'export', label: 'Export PDF' },
];

const SECTIONS = [
  { id: 'checks', label: 'Data Checks', icon: ClipboardCheck },
  { id: 'front', label: 'Front Page', icon: FileText },
  { id: 'intro', label: 'Introduction', icon: BookOpen },
  { id: 'analysis', label: 'Analysis', icon: Table2 },
  { id: 'recommendation', label: 'Recommendation', icon: Wrench },
];

function stepDetail(step, report, counts, uploadBusy) {
  if (step === 'upload') {
    if (uploadBusy) return { text: 'Reading workbook…' };
    return { text: report ? report.source_filename : 'Choose a workbook' };
  }
  if (!report) return { text: 'Waiting for a workbook' };
  if (step === 'review') {
    const parts = [plural(report.uoirs.length, 'UOIR')];
    if (counts.error) parts.push(plural(counts.error, 'error'));
    else if (counts.warning) parts.push(plural(counts.warning, 'warning'));
    return { text: parts.join(' · ') };
  }
  if (counts.error) return { text: `Blocked by ${plural(counts.error, 'error')}`, blocked: true };
  return { text: step === 'preview' ? 'See the PDF as it will print' : report.pdf_filename };
}

export default function Sidebar({
  report,
  counts,
  nav,
  uoirId,
  user,
  authMode,
  uploadBusy,
  onStep,
  onSection,
  onSignOut,
  onClose,
}) {
  const currentIndex = STEPS.findIndex((s) => s.id === nav.step);
  const userName = (user && user.name) || 'Engineer';

  return (
    <aside className="sidebar" aria-label="Workspace navigation">
      <div className="sidebar-grid" aria-hidden="true" />
      <div className="sidebar-inner">
        <div className="brand">
          <PulseMark size={38} tone="glass" />
          <div className="brand-text">
            <div className="brand-title">FMEA Report</div>
            <div className="brand-sub">ALCM - Maintenance Strategy</div>
          </div>
          <button type="button" className="sidebar-close" onClick={onClose} aria-label="Close menu">
            <X size={20} />
          </button>
        </div>

        <div className="sidebar-scroll">
          <nav aria-label="Workflow">
            <div className="side-label">Workflow</div>
            <ol className="stepper">
              {STEPS.map((step, index) => {
                const detail = stepDetail(step.id, report, counts, uploadBusy);
                const enabled = step.id === 'upload' || Boolean(report);
                const isCurrent = step.id === nav.step;
                const isDone = Boolean(report) && index < currentIndex;
                const state = isCurrent ? 'current' : isDone ? 'done' : 'todo';
                return (
                  <li key={step.id} className={`step step-${state} ${detail.blocked ? 'step-blocked' : ''}`}>
                    <button
                      type="button"
                      className="step-button"
                      onClick={() => onStep(step.id)}
                      disabled={!enabled}
                      aria-current={isCurrent ? 'step' : undefined}
                    >
                      <span className="step-node" aria-hidden="true">
                        {detail.blocked && !isCurrent ? (
                          <Lock size={13} />
                        ) : isDone ? (
                          <Check size={14} strokeWidth={3} />
                        ) : (
                          index + 1
                        )}
                      </span>
                      <span className="step-text">
                        <span className="step-label">{step.label}</span>
                        <span className="step-detail" title={detail.text}>
                          {detail.text}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>

          {report && (
            <nav aria-label="Report sections" className="section-nav-wrap">
              <div className="side-label">Report sections</div>
              <ul className="section-nav">
                {SECTIONS.map((section) => {
                  const Icon = section.icon;
                  const active = nav.step === 'review' && nav.section === section.id;
                  return (
                    <li key={section.id}>
                      <button
                        type="button"
                        className={`section-link ${active ? 'is-active' : ''}`}
                        onClick={() => onSection(section.id)}
                        aria-current={active ? 'page' : undefined}
                      >
                        <Icon size={17} aria-hidden="true" />
                        <span className="section-link-label">{section.label}</span>
                        {section.id === 'checks' && (counts.error > 0 || counts.warning > 0) && (
                          <span className={`side-badge ${counts.error ? 'side-badge-error' : 'side-badge-warning'}`}>
                            {counts.error || counts.warning}
                            <span className="visually-hidden">
                              {counts.error
                                ? (counts.error === 1 ? ' error' : ' errors')
                                : (counts.warning === 1 ? ' warning' : ' warnings')}
                            </span>
                          </span>
                        )}
                      </button>
                      {section.id === 'analysis' && report.uoirs.length > 0 && (
                        <ul className="uoir-subnav">
                          {report.uoirs.map((u) => {
                            const c = countIssues(issuesForUoir(report.issues, u.uoir_id));
                            const selected =
                              nav.step === 'review' &&
                              (nav.section === 'analysis' || nav.section === 'recommendation') &&
                              u.uoir_id === uoirId;
                            return (
                              <li key={u.uoir_id}>
                                <button
                                  type="button"
                                  className={`uoir-link ${selected ? 'is-active' : ''}`}
                                  onClick={() => onSection('analysis', u.uoir_id)}
                                  title={`UOIR ID ${u.uoir_id}: ${u.title}`}
                                >
                                  <span className="uoir-link-id">{u.uoir_id}</span>
                                  <span className="uoir-link-title">{u.title}</span>
                                  {c.error > 0 && (
                                    <OctagonAlert size={13} className="uoir-link-flag is-error" role="img" aria-label="has errors" />
                                  )}
                                  {!c.error && c.warning > 0 && (
                                    <TriangleAlert size={13} className="uoir-link-flag is-warning" role="img" aria-label="has warnings" />
                                  )}
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            </nav>
          )}
        </div>

        <div className="sidebar-foot">
          <span className="avatar" aria-hidden="true">
            {userName.slice(0, 1).toUpperCase()}
          </span>
          <div className="user-text">
            <div className="user-name" title={userName}>
              {userName}
            </div>
            <div className="user-meta">{authMode === 'databricks' ? 'Signed in with Databricks' : 'Signed in'}</div>
          </div>
          {authMode !== 'databricks' && (
            <button type="button" className="signout-btn" onClick={onSignOut}>
              <LogOut size={15} aria-hidden="true" />
              Sign out
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
