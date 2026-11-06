import { Cog, OctagonAlert, TriangleAlert } from 'lucide-react';
import { countIssues, plural, sectionLabel } from '../lib/report.js';

// Heading of the analysis section on screen: its UOIR IDs, title, equipment and the
// counts of `issues` (the section's own, from issuesForSection). No sheet caption.
export default function SectionHeading({ section, issues }) {
  const c = countIssues(issues);
  return (
    <div className="uoir-heading">
      <div className="uoir-heading-id">UOIR ID {sectionLabel(section)}</div>
      <h2 className="uoir-heading-title">{section.title}</h2>
      <div className="uoir-heading-meta">
        {section.equipment.length > 0 && (
          <span className="meta-item" title="Equipment">
            <Cog size={15} aria-hidden="true" />
            {section.equipment.join(' / ')}
          </span>
        )}
        {c.error > 0 && (
          <span className="meta-item meta-error">
            <OctagonAlert size={15} aria-hidden="true" />
            {plural(c.error, 'error')}
          </span>
        )}
        {c.warning > 0 && (
          <span className="meta-item meta-warning">
            <TriangleAlert size={15} aria-hidden="true" />
            {plural(c.warning, 'warning')}
          </span>
        )}
      </div>
    </div>
  );
}
