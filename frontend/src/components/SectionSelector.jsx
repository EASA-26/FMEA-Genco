import { useEffect, useRef } from 'react';
import { OctagonAlert, TriangleAlert } from 'lucide-react';
import { countIssues, issuesForSection, newTaskCounts, sectionLabel } from '../lib/report.js';

function AnalysisStats({ section }) {
  const s = section.summary;
  if (!s) return <span className="uoir-card-empty">No analysis data</span>;
  return (
    <>
      <span>
        <b>{s.failure_mode_count}</b> Failure Mode
      </span>
      <span>
        <b>{s.maintenance_task_count}</b> Maint. Task
      </span>
      <span>
        <b>{s.task_executed_count}</b> Executed
      </span>
    </>
  );
}

function RecommendationStats({ section }) {
  if (!section.recommendations.length) return <span className="uoir-card-empty">No recommendations</span>;
  const c = newTaskCounts(section);
  return (
    <>
      <span>
        <b>{c.yes}</b> Yes
      </span>
      <span>
        <b>{c.no}</b> No
      </span>
      {c.notSet > 0 && (
        <span>
          <b>{c.notSet}</b> not set
        </span>
      )}
    </>
  );
}

// Card strip for choosing the analysis section (one per analysis tab) shown in Analysis,
// Recommendation and Workbook data. `value` and `onChange` use the tab name (sheet_name);
// the tab name is shown only in the card's tooltip, with the full title.
export default function SectionSelector({ report, value, onChange, variant = 'analysis' }) {
  const stripRef = useRef(null);

  // Keep the selected card in view when the strip scrolls sideways (many tabs).
  useEffect(() => {
    const strip = stripRef.current;
    const card = strip && strip.querySelector('.uoir-card.is-selected');
    if (!card) return;
    const left = card.offsetLeft; // the strip is the cards' offset parent (position: relative)
    const right = left + card.offsetWidth;
    if (left < strip.scrollLeft) strip.scrollTo({ left: left - 4, behavior: 'smooth' });
    else if (right > strip.scrollLeft + strip.clientWidth) {
      strip.scrollTo({ left: right - strip.clientWidth + 4, behavior: 'smooth' });
    }
  }, [value]);

  return (
    <div className="uoir-selector" role="group" aria-label="Choose an analysis tab" ref={stripRef}>
      {report.analyses.map((section) => {
        const selected = section.sheet_name === value;
        const c = countIssues(issuesForSection(report.issues, section));
        return (
          <button
            key={section.sheet_name}
            type="button"
            className={`uoir-card ${selected ? 'is-selected' : ''}`}
            aria-pressed={selected}
            onClick={() => onChange(section.sheet_name)}
            title={section.title ? `${section.sheet_name}: ${section.title}` : section.sheet_name}
          >
            <span className="uoir-card-top">
              <span className="uoir-card-id">UOIR ID {sectionLabel(section)}</span>
              {c.error > 0 && (
                <span className="mini-flag mini-flag-error">
                  <OctagonAlert size={13} aria-hidden="true" />
                  {c.error}
                  <span className="visually-hidden"> errors</span>
                </span>
              )}
              {c.warning > 0 && (
                <span className="mini-flag mini-flag-warning">
                  <TriangleAlert size={13} aria-hidden="true" />
                  {c.warning}
                  <span className="visually-hidden"> warnings</span>
                </span>
              )}
            </span>
            <span className="uoir-card-title">{section.title}</span>
            <span className="uoir-card-stats">
              {variant === 'analysis' ? <AnalysisStats section={section} /> : <RecommendationStats section={section} />}
            </span>
          </button>
        );
      })}
    </div>
  );
}
