import {
  Activity,
  Check,
  ClipboardList,
  Factory,
  Lock,
  OctagonAlert,
  ShieldCheck,
  TriangleAlert,
  Users,
  Wrench,
  X,
} from 'lucide-react';
import { countIssues, issuesForSection, plural, sectionLabel } from '../lib/report.js';
import AppIcon from './AppIcon';
import brandmark1x from '../assets/tnb-genco-ted-white@1x.png';
import brandmark2x from '../assets/tnb-genco-ted-white@2x.png';
import brandmark3x from '../assets/tnb-genco-ted-white@3x.png';

const STEPS = [
  { id: 'upload', label: 'Upload Excel' },
  { id: 'review', label: 'Review Data' },
  { id: 'preview', label: 'Preview Report' },
  { id: 'export', label: 'Export PDF' },
];

// Report sections, with icons in the reliability, risk and engineering motif.
// ExportView's "In this report" list uses the same icon for each section.
const SECTIONS = [
  { id: 'checks', label: 'Data Checks', icon: ShieldCheck },
  { id: 'front', label: 'Front Page', icon: Factory },
  { id: 'intro', label: 'Introduction', icon: ClipboardList },
  { id: 'analysis', label: 'Analysis', icon: Activity },
  { id: 'recommendation', label: 'Recommendation', icon: Wrench },
];

function stepDetail(step, report, counts, uploadBusy) {
  if (step === 'upload') {
    if (uploadBusy) return { text: 'Reading workbook…' };
    return { text: report ? report.source_filename : 'Choose a workbook' };
  }
  if (!report) return { text: 'Waiting for a workbook' };
  if (step === 'review') {
    const parts = [plural(report.uoir_ids.length, 'UOIR')];
    if (counts.error) parts.push(plural(counts.error, 'error'));
    else if (counts.warning) parts.push(plural(counts.warning, 'warning'));
    return { text: parts.join(' · ') };
  }
  if (counts.error) return { text: `Blocked by ${plural(counts.error, 'error')}`, blocked: true };
  return { text: step === 'preview' ? 'See the PDF as it will print' : report.pdf_filename };
}

// The signed-in user and Sign out live in the top bar; the sidebar foot names the
// team that runs this process.
// `sectionKey` is the tab name (sheet_name) of the analysis section on screen.
export default function Sidebar({ report, counts, nav, sectionKey, uploadBusy, onStep, onSection, onClose }) {
  const currentIndex = STEPS.findIndex((s) => s.id === nav.step);

  return (
    <aside className="sidebar gt-sidebar" aria-label="Workspace navigation">
      {/* Logo block: TNB GENCO · TED brandmark and the product name block */}
      <div className="sidebar-logo gt-sidebar-logo">
        <button type="button" className="sidebar-close gt-icon-btn" onClick={onClose} aria-label="Close menu">
          <X size={20} />
        </button>
        <img
          src={brandmark1x}
          srcSet={`${brandmark1x} 1x, ${brandmark2x} 2x, ${brandmark3x} 3x`}
          alt="TNB GENCO · TED"
          className="gt-brandmark"
        />
        {/* Product block: the app icon next to the name, then the one-line description.
            The sidebar is on every page, so the icon is always in view (pages never repeat it). */}
        <div className="gt-product">
          <div className="gt-product-head">
            <span className="gt-product-icon" aria-hidden="true">
              <AppIcon app="fmea" className="gt-app-icon" />
            </span>
            <p className="gt-product-name">FMEA Report</p>
          </div>
          <p className="gt-product-desc">Failure Mode &amp; Effects Analysis</p>
        </div>
      </div>

      <div className="sidebar-nav gt-nav">
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
                      className={`section-link gt-nav-item ${active ? 'is-active' : ''}`}
                      onClick={() => onSection(section.id)}
                      aria-current={active ? 'page' : undefined}
                    >
                      <Icon size={18} aria-hidden="true" />
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
                    {section.id === 'analysis' && report.analyses.length > 0 && (
                      <ul className="uoir-subnav">
                        {report.analyses.map((a) => {
                          const c = countIssues(issuesForSection(report.issues, a));
                          const selected =
                            nav.step === 'review' &&
                            (nav.section === 'analysis' || nav.section === 'recommendation') &&
                            a.sheet_name === sectionKey;
                          return (
                            <li key={a.sheet_name}>
                              <button
                                type="button"
                                className={`uoir-link ${selected ? 'is-active' : ''}`}
                                onClick={() => onSection('analysis', a.sheet_name)}
                                title={a.sheet_name}
                              >
                                <span className="uoir-link-id">{sectionLabel(a)}</span>
                                <span className="uoir-link-title">{a.title}</span>
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

      <div className="sidebar-foot gt-sidebar-foot">
        <span className="sidebar-team-icon" aria-hidden="true">
          <Users size={18} />
        </span>
        <div className="sidebar-team-text">
          <div className="sidebar-team-label">Team</div>
          <div className="sidebar-team-name">ALCM - Maintenance Strategy</div>
        </div>
      </div>
    </aside>
  );
}
