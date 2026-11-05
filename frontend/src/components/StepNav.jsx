import { useId } from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { plural } from '../lib/report.js';

/**
 * Back / Next buttons between the workflow steps. Pages have no heading of their own
 * (the title is in the top bar), so this sits in the page's right-aligned action row:
 * <div className="page-actions"><StepNav ... /></div>.
 *
 * back: { label, onClick, disabled }           -> secondary button with a left arrow
 * next: { label, onClick, disabled, reason }   -> primary button with a right arrow;
 *        `reason` (shown beside it) says why it is disabled.
 *
 * The button text is the name of the step it opens ("Upload Workbook",
 * "Preview Report"); screen readers also hear "Back to" / "Next:".
 */
export default function StepNav({ back, next }) {
  const reasonId = useId();
  const nextBlocked = Boolean(next && next.disabled);
  return (
    <nav className="step-nav" aria-label="Workflow steps">
      {back && (
        <button
          type="button"
          className="gt-btn-secondary step-nav-back"
          onClick={back.onClick}
          disabled={Boolean(back.disabled)}
          aria-label={`Back to ${back.label}`}
        >
          <ArrowLeft size={18} aria-hidden="true" />
          {back.label}
        </button>
      )}
      {next && (
        <span className="step-nav-next-wrap">
          {nextBlocked && next.reason && (
            <span id={reasonId} className="step-nav-reason">
              {next.reason}
            </span>
          )}
          <button
            type="button"
            className="gt-btn-primary step-nav-next"
            onClick={next.onClick}
            disabled={nextBlocked}
            aria-label={`Next: ${next.label}`}
            aria-describedby={nextBlocked && next.reason ? reasonId : undefined}
          >
            {next.label}
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        </span>
      )}
    </nav>
  );
}

/** Step 2 (Review Data): the same Back / Next on Data checks and every report section. */
export function ReviewStepNav({ counts, onBack, onNext }) {
  return (
    <StepNav
      back={{ label: 'Upload Workbook', onClick: onBack }}
      next={{
        label: 'Preview Report',
        onClick: onNext,
        disabled: counts.error > 0,
        reason: `Fix ${plural(counts.error, 'error')} to preview`,
      }}
    />
  );
}
