import { CalendarDays, Factory, FileDown, PenLine } from 'lucide-react';
import CoverPage from '../components/CoverPage.jsx';
import { ReviewStepNav } from '../components/StepNav.jsx';

// Station and Date of Analysis carry no "sheet, cell" caption: Review Data does not
// name the cells values come from.
export default function FrontPageView({ report, counts, onBack, onNext }) {
  const rows = [
    {
      icon: Factory,
      label: 'Station',
      value: report.station,
      missing: 'Not found in the workbook',
    },
    {
      icon: CalendarDays,
      label: 'Date of Analysis',
      value: report.analysis_date_text,
      missing: 'Not found in the workbook',
    },
    {
      icon: PenLine,
      label: 'Prepared by / Approved by',
      value: 'Left blank for signatures',
      source: 'Signed on the printed or digital copy',
    },
    {
      icon: FileDown,
      label: 'PDF file name',
      value: report.pdf_filename,
      source: 'Station and Date of Analysis',
    },
  ];

  return (
    <div className="view-front">
      <div className="page-actions">
        <ReviewStepNav counts={counts} onBack={onBack} onNext={onNext} />
      </div>

      <div className="front-layout">
        <CoverPage station={report.station} analysisDate={report.analysis_date_text} />

        <aside className="gt-card front-facts" aria-label="Where the front page values come from">
          <h2 className="card-title">On this page</h2>
          <ul className="source-list">
            {rows.map((row) => {
              const Icon = row.icon;
              return (
                <li key={row.label}>
                  <span className="icon-tile icon-tile-soft" aria-hidden="true">
                    <Icon size={17} />
                  </span>
                  <div>
                    <div className="source-label">{row.label}</div>
                    <div className={`source-value ${row.value ? '' : 'is-missing'}`}>{row.value || row.missing}</div>
                    {row.source && <div className="source-origin">{row.source}</div>}
                  </div>
                </li>
              );
            })}
          </ul>
        </aside>
      </div>
    </div>
  );
}
