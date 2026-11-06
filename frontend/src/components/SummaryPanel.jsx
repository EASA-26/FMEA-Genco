import { Suspense, lazy, useId, useState } from 'react';
import { ChartPie, CircleCheck, Copy, ListTree, TriangleAlert, Wrench } from 'lucide-react';
import { EmptyState } from './Feedback.jsx';
import Spinner from './Spinner.jsx';
import { plural } from '../lib/report.js';

// recharts is only needed on this tab, so it loads as its own chunk.
const StrategyPie = lazy(() => import('./StrategyPie.jsx'));

function StatCard({ icon: Icon, label, value, hint }) {
  return (
    <div className="gt-card stat-card">
      <div className="stat-head">
        <span className="icon-tile icon-tile-soft" aria-hidden="true">
          <Icon size={18} />
        </span>
        <span className="stat-label">{label}</span>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-hint">{hint}</div>
    </div>
  );
}

export default function SummaryPanel({ section, onShowChecks }) {
  const [active, setActive] = useState(null);
  // Tab names and joined IDs contain spaces, so the card headings get React ids.
  const evrId = useId();
  const wcId = useId();
  const s = section.summary;

  if (!s) {
    return (
      <EmptyState
        icon={ChartPie}
        title="No summary for this tab"
        actions={
          <button type="button" className="gt-btn-secondary" onClick={onShowChecks}>
            Open Data checks
          </button>
        }
      >
        The summary could not be worked out for this tab. See Data checks.
      </EmptyState>
    );
  }

  return (
    <div className="summary">
      <div className="stat-grid">
        <StatCard icon={ListTree} label="Failure Mode" value={s.failure_mode_count} hint="Rows in the analysis, exact duplicates counted once" />
        <StatCard icon={Wrench} label="Maintenance Task" value={s.maintenance_task_count} hint="Counted rows except NSM (No Schedule Maintenance)" />
        <StatCard icon={CircleCheck} label="Task Executed" value={s.task_executed_count} hint="Rows with New Task = No" />
      </div>

      <section className="gt-card summary-card" aria-labelledby={evrId}>
        <div className="summary-card-head">
          <h3 id={evrId} className="card-title">
            Existing vs Revised
          </h3>
          <span className="card-meta">Existing = New Task No · New = New Task Yes</span>
        </div>
        <div className="evr-grid">
          <figure className="pie-block">
            <figcaption className="pie-title">
              Recommended Strategy <span className="pie-total">{plural(s.pie_total, 'row')}</span>
            </figcaption>
            {s.pie.length ? (
              <>
                <div
                  className="pie-canvas"
                  role="img"
                  aria-label={`Pie chart of Recommended Strategy: ${s.pie
                    .map((slice) => `${slice.label} ${slice.count} (${slice.percent.toFixed(1)}%)`)
                    .join(', ')}`}
                >
                  <Suspense
                    fallback={
                      <div className="pie-loading">
                        <Spinner size={20} />
                      </div>
                    }
                  >
                    <StrategyPie slices={s.pie} activeIndex={active} onActiveChange={setActive} />
                  </Suspense>
                </div>
                <ul className="legend" aria-label="Recommended Strategy legend">
                  {s.pie.map((slice, index) => (
                    <li
                      key={slice.code || 'not-specified'}
                      className={active === index ? 'is-active' : ''}
                      onMouseEnter={() => setActive(index)}
                      onMouseLeave={() => setActive(null)}
                    >
                      <span className="swatch" style={{ background: slice.color }} aria-hidden="true" />
                      <span className="legend-label">{slice.label}</span>
                      <span className="legend-count">{slice.count}</span>
                      <span className="legend-pct">{slice.percent.toFixed(1)}%</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <EmptyState icon={ChartPie} title="No strategy values to chart." compact />
            )}
          </figure>

          <div className="table-scroll evr-table-wrap">
            <table className="data-table strategy-table">
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Strategy</th>
                  <th scope="col" className="num">
                    Existing
                  </th>
                  <th scope="col" className="num">
                    New
                  </th>
                </tr>
              </thead>
              <tbody>
                {s.strategy_rows.map((row) => (
                  <tr key={row.code || 'not-specified'} className={row.total === 0 ? 'is-zero' : ''}>
                    <td className="code-cell">
                      <span className="swatch" style={{ background: row.color }} aria-hidden="true" />
                      {row.code || '—'}
                    </td>
                    <td>{row.label}</td>
                    <td className="num">{row.existing}</td>
                    <td className="num">{row.new}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="gt-card summary-card" aria-labelledby={wcId}>
        <div className="summary-card-head">
          <h3 id={wcId} className="card-title">
            Work-Centre Execution
          </h3>
          <span className="card-meta">Executed = New Task No · Pending = New Task Yes</span>
        </div>
        {s.work_centre_rows.length ? (
          <div className="table-scroll">
            <table className="data-table wc-table">
              <thead>
                <tr>
                  <th scope="col">Work Centre</th>
                  <th scope="col" className="num">
                    Total
                  </th>
                  <th scope="col" className="num">
                    Executed
                  </th>
                  <th scope="col" className="num">
                    Pending
                  </th>
                </tr>
              </thead>
              <tbody>
                {s.work_centre_rows.map((row) => (
                  <tr key={row.work_centre}>
                    <td>{row.work_centre}</td>
                    <td className="num strong">{row.total}</td>
                    <td className="num">{row.executed}</td>
                    <td className="num">{row.pending}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={Wrench} title="No work-centre counts" compact>
            No counted rows have New Task set to Yes or No.
          </EmptyState>
        )}

        {(s.not_counted.length > 0 || s.duplicate_rows.length > 0) && (
          <ul className="count-notes">
            {s.not_counted.map((row) => (
              <li key={`nc-${row.source_row}`}>
                <TriangleAlert size={15} className="sev-warning" aria-hidden="true" />
                <span>
                  <strong>Not counted:</strong> row {row.source_row} ({[row.strategy, row.trade].filter(Boolean).join(', ') || 'no strategy or trade'}) — {row.reason}.
                </span>
              </li>
            ))}
            {s.duplicate_rows.map((rowNumber) => (
              <li key={`dup-${rowNumber}`}>
                <Copy size={15} className="sev-warning" aria-hidden="true" />
                <span>
                  <strong>Duplicate:</strong> row {rowNumber} is identical to an earlier row and was counted once.
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
