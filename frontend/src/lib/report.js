// Small helpers for reading the Report JSON (backend/report/models.py) in the UI.
// Nothing here recalculates counts: the numbers on screen are the backend's, so the
// review screens, the preview and the exported PDF always agree.

/** "1 row" / "3 rows" */
export function plural(count, singular, pluralForm = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

export function countIssues(issues = []) {
  const counts = { error: 0, warning: 0, info: 0 };
  for (const issue of issues) {
    if (counts[issue.severity] !== undefined) counts[issue.severity] += 1;
  }
  return counts;
}

export function issuesForUoir(issues = [], uoirId) {
  return issues.filter((issue) => issue.uoir_id === uoirId);
}

/** Header key used by the workbook mapping: lowercase letters and digits only. */
export function normaliseHeader(text) {
  return String(text || '')
    .replace(/ /g, ' ')
    .toLowerCase()
    .replace(/[^0-9a-z]/g, '');
}

/** Short decision-diagram flag columns shown narrow and centred. */
export const FLAG_HEADERS = new Set(['h', 's', 'e', 'o', '1', '2', '3', 'h4', 'h5', 's4']);

/** Column letters of an Excel cell reference, e.g. "S9" -> "S". */
export function cellColumnLetters(cell) {
  const match = /^([A-Z]+)\d+$/i.exec(String(cell || '').trim());
  return match ? match[1].toUpperCase() : null;
}

export const FAILURE_DETAILS_COLUMNS = [
  { key: 'uoir_id', label: 'UOIR ID' },
  { key: 'title', label: 'Title' },
  { key: 'faulty_date_text', label: 'Faulty Date' },
  { key: 'uoir_date_text', label: 'UOIR ID Date' },
  { key: 'corrective_action', label: 'Corrective Action (CA)' },
  { key: 'preventive_action', label: 'Preventive Action (PA)' },
  { key: 'equipment', label: 'Equipment' },
];

export const TEAM_COLUMNS = [
  { key: 'no', label: 'No' },
  { key: 'name', label: 'Name' },
  { key: 'staff_no', label: 'Staff No' },
  { key: 'section', label: 'Section' },
];

/** Counts of recommendation rows per New Task filter tab. */
export function newTaskCounts(uoir) {
  const counts = { yes: 0, no: 0, notSet: 0 };
  for (const group of uoir.recommendations || []) {
    for (const row of group.rows) {
      if (row.new_task === 'yes') counts.yes += 1;
      else if (row.new_task === 'no') counts.no += 1;
      else counts.notSet += 1;
    }
  }
  return counts;
}

/**
 * Whether a row belongs to a New Task filter tab. Every row falls into exactly one
 * tab ("notset" takes anything that is not Yes or No), matching newTaskCounts, so
 * filtering can never hide a row from every tab.
 */
export function matchesNewTaskTab(row, tab) {
  if (tab === 'yes') return row.new_task === 'yes';
  if (tab === 'no') return row.new_task === 'no';
  return row.new_task !== 'yes' && row.new_task !== 'no';
}

/** "17 September 2026, 09:30" from an ISO datetime, or "" when missing. */
export function formatDateTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const day = date.getDate();
  const month = date.toLocaleString('en-GB', { month: 'long' });
  const time = date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return `${day} ${month} ${date.getFullYear()}, ${time}`;
}

export function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Location parts of an issue for display, e.g. ["Sheet 'UOIR'", "Row 7", ...]. */
export function issueLocation(issue) {
  const parts = [];
  if (issue.sheet) parts.push({ label: 'Sheet', value: issue.sheet });
  if (issue.row) parts.push({ label: 'Row', value: String(issue.row) });
  if (issue.column) parts.push({ label: 'Column', value: issue.column });
  if (issue.cell) parts.push({ label: 'Cell', value: issue.cell });
  return parts;
}

/** The UOIR section whose analysis tab an issue points into (for "Show in table"). */
export function issueTarget(report, issue) {
  if (!issue.uoir_id || !issue.row || !issue.sheet) return null;
  const uoir = report.uoirs.find((u) => u.uoir_id === issue.uoir_id);
  if (!uoir || !uoir.analysis || uoir.analysis.sheet !== issue.sheet) return null;
  const hasRow = uoir.analysis.rows.some((r) => r.source_row === issue.row);
  return hasRow ? uoir : null;
}
