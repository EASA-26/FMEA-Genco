import { FAILURE_DETAILS_COLUMNS, TEAM_COLUMNS } from '../lib/report.js';

// The two Introduction tables, shared by the Introduction section and the
// read-only Workbook data panel in Review Data, so both always show the same thing.
// Callers decide what to show when there are no rows.

// The scroller takes keyboard focus (tabIndex 0) so a wide table can be scrolled
// sideways with the arrow keys; `label` names it for screen readers.
function RowsTable({ columns, rows, className, label }) {
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label={label}>
      <table className={`data-table ${className}`}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} scope="col" className={`col-${col.key}`}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.source_row}>
              {columns.map((col) => (
                <td key={col.key} className={`col-${col.key} multiline`}>
                  {row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Failure Details: one row per UOIR sheet row (a UOIR ID can repeat). */
export function FailureDetailsTable({ rows }) {
  return (
    <RowsTable columns={FAILURE_DETAILS_COLUMNS} rows={rows} className="failure-details-table" label="Failure Details table" />
  );
}

/** Team Members: the analysis team from the Team Member sheet. */
export function TeamTable({ rows }) {
  return <RowsTable columns={TEAM_COLUMNS} rows={rows} className="team-table" label="Team Members table" />;
}
