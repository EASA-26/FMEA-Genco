import { ChartPie, FileWarning, ListTree, StickyNote, Table2 } from 'lucide-react';
import { ReviewStepNav } from '../components/StepNav.jsx';
import Tabs from '../components/Tabs.jsx';
import SectionSelector from '../components/SectionSelector.jsx';
import AnalysisTable from '../components/AnalysisTable.jsx';
import SummaryPanel from '../components/SummaryPanel.jsx';
import { EmptyState } from '../components/Feedback.jsx';
import SectionHeading from '../components/SectionHeading.jsx';
import { issuesForSection, plural, sectionLabel } from '../lib/report.js';

function AnalysisTab({ section, issues, focus, onShowChecks }) {
  if (!section.analysis) {
    return (
      <EmptyState
        icon={FileWarning}
        title="No analysis table for this tab"
        actions={
          <button type="button" className="gt-btn-secondary" onClick={onShowChecks}>
            Open Data checks
          </button>
        }
      >
        The analysis table could not be read from this tab. See Data checks.
      </EmptyState>
    );
  }

  const table = section.analysis;
  const mergedCount = (table.merged || []).length;
  return (
    <div className="analysis-tab">
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
      {/* No sheet, cell or header-row captions in Review Data (only data-check messages say
          where a problem is). */}
      <div className="table-caption">
        <span>
          {plural(table.rows.length, 'row')} · {plural(table.columns.length, 'column')}
          {mergedCount > 0 && <> · {plural(mergedCount, 'merged range')} kept as in the workbook</>}
        </span>
        <span className="table-caption-hint">Scroll sideways to see every column.</span>
      </div>
      <AnalysisTable section={section} issues={issues} focus={focus} />
    </div>
  );
}

// `counts` are the data-check counts (they decide whether Next can open the preview).
// `section` is the analysis section (tab) on screen, or null when the workbook has none.
export default function AnalysisView({ report, counts, section, onSelectSection, tab, onTab, focus, onShowChecks, onBack, onNext }) {
  const header = (
    <div className="page-actions">
      <ReviewStepNav counts={counts} onBack={onBack} onNext={onNext} />
    </div>
  );

  if (!section) {
    return (
      <div className="view-analysis">
        {header}
        <EmptyState icon={ListTree} title="No analysis tabs found">
          No analysis tabs were found in the workbook. See Data checks.
        </EmptyState>
      </div>
    );
  }

  const issues = issuesForSection(report.issues, section);
  const tabs = [
    { id: 'analysis', label: 'FMEA Analysis', icon: Table2 },
    { id: 'summary', label: 'FMEA Summary', icon: ChartPie },
  ];

  return (
    <div className="view-analysis">
      {header}
      <SectionSelector report={report} value={section.sheet_name} onChange={onSelectSection} variant="analysis" />

      <section className="uoir-panel" aria-label={`UOIR ID ${sectionLabel(section)}`}>
        <SectionHeading section={section} issues={issues} />
        <Tabs tabs={tabs} value={tab} onChange={onTab} label="Analysis views" idPrefix="analysis" />
        <div id="analysis-panel" role="tabpanel" aria-labelledby={`analysis-tab-${tab}`} className="tab-panel" key={`${section.sheet_name}-${tab}`}>
          {tab === 'summary' ? (
            <SummaryPanel section={section} onShowChecks={onShowChecks} />
          ) : (
            <AnalysisTab section={section} issues={issues} focus={focus} onShowChecks={onShowChecks} />
          )}
        </div>
      </section>
    </div>
  );
}
