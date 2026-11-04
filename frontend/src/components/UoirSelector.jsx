import { useEffect, useRef } from 'react';
import { OctagonAlert, TriangleAlert } from 'lucide-react';
import { countIssues, issuesForUoir, newTaskCounts } from '../lib/report.js';

function AnalysisStats({ uoir }) {
  const s = uoir.summary;
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

function RecommendationStats({ uoir }) {
  if (!uoir.recommendations.length) return <span className="uoir-card-empty">No recommendations</span>;
  const c = newTaskCounts(uoir);
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

// Card strip for choosing the UOIR shown in Analysis and Recommendation.
export default function UoirSelector({ report, value, onChange, variant = 'analysis' }) {
  const stripRef = useRef(null);

  // Keep the selected card in view when the strip scrolls sideways (many UOIRs).
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
    <div className="uoir-selector" role="group" aria-label="Choose a UOIR" ref={stripRef}>
      {report.uoirs.map((uoir) => {
        const selected = uoir.uoir_id === value;
        const c = countIssues(issuesForUoir(report.issues, uoir.uoir_id));
        return (
          <button
            key={uoir.uoir_id}
            type="button"
            className={`uoir-card ${selected ? 'is-selected' : ''}`}
            aria-pressed={selected}
            onClick={() => onChange(uoir.uoir_id)}
            title={uoir.title}
          >
            <span className="uoir-card-top">
              <span className="uoir-card-id">UOIR ID {uoir.uoir_id}</span>
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
            <span className="uoir-card-title">{uoir.title}</span>
            <span className="uoir-card-stats">
              {variant === 'analysis' ? <AnalysisStats uoir={uoir} /> : <RecommendationStats uoir={uoir} />}
            </span>
          </button>
        );
      })}
    </div>
  );
}
