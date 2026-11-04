import { useEffect, useMemo, useRef, useState } from 'react';
import { OctagonAlert, TriangleAlert, Copy } from 'lucide-react';
import { FLAG_HEADERS, cellColumnLetters, normaliseHeader } from '../lib/report.js';

// Column widths (px) by header, so the wide FMEA table reads like the workbook:
// short decision flags stay narrow, descriptive text gets room to wrap.
const WIDTHS = {
  flag: 46,
  no: 58,
  long: 230,
  task: 280,
  strategy: 166,
  frequency: 118,
  trade: 118,
  kks: 170,
  newtask: 92,
  medium: 170,
  blank: 110,
  other: 150,
};

function columnKind(header) {
  const key = normaliseHeader(header);
  if (!key) return 'blank';
  if (FLAG_HEADERS.has(key)) return 'flag';
  switch (key) {
    case 'no':
      return 'no';
    case 'failuremode':
    case 'failureeffect':
      return 'long';
    case 'task':
      return 'task';
    case 'recommendedstrategy':
      return 'strategy';
    case 'frequency':
      return 'frequency';
    case 'trade':
      return 'trade';
    case 'kks':
      return 'kks';
    case 'newtask':
      return 'newtask';
    case 'reviewtask':
    case 'remark':
    case 'maintenanceplanno':
      return 'medium';
    default:
      return 'other';
  }
}

/**
 * rowSpan/colSpan for each merge's top-left cell and the set of cells it covers.
 * The backend already clips merges to the table; this stays defensive so a bad
 * range can never shift cells: ranges outside the table are ignored, ranges are
 * clipped to it, and a range touching a cell already used by another merge is
 * skipped (its cells then render one by one).
 */
function mergeLayout(table) {
  const spans = new Map();
  const covered = new Set();
  const lastRow = table.rows.length - 1;
  const lastCol = table.columns.length - 1;

  for (const m of table.merged || []) {
    if (m.first_row > lastRow || m.first_col > lastCol || m.last_row < 0 || m.last_col < 0) continue;
    const r0 = Math.max(m.first_row, 0);
    const c0 = Math.max(m.first_col, 0);
    const r1 = Math.min(m.last_row, lastRow);
    const c1 = Math.min(m.last_col, lastCol);
    if (r1 < r0 || c1 < c0 || (r0 === r1 && c0 === c1)) continue;

    const cells = [];
    for (let r = r0; r <= r1; r += 1) {
      for (let c = c0; c <= c1; c += 1) cells.push(`${r}:${c}`);
    }
    if (cells.some((key) => covered.has(key) || spans.has(key))) continue;

    spans.set(cells[0], { rowSpan: r1 - r0 + 1, colSpan: c1 - c0 + 1 });
    for (const key of cells.slice(1)) covered.add(key);
  }
  return { spans, covered };
}

const TIP_WIDTH = 340;   // keep in step with .row-tip max-width in views.css

/** Screen-reader text for a row's check icon (the tooltip repeats it visually). */
function flagLabel(checks, duplicateOf) {
  const parts = (checks || []).map((issue) => issue.message);
  if (duplicateOf) parts.push(`Identical to row ${duplicateOf}; counted once.`);
  return parts.join(' ');
}

export default function AnalysisTable({ uoir, issues, focus }) {
  const table = uoir.analysis;
  const scrollRef = useRef(null);
  const [flash, setFlash] = useState(null);
  const [tip, setTip] = useState(null);   // { row, left, top, align } for the row-check tooltip

  const kinds = useMemo(() => table.columns.map(columnKind), [table]);
  const { spans, covered } = useMemo(() => mergeLayout(table), [table]);
  const tableWidth = 64 + kinds.reduce((sum, kind) => sum + WIDTHS[kind], 0);

  // Checks per Excel row, shown as an icon in the row gutter; hovering or
  // focusing the icon shows the messages, so the row itself explains what is wrong.
  const rowIssues = useMemo(() => {
    const byRow = new Map();
    for (const issue of issues) {
      if (!issue.row || issue.sheet !== table.sheet || issue.severity === 'info') continue;
      const list = byRow.get(issue.row);
      if (list) list.push(issue);
      else byRow.set(issue.row, [issue]);
    }
    return byRow;
  }, [issues, table.sheet]);
  const duplicates = useMemo(
    () => new Map(uoir.tasks.filter((t) => t.is_duplicate).map((t) => [t.source_row, t.duplicate_of_row])),
    [uoir.tasks],
  );

  // Bring a row (and cell) picked in Data checks into view and highlight it briefly.
  useEffect(() => {
    if (!focus || !scrollRef.current) return undefined;
    const letters = cellColumnLetters(focus.cell);
    const colIndex = letters ? table.column_letters.indexOf(letters) : -1;
    setFlash({ row: focus.row, col: colIndex });
    const frame = requestAnimationFrame(() => {
      const root = scrollRef.current;
      if (!root) return;
      const target =
        (colIndex >= 0 && root.querySelector(`[data-row="${focus.row}"] [data-col="${colIndex}"]`)) ||
        root.querySelector(`[data-row="${focus.row}"]`);
      if (target) target.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
    });
    const timer = setTimeout(() => setFlash(null), 3200);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
    };
  }, [focus, table]);

  const showTip = (sourceRow, element) => {
    const box = element.getBoundingClientRect();
    const roomOnRight = window.innerWidth - box.right;
    const align = roomOnRight < TIP_WIDTH + 24 ? 'left' : 'right';
    setTip({
      row: sourceRow,
      left: align === 'right' ? box.right + 10 : Math.max(12, box.left - TIP_WIDTH - 10),
      top: Math.min(box.top, window.innerHeight - 40),
      align,
    });
  };
  const hideTip = () => setTip(null);

  return (
    <div
      className="table-scroll analysis-scroll"
      ref={scrollRef}
      tabIndex={0}
      aria-label={`FMEA Analysis table for UOIR ID ${uoir.uoir_id}`}
      onScroll={hideTip}
    >
      <table className="grid-table analysis-table" style={{ width: tableWidth }}>
        <colgroup>
          <col style={{ width: 64 }} />
          {kinds.map((kind, i) => (
            <col key={i} style={{ width: WIDTHS[kind] }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <th scope="col" className="gutter">
              <span className="th-text">Row</span>
              <span className="col-letter">Excel</span>
            </th>
            {table.columns.map((header, i) => (
              <th key={i} scope="col" className={`kind-${kinds[i]}`}>
                <span className="th-text">{header || ' '}</span>
                <span className="col-letter">{table.column_letters[i]}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => {
            const checks = rowIssues.get(row.source_row);
            const mark = !checks ? undefined : checks.some((i) => i.severity === 'error') ? 'error' : 'warning';
            const duplicateOf = duplicates.get(row.source_row);
            const flashRow = flash && flash.row === row.source_row;
            return (
              <tr
                key={row.source_row}
                data-row={row.source_row}
                className={`${flashRow ? 'is-flash' : ''} ${duplicateOf ? 'is-duplicate' : ''}`}
              >
                <th scope="row" className={`gutter ${mark ? `gutter-${mark}` : ''}`}>
                  <span className="gutter-inner">
                    {row.source_row}
                    {(mark || duplicateOf) && (
                      <button
                        type="button"
                        className="row-flag"
                        aria-label={flagLabel(checks, duplicateOf)}
                        aria-expanded={tip?.row === row.source_row}
                        onMouseEnter={(e) => showTip(row.source_row, e.currentTarget)}
                        onMouseLeave={hideTip}
                        onFocus={(e) => showTip(row.source_row, e.currentTarget)}
                        onBlur={hideTip}
                        onClick={(e) =>
                          tip?.row === row.source_row ? hideTip() : showTip(row.source_row, e.currentTarget)
                        }
                        onKeyDown={(e) => e.key === 'Escape' && hideTip()}
                      >
                        {mark === 'error' && <OctagonAlert size={13} className="sev-error" aria-hidden="true" />}
                        {mark === 'warning' && !duplicateOf && (
                          <TriangleAlert size={13} className="sev-warning" aria-hidden="true" />
                        )}
                        {duplicateOf && <Copy size={13} className="sev-warning" aria-hidden="true" />}
                      </button>
                    )}
                  </span>
                </th>
                {/* One cell per header column, so a short or long cells list can never shift the grid. */}
                {table.columns.map((_, c) => {
                  const key = `${r}:${c}`;
                  if (covered.has(key)) return null;
                  const span = spans.get(key);
                  const flashCell = flashRow && flash.col === c;
                  return (
                    <td
                      key={c}
                      data-col={c}
                      rowSpan={span ? span.rowSpan : undefined}
                      colSpan={span ? span.colSpan : undefined}
                      className={`kind-${kinds[c]} ${span ? 'is-merged' : ''} ${flashCell ? 'is-flash-cell' : ''}`}
                    >
                      {row.cells[c] ?? ''}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      {tip && (
        <div className={`row-tip row-tip-${tip.align}`} role="tooltip" style={{ left: tip.left, top: tip.top }}>
          <p className="row-tip-head">Row {tip.row}</p>
          {(rowIssues.get(tip.row) || []).map((issue, i) => (
            <p key={i} className="row-tip-line">
              {issue.severity === 'error' ? (
                <OctagonAlert size={13} className="sev-error sev-icon" aria-hidden="true" />
              ) : (
                <TriangleAlert size={13} className="sev-warning sev-icon" aria-hidden="true" />
              )}
              <span>
                {issue.message}
                {issue.column && <span className="row-tip-where">{issue.column}{issue.cell ? ` · ${issue.cell}` : ''}</span>}
              </span>
            </p>
          ))}
          {duplicates.get(tip.row) && (
            <p className="row-tip-line">
              <Copy size={13} className="sev-warning sev-icon" aria-hidden="true" />
              <span>Identical to row {duplicates.get(tip.row)}; counted once.</span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
