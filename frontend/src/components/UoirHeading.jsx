import { Cog, FileSpreadsheet, OctagonAlert, TriangleAlert } from 'lucide-react';
import { countIssues, plural } from '../lib/report.js';

export default function UoirHeading({ uoir, issues, showSheet = false }) {
  const c = countIssues(issues);
  return (
    <div className="uoir-heading">
      <div className="uoir-heading-id">UOIR ID {uoir.uoir_id}</div>
      <h2 className="uoir-heading-title">{uoir.title}</h2>
      <div className="uoir-heading-meta">
        {showSheet && (
          <span className="meta-item" title="Worksheet">
            <FileSpreadsheet size={15} aria-hidden="true" />
            {uoir.sheet_name ? `Tab '${uoir.sheet_name}'` : 'No analysis tab linked'}
          </span>
        )}
        {uoir.equipment.length > 0 && (
          <span className="meta-item" title="Equipment">
            <Cog size={15} aria-hidden="true" />
            {uoir.equipment.join(' / ')}
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
