import { useState } from 'react';
import { ClipboardList, FileWarning, ListTree, Lock, StickyNote, Table2, Users } from 'lucide-react';
import Tabs from './Tabs.jsx';
import UoirSelector from './UoirSelector.jsx';
import AnalysisTable from './AnalysisTable.jsx';
import { EmptyState } from './Feedback.jsx';
import { FailureDetailsTable, TeamTable } from './IntroTables.jsx';
import { issuesForUoir, plural } from '../lib/report.js';

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

function AnalysisPanel({ report, uoirId, onSelectUoir }) {
  if (!report.uoirs.length) {
    return (
      <EmptyState icon={ListTree} title="No UOIRs found" compact>
        The workbook does not list any UOIRs. The checks above say what to fix.
      </EmptyState>
    );
  }

  const uoir = report.uoirs.find((u) => u.uoir_id === uoirId) || report.uoirs[0];
  const table = uoir.analysis;
  return (
    <>
      <UoirSelector report={report} value={uoir.uoir_id} onChange={onSelectUoir} variant="analysis" />
      <div className="wbd-uoir-head">
        <div className="wbd-uoir-id">UOIR ID {uoir.uoir_id}</div>
        <h3 className="wbd-uoir-title">{uoir.title}</h3>
      </div>
      {uoir.notes.length > 0 && (
        <ul className="notes" aria-label="Notes found outside the table">
          {uoir.notes.map((note) => (
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
          <AnalysisTable uoir={uoir} issues={issuesForUoir(report.issues, uoir.uoir_id)} focus={null} />
        </>
      ) : (
        <EmptyState icon={FileWarning} title="No analysis table for this UOIR" compact>
          The analysis tab for UOIR ID {uoir.uoir_id} was not found or could not be read. The checks above say what to fix.
        </EmptyState>
      )}
    </>
  );
}

export default function WorkbookData({ report }) {
  const [tab, setTab] = useState('team');
  const [uoirId, setUoirId] = useState(report.uoirs.length ? report.uoirs[0].uoir_id : null);

  const tabs = [
    { id: 'team', label: 'Team Members', icon: Users, count: report.team.length },
    { id: 'failures', label: 'Failure Details', icon: ClipboardList, count: report.failure_details.length },
    { id: 'analysis', label: 'Analysis', icon: Table2, count: report.uoirs.filter((u) => u.analysis).length },
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
        {tab === 'analysis' && <AnalysisPanel report={report} uoirId={uoirId} onSelectUoir={setUoirId} />}
      </div>
    </section>
  );
}
