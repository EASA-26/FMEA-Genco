import { CircleCheck, CircleDashed, ListTree, OctagonAlert, Sparkles, TriangleAlert, Wrench } from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import Tabs from '../components/Tabs.jsx';
import UoirSelector from '../components/UoirSelector.jsx';
import UoirHeading from '../components/UoirHeading.jsx';
import { EmptyState } from '../components/Feedback.jsx';
import { issuesForUoir, matchesNewTaskTab, newTaskCounts, plural } from '../lib/report.js';

const EMPTY_TEXT = {
  yes: 'No rows in this UOIR have New Task = Yes.',
  no: 'No rows in this UOIR have New Task = No.',
  notset: 'Every row in this UOIR has New Task set.',
};

function NotSetTag({ row, task }) {
  if (row.new_task !== 'blank') {
    return (
      <span className="tag tag-error">
        <OctagonAlert size={13} aria-hidden="true" /> Not Yes or No{task && task.new_task_raw ? `: “${task.new_task_raw}”` : ''}
      </span>
    );
  }
  if (task && task.strategy_code === 'NSM') {
    return <span className="tag tag-neutral">NSM · not required</span>;
  }
  return (
    <span className="tag tag-warning">
      <TriangleAlert size={13} aria-hidden="true" /> Blank
    </span>
  );
}

function RecommendationGroup({ group, tab, tasksByRow }) {
  const showStatus = tab === 'notset';
  return (
    <section className="card rec-group" aria-label={group.heading}>
      <header className="rec-group-head">
        <h3 className="rec-group-title">{group.heading}</h3>
        <span className="card-meta">{plural(group.rows.length, 'row')}</span>
      </header>
      <div className="table-scroll">
        <table className="data-table rec-table">
          <colgroup>
            <col style={{ width: 64 }} />
            <col style={{ width: '32%' }} />
            <col />
            <col style={{ width: 150 }} />
            {showStatus && <col style={{ width: 190 }} />}
          </colgroup>
          <thead>
            <tr>
              <th scope="col" rowSpan={2} className="gutter-head">
                Row
              </th>
              <th scope="col" rowSpan={2}>
                Failure Mode
              </th>
              <th scope="colgroup" colSpan={2} className="th-group">
                Recommendations
              </th>
              {showStatus && (
                <th scope="col" rowSpan={2}>
                  New Task
                </th>
              )}
            </tr>
            <tr>
              <th scope="col" className="th-sub">
                Task
              </th>
              <th scope="col" className="th-sub">
                Frequency
              </th>
            </tr>
          </thead>
          <tbody>
            {group.rows.map((row) => (
              <tr key={row.source_row}>
                <td className="gutter-cell">{row.source_row}</td>
                <td className="multiline">{row.failure_mode}</td>
                <td className="multiline">{row.task}</td>
                <td className="multiline">{row.frequency}</td>
                {showStatus && (
                  <td>
                    <NotSetTag row={row} task={tasksByRow.get(row.source_row)} />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function RecommendationView({ report, uoir, onSelectUoir, tab, onTab }) {
  const header = (
    <PageHeader eyebrow="Review Data · Report section" title="Recommendation">
      Maintenance tasks for each UOIR, grouped by Equipment and KKS.
    </PageHeader>
  );

  if (!uoir) {
    return (
      <div className="view-recommendation">
        {header}
        <EmptyState icon={ListTree} title="No UOIRs found">
          The UOIR sheet did not list any UOIRs. See Data checks for what to fix.
        </EmptyState>
      </div>
    );
  }

  const counts = newTaskCounts(uoir);
  const activeTab = tab === 'notset' && counts.notSet === 0 ? 'yes' : tab;
  const tabs = [
    { id: 'yes', label: 'New Task = Yes', count: counts.yes, icon: Sparkles },
    { id: 'no', label: 'New Task = No', count: counts.no, icon: CircleCheck },
  ];
  if (counts.notSet > 0) tabs.push({ id: 'notset', label: 'New Task not set', count: counts.notSet, icon: CircleDashed });

  const groups = uoir.recommendations
    .map((group) => ({ ...group, rows: group.rows.filter((row) => matchesNewTaskTab(row, activeTab)) }))
    .filter((group) => group.rows.length > 0);
  const tasksByRow = new Map(uoir.tasks.map((task) => [task.source_row, task]));

  return (
    <div className="view-recommendation">
      {header}
      <UoirSelector report={report} value={uoir.uoir_id} onChange={onSelectUoir} variant="recommendation" />

      <section className="uoir-panel" aria-label={`UOIR ID ${uoir.uoir_id}`}>
        <UoirHeading uoir={uoir} issues={issuesForUoir(report.issues, uoir.uoir_id)} />
        {uoir.recommendations.length === 0 ? (
          <EmptyState icon={Wrench} title="No recommendations for this UOIR">
            Recommendations come from the analysis tab. It was not found or has no rows to show.
          </EmptyState>
        ) : (
          <>
            <div className="tabs-row">
              <Tabs tabs={tabs} value={activeTab} onChange={onTab} label="Filter by New Task" idPrefix="recommendation" />
              <span className="tabs-note">Tabs only filter this view. The PDF lists every row.</span>
            </div>
            <div
              id="recommendation-panel"
              role="tabpanel"
              aria-labelledby={`recommendation-tab-${activeTab}`}
              className="tab-panel rec-groups"
              key={`${uoir.uoir_id}-${activeTab}`}
            >
              {groups.length ? (
                groups.map((group, index) => (
                  <RecommendationGroup key={`${index}-${group.heading}`} group={group} tab={activeTab} tasksByRow={tasksByRow} />
                ))
              ) : (
                <EmptyState icon={Wrench} title="Nothing in this tab" compact>
                  {EMPTY_TEXT[activeTab]}
                </EmptyState>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
