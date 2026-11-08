import { useEffect, useRef, useState } from 'react';
import { CalendarDays, Check, CheckCheck, ChevronDown, CircleCheck, Factory, ListTree, LocateFixed, Undo2, Users } from 'lucide-react';
import * as api from '../api/client.js';
import { ReviewStepNav } from '../components/StepNav.jsx';
import WorkbookData from '../components/WorkbookData.jsx';
import { Alert, SeverityIcon } from '../components/Feedback.jsx';
import { issueLocation, issueTarget, plural } from '../lib/report.js';

const ACCEPTED_NOTE = 'Accepted values go into the PDF exactly as they are in the workbook.';

// Errors and warnings stay in their own group until they are accepted on this page;
// then they move to "Accepted" (collapsed), each with Undo. Info notes are never accepted.
const GROUPS = [
  { key: 'error', title: 'Must fix before export', collapsible: false },
  { key: 'warning', title: 'Please check', collapsible: false },
  { key: 'info', title: 'For information', collapsible: true },
  { key: 'accepted', title: 'Accepted', collapsible: true },
];

/** The issues of one group, in report order. */
function groupIssues(issues, key) {
  if (key === 'info') return issues.filter((i) => i.severity === 'info');
  if (key === 'accepted') return issues.filter((i) => i.accepted && (i.severity === 'error' || i.severity === 'warning'));
  return issues.filter((i) => i.severity === key && !i.accepted);
}

const headingId = (key) => `issues-${key}`;
const toggleId = (key) => `issues-${key}-toggle`;

/** The element in `root` whose `attr` is `value`, or null. */
function findByAttr(root, attr, value) {
  return Array.from(root.querySelectorAll(`[${attr}]`)).find((el) => el.getAttribute(attr) === value) || null;
}

/**
 * Where keyboard focus goes once an Accept / Undo has been applied on screen:
 * - after Accept (or Accept all): the next item's Accept button in the same group,
 *   else that group's heading, else the Accepted toggle;
 * - after Undo: the next item's Undo button in Accepted, else the Accepted toggle, else
 *   (nothing left in Accepted) the Accept button of the item that went back.
 */
function focusTarget(root, intent) {
  if (intent.element) return intent.element.isConnected ? intent.element : null;
  const acceptedToggle = document.getElementById(toggleId('accepted'));
  if (intent.kind === 'accept') {
    for (const id of intent.after) {
      const button = findByAttr(root, 'data-accept-id', id);
      if (button) return button;
    }
    return document.getElementById(headingId(intent.group)) || acceptedToggle;
  }
  for (const id of intent.after) {
    const button = findByAttr(root, 'data-undo-id', id);
    if (button) return button;
  }
  return acceptedToggle || intent.ids.map((id) => findByAttr(root, 'data-accept-id', id)).find(Boolean) || null;
}

function IssueItem({ issue, report, busy, onShowInTable, onAccept, onUndo }) {
  const location = issueLocation(issue);
  const target = issueTarget(report, issue);
  const start = issue.message.slice(0, 80);

  let action = null;
  if (issue.accepted) {
    action = (
      <button
        type="button"
        className="btn-ghost btn-sm issue-undo"
        data-undo-id={issue.id}
        aria-label={`Undo: ${start}`}
        disabled={busy}
        onClick={(event) => onUndo(issue, event.currentTarget)}
      >
        <Undo2 size={15} aria-hidden="true" /> Undo
      </button>
    );
  } else if (issue.acceptable) {
    action = (
      <button
        type="button"
        className="gt-btn-secondary btn-sm issue-accept"
        data-accept-id={issue.id}
        aria-label={`Accept: ${start}`}
        disabled={busy}
        onClick={(event) => onAccept(issue, event.currentTarget)}
      >
        <Check size={15} aria-hidden="true" /> Accept
      </button>
    );
  } else if (issue.severity === 'error') {
    action = <span className="issue-fix-note">Fix this in the workbook</span>;
  }

  return (
    <li className={`issue issue-${issue.severity} ${issue.accepted ? 'issue-accepted' : ''}`}>
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
      {(target || action) && (
        <div className="issue-actions">
          {target && (
            <button type="button" className="btn-ghost btn-sm issue-action" onClick={() => onShowInTable(issue)}>
              <LocateFixed size={15} aria-hidden="true" /> Show in table
            </button>
          )}
          {action}
        </div>
      )}
    </li>
  );
}

function IssueGroup({ group, issues, report, busy, onShowInTable, onAccept, onAcceptAll, onUndo }) {
  const [open, setOpen] = useState(!group.collapsible);
  // The readiness banner already says when nothing is wrong, so empty groups are not shown.
  if (issues.length === 0) return null;
  const id = headingId(group.key);
  const accepted = group.key === 'accepted';
  const acceptable = group.key === 'error' || group.key === 'warning' ? issues.filter((i) => i.acceptable) : [];
  const showNote = accepted || (group.key === 'error' && acceptable.length > 0);

  const heading = (
    <>
      {accepted ? (
        <CircleCheck size={18} className="sev-icon sev-accepted" aria-hidden="true" />
      ) : (
        <SeverityIcon severity={group.key} size={18} />
      )}
      <span className="issue-group-title">{group.title}</span>
      <span className={`count-pill count-pill-${group.key}`}>{issues.length}</span>
    </>
  );

  const note = showNote && <p className="issue-group-note">{ACCEPTED_NOTE}</p>;

  return (
    <section className={`gt-card issue-group issue-group-${group.key}`} aria-labelledby={id}>
      {group.collapsible ? (
        <h2 className="issue-group-head" id={id}>
          <button
            type="button"
            id={toggleId(group.key)}
            className="issue-group-toggle"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            {heading}
            <ChevronDown size={18} className={`chevron ${open ? 'is-open' : ''}`} aria-hidden="true" />
          </button>
        </h2>
      ) : (
        <div className="issue-group-bar">
          {/* Focus lands here after the last Accept button of the group has gone. */}
          <h2 className="issue-group-head" id={id} tabIndex={-1}>
            {heading}
          </h2>
          {acceptable.length > 0 && (
            <button
              type="button"
              className="btn-ghost btn-sm issue-accept-all"
              aria-describedby={id}
              disabled={busy}
              onClick={(event) => onAcceptAll(group.key, acceptable, event.currentTarget)}
            >
              <CheckCheck size={15} aria-hidden="true" /> Accept all
            </button>
          )}
        </div>
      )}
      {/* In Accepted the note shows even while the list is collapsed. */}
      {accepted && note}
      {open && (
        <ul className="issue-list">
          {issues.map((issue) => (
            <IssueItem
              key={issue.id}
              issue={issue}
              report={report}
              busy={busy}
              onShowInTable={onShowInTable}
              onAccept={onAccept}
              onUndo={onUndo}
            />
          ))}
        </ul>
      )}
      {!accepted && note}
    </section>
  );
}

/** The readiness banner: open errors block the export; accepted items are counted. */
function ReadinessBanner({ report, counts }) {
  const acceptedCount = groupIssues(report.issues, 'accepted').length;
  const suffix = acceptedCount > 0 ? ` · ${acceptedCount} accepted` : '';

  if (counts.error > 0) {
    const canAccept = report.issues.some((i) => i.severity === 'error' && !i.accepted && i.acceptable);
    return (
      <Alert tone="error" label="Blocked" title={`Export blocked · ${plural(counts.error, 'error')} left`}>
        {canAccept
          ? 'Fix them in the workbook, or accept the ones with an Accept button.'
          : 'Fix them in Excel, save the workbook and upload it again. Preview and export unlock once no errors remain.'}
      </Alert>
    );
  }
  if (counts.warning > 0) {
    return (
      <Alert tone="success" label="Ready" title={`Ready to export · ${plural(counts.warning, 'item')} worth checking${suffix}`}>
        Warnings do not block the export, but please confirm the report reads correctly.
      </Alert>
    );
  }
  if (acceptedCount > 0) {
    return (
      <Alert tone="success" label="Ready" title={`Ready to export${suffix}`}>
        {ACCEPTED_NOTE}
      </Alert>
    );
  }
  return (
    <Alert tone="success" label="Ready" title="Ready to export · no problems found">
      Everything the report needs was found in the workbook.
    </Alert>
  );
}

// `counts` are the open issues (accepted ones left out). `onAcceptance(ids, accepted)`
// resolves once the change is on screen, or once the workspace has gone back to Upload
// because the workbook is no longer open here; it rejects with a plain message (400).
// `acceptanceBusy` is true while any Accept / Undo request runs.
export default function ChecksView({
  report,
  counts,
  onShowInTable,
  onAcceptance,
  acceptanceBusy,
  onWorkbookClosed,
  onBack,
  onNext,
}) {
  const [failure, setFailure] = useState('');
  const [focusAfter, setFocusAfter] = useState(null);
  const rootRef = useRef(null);
  const mounted = useRef(true);
  const busy = Boolean(acceptanceBusy);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Runs once the updated report (or, after a refusal, the same one) is on screen.
  useEffect(() => {
    if (!focusAfter) return;
    setFocusAfter(null);
    const root = rootRef.current;
    const target = root && focusTarget(root, focusAfter);
    if (target) target.focus();
  }, [focusAfter, report]);

  async function change(ids, accepted, intent, trigger) {
    if (busy || ids.length === 0) return;
    setFailure('');
    try {
      await onAcceptance(ids, accepted);
      if (mounted.current) setFocusAfter(intent);
    } catch (err) {
      if (!mounted.current) return;
      if (err instanceof api.ApiError && (err.status === 404 || err.status === 409) && onWorkbookClosed) {
        onWorkbookClosed();
        return;
      }
      // Nothing changed: say why, and give focus back to the button that was pressed.
      setFailure(err.message || 'The change could not be saved. Please try again.');
      setFocusAfter({ element: trigger });
    }
  }

  function accept(issue, trigger) {
    const list = groupIssues(report.issues, issue.severity);
    const after = list.slice(list.findIndex((i) => i.id === issue.id) + 1).map((i) => i.id);
    change([issue.id], true, { kind: 'accept', group: issue.severity, after }, trigger);
  }

  function acceptAll(groupKey, issues, trigger) {
    change(
      issues.map((i) => i.id),
      true,
      { kind: 'accept', group: groupKey, after: [] },
      trigger,
    );
  }

  function undo(issue, trigger) {
    const list = groupIssues(report.issues, 'accepted');
    const after = list.slice(list.findIndex((i) => i.id === issue.id) + 1).map((i) => i.id);
    change([issue.id], false, { kind: 'undo', ids: [issue.id], after }, trigger);
  }

  const facts = [
    { icon: Factory, label: 'Station', value: report.station || 'Not found' },
    { icon: CalendarDays, label: 'Date of Analysis', value: report.analysis_date_text || 'Not found' },
    { icon: ListTree, label: 'UOIRs', value: String(report.uoir_ids.length) },
    { icon: Users, label: 'Team members', value: String(report.team.length) },
  ];

  return (
    <div className="view-checks" ref={rootRef}>
      {/* The title and subtitle are in the top bar; this row holds the page's buttons only. */}
      <div className="page-actions">
        <ReviewStepNav report={report} counts={counts} onBack={onBack} onNext={onNext} />
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

      <ReadinessBanner report={report} counts={counts} />

      {failure && (
        <Alert tone="error" label="Not changed">
          {failure}
        </Alert>
      )}

      {GROUPS.map((group) => (
        <IssueGroup
          key={group.key}
          group={group}
          issues={groupIssues(report.issues, group.key)}
          report={report}
          busy={busy}
          onShowInTable={onShowInTable}
          onAccept={accept}
          onAcceptAll={acceptAll}
          onUndo={undo}
        />
      ))}

      <WorkbookData report={report} />
    </div>
  );
}
