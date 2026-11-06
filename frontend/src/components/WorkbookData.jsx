import { useState } from 'react';
import { ClipboardList, FileWarning, ListTree, Lock, StickyNote, Table2, Users } from 'lucide-react';
import Tabs from './Tabs.jsx';
import SectionSelector from './SectionSelector.jsx';
import AnalysisTable from './AnalysisTable.jsx';
import { EmptyState } from './Feedback.jsx';
import { FailureDetailsTable, TeamTable } from './IntroTables.jsx';
import { findSection, issuesForSection, plural, sectionLabel } from '../lib/report.js';

// Review Data: everything read from the workbook, in one card, so it can be checked
// before the report preview. Read-only on purpose: the workbook stays the single
// source of truth, and changes are made there and uploaded again.
// No sheet or cell references here: the issue list above already says where to fix things.

function TeamPanel({ report }) {
  return (
    <>
      <dl className="wbd-facts">
        <div className="wbd-fact">
          <dt>Station</dt>
          <dd>{report.station || 'Not found'}</dd>
        </div>
        <div className="wbd-fact">
          <dt>Date of Analysis</dt>
          <dd>{report.analysis_date_text || 'Not found'}</dd>
        </div>
      </dl>
      {report.team.length ? (
        <TeamTable rows={report.team} />
      ) : (
        <EmptyState icon={Users} title="No team members" compact>
          No team members were found in the workbook.
        </EmptyState>
      )}
    </>
  );
}

function FailureDetailsPanel({ report }) {
  if (!report.failure_details.length) {
    return (
      <EmptyState icon={ClipboardList} title="No failure details" compact>
        No UOIR rows were found in the workbook. The checks above say what to fix.
      </EmptyState>
    );
  }
  return <FailureDetailsTable rows={report.failure_details} />;
}

// One entry per analysis tab, chosen here independently of the Analysis page.
function AnalysisPanel({ report, sectionKey, onSelectSection }) {
  if (!report.analyses.length) {
    return (
      <EmptyState icon={ListTree} title="No analysis tabs found" compact>
        No analysis tabs were found in the workbook. See Data checks.
      </EmptyState>
    );
  }

  const section = findSection(report, sectionKey) || report.analyses[0];
  const table = section.analysis;
  return (
    <>
      <SectionSelector report={report} value={section.sheet_name} onChange={onSelectSection} variant="analysis" />
      <div className="wbd-uoir-head">
        <div className="wbd-uoir-id">UOIR ID {sectionLabel(section)}</div>
        <h3 className="wbd-uoir-title">{section.title}</h3>
      </div>
      {section.notes.length > 0 && (
        <ul className="notes" aria-label="Notes found outside the table">
          {section.notes.map((note) => (
            <li key={note.cell} className="note">
              <StickyNote size={16} aria-hidden="true" />
              <span className="note-label">Note :</span>
              <span className="note-text">{note.text}</span>
            </li>
          ))}
        </ul>
      )}
      {table ? (
        <>
          <div className="table-caption">
            <span>
              {plural(table.rows.length, 'row')} · {plural(table.columns.length, 'column')}
            </span>
            <span className="table-caption-hint">Scroll sideways to see every column.</span>
          </div>
          <AnalysisTable section={section} issues={issuesForSection(report.issues, section)} focus={null} />
        </>
      ) : (
        <EmptyState icon={FileWarning} title="No analysis table for this tab" compact>
          The analysis table could not be read from this tab. See Data checks.
        </EmptyState>
      )}
    </>
  );
}

export default function WorkbookData({ report }) {
  const [tab, setTab] = useState('team');
  const [sectionKey, setSectionKey] = useState(report.analyses[0]?.sheet_name ?? null);

  const tabs = [
    { id: 'team', label: 'Team Members', icon: Users, count: report.team.length },
    { id: 'failures', label: 'Failure Details', icon: ClipboardList, count: report.failure_details.length },
    { id: 'analysis', label: 'Analysis', icon: Table2, count: report.analyses.length },
  ];

  return (
    <section className="gt-card workbook-data" aria-labelledby="workbook-data-title">
      <div className="workbook-data-head">
        <h2 id="workbook-data-title" className="card-title">
          Workbook data
        </h2>
        <p className="workbook-data-note">
          <Lock size={14} aria-hidden="true" />
          <span>Read-only. To change anything, edit the workbook in Excel and upload it again.</span>
        </p>
      </div>

      <Tabs tabs={tabs} value={tab} onChange={setTab} label="Workbook data" idPrefix="workbook-data" />
      <div
        id="workbook-data-panel"
        role="tabpanel"
        aria-labelledby={`workbook-data-tab-${tab}`}
        className="tab-panel workbook-data-panel"
        tabIndex={0}
        key={tab}
      >
        {tab === 'team' && <TeamPanel report={report} />}
        {tab === 'failures' && <FailureDetailsPanel report={report} />}
        {tab === 'analysis' && (
          <AnalysisPanel report={report} sectionKey={sectionKey} onSelectSection={setSectionKey} />
        )}
      </div>
    </section>
  );
}
