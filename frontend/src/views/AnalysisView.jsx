import { ChartPie, FileWarning, ListTree, StickyNote, Table2 } from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import Tabs from '../components/Tabs.jsx';
import UoirSelector from '../components/UoirSelector.jsx';
import AnalysisTable from '../components/AnalysisTable.jsx';
import SummaryPanel from '../components/SummaryPanel.jsx';
import { EmptyState } from '../components/Feedback.jsx';
import UoirHeading from '../components/UoirHeading.jsx';
import { issuesForUoir, plural } from '../lib/report.js';

function AnalysisTab({ uoir, issues, focus, onShowChecks }) {
  if (!uoir.analysis) {
    return (
      <EmptyState
        icon={FileWarning}
        title="No analysis table for this UOIR"
        actions={
          <button type="button" className="btn btn-secondary" onClick={onShowChecks}>
            Open Data checks
          </button>
        }
      >
        The analysis tab for UOIR ID {uoir.uoir_id} was not found or could not be read. Data checks explain what to fix.
      </EmptyState>
    );
  }

  const table = uoir.analysis;
  const mergedCount = (table.merged || []).length;
  return (
    <div className="analysis-tab">
      {uoir.notes.length > 0 && (
        <ul className="notes" aria-label="Notes found outside the table">
          {uoir.notes.map((note) => (
            <li key={note.cell} className="note">
              <StickyNote size={16} aria-hidden="true" />
              <span className="note-label">Note :</span>
              <span className="note-text">{note.text}</span>
              <span className="loc">
                <span className="loc-label">Cell</span> {note.cell}
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="table-caption">
        <span>
          {plural(table.rows.length, 'row')} · {plural(table.columns.length, 'column')} · header on row {table.header_row}
          {mergedCount > 0 && <> · {plural(mergedCount, 'merged range')} kept as in the workbook</>}
        </span>
        <span className="table-caption-hint">Scroll sideways to see every column.</span>
      </div>
      <AnalysisTable uoir={uoir} issues={issues} focus={focus} />
    </div>
  );
}

export default function AnalysisView({ report, uoir, onSelectUoir, tab, onTab, focus, onShowChecks }) {
  const header = (
    <PageHeader eyebrow="Review Data · Report section" title="Analysis">
      The FMEA Analysis table and FMEA Summary counts for each UOIR.
    </PageHeader>
  );

  if (!uoir) {
    return (
      <div className="view-analysis">
        {header}
        <EmptyState icon={ListTree} title="No UOIRs found">
          The UOIR sheet did not list any UOIRs. See Data checks for what to fix.
        </EmptyState>
      </div>
    );
  }

  const issues = issuesForUoir(report.issues, uoir.uoir_id);
  const tabs = [
    { id: 'analysis', label: 'FMEA Analysis', icon: Table2 },
    { id: 'summary', label: 'FMEA Summary', icon: ChartPie },
  ];

  return (
    <div className="view-analysis">
      {header}
      <UoirSelector report={report} value={uoir.uoir_id} onChange={onSelectUoir} variant="analysis" />

      <section className="uoir-panel" aria-label={`UOIR ID ${uoir.uoir_id}`}>
        <UoirHeading uoir={uoir} issues={issues} showSheet />
        <Tabs tabs={tabs} value={tab} onChange={onTab} label="Analysis views" idPrefix="analysis" />
        <div id="analysis-panel" role="tabpanel" aria-labelledby={`analysis-tab-${tab}`} className="tab-panel" key={`${uoir.uoir_id}-${tab}`}>
          {tab === 'summary' ? (
            <SummaryPanel uoir={uoir} onShowChecks={onShowChecks} />
          ) : (
            <AnalysisTab uoir={uoir} issues={issues} focus={focus} onShowChecks={onShowChecks} />
          )}
        </div>
      </section>
    </div>
  );
}
