import { ClipboardList, Users } from 'lucide-react';
import { EmptyState } from '../components/Feedback.jsx';
import { FailureDetailsTable, TeamTable } from '../components/IntroTables.jsx';
import { ReviewStepNav } from '../components/StepNav.jsx';
import { plural } from '../lib/report.js';

export default function IntroductionView({ report, counts, onBack, onNext }) {
  return (
    <div className="view-intro">
      <div className="page-actions">
        <ReviewStepNav counts={counts} onBack={onBack} onNext={onNext} />
      </div>

      <section className="gt-card table-card" aria-labelledby="failure-details-title">
        <div className="table-card-head">
          <h2 id="failure-details-title" className="card-title">
            Failure Details
          </h2>
          <span className="card-meta">{plural(report.failure_details.length, 'row')}</span>
        </div>
        {report.failure_details.length ? (
          <FailureDetailsTable rows={report.failure_details} />
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
          <span className="card-meta">{plural(report.team.length, 'member')}</span>
        </div>
        {report.team.length ? (
          <TeamTable rows={report.team} />
        ) : (
          <EmptyState icon={Users} title="No team members" compact>
            No team members were found in the workbook.
          </EmptyState>
        )}
      </section>
    </div>
  );
}
