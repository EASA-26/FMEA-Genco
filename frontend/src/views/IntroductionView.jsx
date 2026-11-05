import { ClipboardList, Users } from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import { EmptyState } from '../components/Feedback.jsx';
import { FAILURE_DETAILS_COLUMNS, TEAM_COLUMNS, plural } from '../lib/report.js';

export default function IntroductionView({ report }) {
  return (
    <div className="view-intro">
      <PageHeader eyebrow="Review Data · Report section" title="Introduction">
        Failure details from the UOIR sheet and the analysis team from the Team Member sheet, exactly as written in the workbook.
      </PageHeader>

      <section className="gt-card table-card" aria-labelledby="failure-details-title">
        <div className="table-card-head">
          <h2 id="failure-details-title" className="card-title">
            Failure Details
          </h2>
          <span className="card-meta">{plural(report.failure_details.length, 'row')} · UOIR sheet</span>
        </div>
        {report.failure_details.length ? (
          <div className="table-scroll">
            <table className="data-table failure-details-table">
              <thead>
                <tr>
                  {FAILURE_DETAILS_COLUMNS.map((col) => (
                    <th key={col.key} scope="col" className={`col-${col.key}`}>
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.failure_details.map((row) => (
                  <tr key={row.source_row}>
                    {FAILURE_DETAILS_COLUMNS.map((col) => (
                      <td key={col.key} className={`col-${col.key} multiline`}>
                        {row[col.key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={ClipboardList} title="No failure details" compact>
            No UOIR rows were found. See Data checks for what to fix.
          </EmptyState>
        )}
      </section>

      <section className="gt-card table-card" aria-labelledby="team-title">
        <div className="table-card-head">
          <h2 id="team-title" className="card-title">
            Team Members
          </h2>
          <span className="card-meta">{plural(report.team.length, 'member')} · Team Member sheet</span>
        </div>
        {report.team.length ? (
          <div className="table-scroll">
            <table className="data-table team-table">
              <thead>
                <tr>
                  {TEAM_COLUMNS.map((col) => (
                    <th key={col.key} scope="col" className={`col-${col.key}`}>
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.team.map((member) => (
                  <tr key={member.source_row}>
                    {TEAM_COLUMNS.map((col) => (
                      <td key={col.key} className={`col-${col.key} multiline`}>
                        {member[col.key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={Users} title="No team members" compact>
            No team members were found on the Team Member sheet.
          </EmptyState>
        )}
      </section>
    </div>
  );
}
