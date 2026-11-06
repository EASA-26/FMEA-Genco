import { useState } from 'react';
import { CalendarDays, ChevronDown, Factory, ListTree, LocateFixed, Users } from 'lucide-react';
import { ReviewStepNav } from '../components/StepNav.jsx';
import WorkbookData from '../components/WorkbookData.jsx';
import { Alert, SeverityIcon } from '../components/Feedback.jsx';
import { issueLocation, issueTarget, plural } from '../lib/report.js';

const GROUPS = [
  { severity: 'error', title: 'Must fix before export', collapsible: false },
  { severity: 'warning', title: 'Please check', collapsible: false },
  { severity: 'info', title: 'For information', collapsible: true },
];

function IssueItem({ issue, report, onShowInTable }) {
  const location = issueLocation(issue);
  const target = issueTarget(report, issue);
  return (
    <li className={`issue issue-${issue.severity}`}>
      <SeverityIcon severity={issue.severity} size={18} />
      <div className="issue-body">
        <p className="issue-message">{issue.message}</p>
        {(location.length > 0 || issue.uoir_id) && (
          <div className="issue-meta">
            {issue.uoir_id && <span className="gt-badge loc-uoir">UOIR ID {issue.uoir_id}</span>}
            {location.map((part) => (
              <span key={part.label} className="loc" title={`${part.label}: ${part.value}`}>
                <span className="loc-label">{part.label}</span> {part.value}
              </span>
            ))}
          </div>
        )}
      </div>
      {target && (
        <button type="button" className="btn-ghost btn-sm issue-action" onClick={() => onShowInTable(issue)}>
          <LocateFixed size={15} aria-hidden="true" /> Show in table
        </button>
      )}
    </li>
  );
}

function IssueGroup({ group, issues, report, onShowInTable }) {
  const [open, setOpen] = useState(!group.collapsible);
  // The readiness banner already says when nothing is wrong, so empty groups are not shown.
  if (issues.length === 0) return null;
  const headingId = `issues-${group.severity}`;

  const heading = (
    <>
      <SeverityIcon severity={group.severity} size={18} />
      <span className="issue-group-title">{group.title}</span>
      <span className={`count-pill count-pill-${group.severity}`}>{issues.length}</span>
    </>
  );

  return (
    <section className={`gt-card issue-group issue-group-${group.severity}`} aria-labelledby={headingId}>
      {group.collapsible ? (
        <h2 className="issue-group-head" id={headingId}>
          <button type="button" className="issue-group-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {heading}
            <ChevronDown size={18} className={`chevron ${open ? 'is-open' : ''}`} aria-hidden="true" />
          </button>
        </h2>
      ) : (
        <h2 className="issue-group-head" id={headingId}>
          {heading}
        </h2>
      )}
      {open && (
        <ul className="issue-list">
          {issues.map((issue, index) => (
            <IssueItem key={`${issue.code}-${index}`} issue={issue} report={report} onShowInTable={onShowInTable} />
          ))}
        </ul>
      )}
    </section>
  );
}

export default function ChecksView({ report, counts, onShowInTable, onBack, onNext }) {
  const facts = [
    { icon: Factory, label: 'Station', value: report.station || 'Not found' },
    { icon: CalendarDays, label: 'Date of Analysis', value: report.analysis_date_text || 'Not found' },
    { icon: ListTree, label: 'UOIRs', value: String(report.uoir_ids.length) },
    { icon: Users, label: 'Team members', value: String(report.team.length) },
  ];

  return (
    <div className="view-checks">
      {/* The title and subtitle are in the top bar; this row holds the page's buttons only. */}
      <div className="page-actions">
        <ReviewStepNav counts={counts} onBack={onBack} onNext={onNext} />
      </div>

      <div className="fact-grid">
        {facts.map((fact) => {
          const Icon = fact.icon;
          return (
            <div key={fact.label} className="gt-card fact">
              <span className="icon-tile icon-tile-soft" aria-hidden="true">
                <Icon size={18} />
              </span>
              <div className="fact-text">
                <div className="fact-label">{fact.label}</div>
                <div className="fact-value" title={fact.value}>
                  {fact.value}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {counts.error > 0 ? (
        <Alert tone="error" label="Export blocked" title={`${plural(counts.error, 'error')} must be fixed in the workbook`}>
          Fix them in Excel, save the workbook and upload it again. Preview and export unlock once no errors remain.
        </Alert>
      ) : (
        <Alert
          tone="success"
          label="Ready"
          title={counts.warning ? `Ready to export · ${plural(counts.warning, 'item')} worth checking` : 'Ready to export · no problems found'}
        >
          {counts.warning
            ? 'Warnings do not block the export, but please confirm the report reads correctly.'
            : 'Everything the report needs was found in the workbook.'}
        </Alert>
      )}

      {GROUPS.map((group) => (
        <IssueGroup
          key={group.severity}
          group={group}
          issues={report.issues.filter((i) => i.severity === group.severity)}
          report={report}
          onShowInTable={onShowInTable}
        />
      ))}

      <WorkbookData report={report} />
    </div>
  );
}
