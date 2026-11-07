// In-browser stand-in for the FMEA API, used only when VITE_MOCK=1 on the dev server.
// Everything it returns is SYNTHETIC (made-up station, people, staff numbers, UOIRs).
//
// One-time use, as in the real app: the report lives only in this page's memory, the
// workspace discards it when it opens, and a refresh starts again on Upload. Only the
// sign-in is remembered (sessionStorage) so a refresh does not sign you out.
//
// Handy switches while building screens:
//   ?mock_auth=databricks     no sign-in page (forwarded identity)
//   ?mock_signed_in=1         start signed in (local mode)
//   ?mock_outlook=0           no Outlook drafts: Export offers the mail-app fallback (as with the new Outlook)
//   ?mock_reset=1             forget the remembered mock session
// Sign in with any username; password "wrong" -> incorrect, "locked" -> too many attempts.
// Upload any .xlsx: a name containing "error" gives a report with blocking errors (one
// that can be accepted on Data Checks, one that cannot), "value-error" gives one whose
// errors can all be accepted (so it can be unblocked), "no-tabs" gives a workbook with no
// analysis tabs (blocking error, empty sections), "broken" gives an unreadable-workbook
// message, "slow" takes longer. Accept / Undo on Data Checks works as on the server and
// lasts until the next upload or discard.
// Email the PDF: a recipient containing "outlook-fail" -> Outlook could not open,
// "outlook-busy" -> still opening the previous email; anything else opens "Outlook".
// In the browser console:
//   window.fmeaMock.expireSession()  ends the session so the next request gets 401
//                                    (the app should return to sign-in)
//   window.fmeaMock.closeWorkbook()  discards the report as another tab would, so the
//                                    next preview, download, email or Accept gets 404

import syntheticReport from './synthetic-report.json';
import { buildMockPdf } from './mockPdf.js';
import { parseRecipients } from '../lib/email.js';

const STORE_KEY = 'fmea-mock-session';
const params = new URLSearchParams(window.location.search);

function loadState() {
  if (params.has('mock_reset')) sessionStorage.removeItem(STORE_KEY);
  let saved = null;
  try {
    saved = JSON.parse(sessionStorage.getItem(STORE_KEY) || 'null');
  } catch {
    saved = null;
  }
  const state = {
    signedIn: Boolean(saved && saved.signedIn),
    authMode: saved && saved.authMode,
    variant: null,
    filename: null,
    // The open report's id (new on every upload) and the ids of its accepted issues.
    reportId: '',
    accepted: new Set(),
  };
  if (params.get('mock_auth') === 'databricks') state.authMode = 'databricks';
  if (!state.authMode) state.authMode = 'local';
  if (params.has('mock_signed_in') || state.authMode === 'databricks') state.signedIn = true;
  return state;
}

const state = loadState();
const outlookEmail = params.get('mock_outlook') !== '0';
save();

window.fmeaMock = {
  expireSession() {
    state.signedIn = false;
    clearReport();
    save();
  },
  closeWorkbook() {
    clearReport();
  },
};

/** Remember only the sign-in; the report is never stored anywhere. */
function save() {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify({ signedIn: state.signedIn, authMode: state.authMode }));
  } catch {
    // Storage may be unavailable (private mode); the mock still works for this page.
  }
}

function clearReport() {
  state.variant = null;
  state.filename = null;
  state.reportId = '';
  state.accepted.clear();
}

/** A random 16-character hex token, like the server's report_id. */
function newReportId() {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

const clone = (value) => JSON.parse(JSON.stringify(value));
const wait = (ms, signal) =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    if (signal) {
      signal.addEventListener(
        'abort',
        () => {
          clearTimeout(timer);
          reject(new DOMException('Aborted', 'AbortError'));
        },
        { once: true },
      );
    }
  });

/**
 * Adds blocking problems to the SYNTHETIC report: an empty required cell (a value error,
 * which can be accepted), and an analysis tab whose table could not be read (structural,
 * which cannot; its section has no analysis and no summary).
 */
function withErrors(report) {
  const first = report.analyses[0];
  const sheet901 = first.analysis.sheet;
  const row = first.analysis.rows[3];
  row.cells[2] = '';
  first.tasks[3].failure_effect = '';

  const sheet906 = 'UOIR ID 906 - Ash conveyor belt';
  report.failure_details.push({
    no: String(report.failure_details.length + 1),
    uoir_id: '906',
    title: 'SYNTHETIC - Ash conveyor belt misalignment trip',
    faulty_date: '2026-07-02',
    faulty_date_text: '2 July 2026',
    uoir_date: '2026-07-03',
    uoir_date_text: '3 July 2026',
    corrective_action: 'Realigned the belt and adjusted the tail pulley',
    preventive_action: 'Weekly belt tracking check',
    equipment: 'Ash Conveyor 3',
    source_row: report.failure_details[report.failure_details.length - 1].source_row + 1,
  });
  report.uoir_ids.push('906');
  report.analyses.push({
    sheet_name: sheet906,
    uoir_ids: ['906'],
    title: 'SYNTHETIC - Ash conveyor belt misalignment trip',
    equipment: ['Ash Conveyor 3'],
    notes: [],
    analysis: null,
    tasks: [],
    summary: null,
    recommendations: [],
  });
  report.issues.unshift(
    {
      severity: 'error',
      code: 'REQUIRED_VALUE_BLANK',
      message: `Failure Effect is empty on row 6 of '${sheet901}'. Fill it in and upload again.`,
      sheet: sheet901,
      row: 6,
      column: 'Failure Effect',
      cell: 'C6',
      uoir_id: first.uoir_ids.join(', '),
    },
    {
      severity: 'error',
      code: 'ANALYSIS_HEADER_MISSING',
      message: `The analysis table was not found on '${sheet906}'. Expected a header row with 'Failure Mode' and 'RecommendedStrategy' within the first 15 rows.`,
      sheet: sheet906,
      row: null,
      column: null,
      cell: null,
      uoir_id: '906',
    },
  );
  return report;
}

/**
 * Adds value errors only, each of which can be accepted: a blank Failure Effect (row 5 of
 * the 901 tab), a New Task that is not Yes or No (row 6) and a blank Station. This is
 * the report that accepting its errors on Data Checks unblocks.
 */
function withValueErrors(report) {
  const first = report.analyses[0];
  const table = first.analysis;
  const sheet901 = table.sheet;
  const uoirId = first.uoir_ids.join(', ');
  const tableRow = (sourceRow) => table.rows.find((r) => r.source_row === sourceRow);
  const task = (sourceRow) => first.tasks.find((t) => t.source_row === sourceRow);

  tableRow(5).cells[table.columns.indexOf('Failure Effect')] = '';
  task(5).failure_effect = '';

  // Row 6 (an FF task, New Task "No" before) shows "Done" as written. As on the server,
  // it is left out of the Existing/New and Work-Centre counts and listed as not counted.
  tableRow(6).cells[table.columns.indexOf('New Task')] = 'Done';
  const done = task(6);
  done.new_task = 'invalid';
  done.new_task_raw = 'Done';
  const summary = first.summary;
  summary.task_executed_count -= 1;
  summary.strategy_rows.find((s) => s.code === done.strategy_code).existing -= 1;
  const centre = summary.work_centre_rows.find((w) => w.work_centre === done.trade);
  centre.total -= 1;
  centre.executed -= 1;
  summary.not_counted.push({
    source_row: 6,
    reason: 'New Task is not Yes or No',
    strategy: done.strategy_code,
    trade: done.trade,
  });
  for (const group of first.recommendations) {
    for (const row of group.rows) if (row.source_row === 6) row.new_task = 'invalid';
  }

  // With no station the file name says "Station", as on the server.
  report.station = '';
  report.pdf_filename = `FMEA_Report_Station_${report.analysis_date}.pdf`;

  report.issues.unshift(
    {
      severity: 'error',
      code: 'STATION_BLANK',
      message: "Station is empty (cell B2 on 'Team Member'). Fill it in and upload again.",
      sheet: 'Team Member',
      row: 2,
      column: null,
      cell: 'B2',
      uoir_id: null,
    },
    {
      severity: 'error',
      code: 'REQUIRED_VALUE_BLANK',
      message: `Failure Effect is empty on row 5 of '${sheet901}'. Fill it in and upload again.`,
      sheet: sheet901,
      row: 5,
      column: 'Failure Effect',
      cell: 'C5',
      uoir_id: uoirId,
    },
    {
      severity: 'error',
      code: 'NEW_TASK_INVALID',
      message: `New Task must be Yes or No, but row 6 of '${sheet901}' has 'Done'. Correct it and upload again.`,
      sheet: sheet901,
      row: 6,
      column: 'New Task',
      cell: 'S6',
      uoir_id: uoirId,
    },
  );
  return report;
}

/**
 * The SYNTHETIC workbook with no analysis tabs at all: no sections, and the blocking
 * ANALYSIS_SHEET_NONE error. The UOIR sheet and its issues stay; issues raised inside
 * the tabs go, and ANALYSIS_SHEET_MISSING is not raised alongside ANALYSIS_SHEET_NONE.
 */
function withoutTabs(report) {
  const tabNames = new Set(report.analyses.map((section) => section.sheet_name));
  report.analyses = [];
  report.issues = report.issues.filter(
    (issue) => !tabNames.has(issue.sheet) && issue.code !== 'ANALYSIS_SHEET_MISSING',
  );
  report.issues.unshift({
    severity: 'error',
    code: 'ANALYSIS_SHEET_NONE',
    message:
      "The workbook has no analysis tabs, so the report would have no FMEA Analysis. Add a tab named like 'UOIR ID 123 - Title of the UOIR' and upload again.",
    sheet: null,
    row: null,
    column: null,
    cell: null,
    uoir_id: null,
  });
  return report;
}

// Value errors that can be accepted (backend/config/mapping.py ACCEPTABLE_ERROR_CODES).
// Every warning can be accepted (marked as checked); no info and no other error can.
const ACCEPTABLE_ERROR_CODES = new Set([
  'REQUIRED_VALUE_BLANK',
  'NEW_TASK_INVALID',
  'UOIR_VALUE_BLANK',
  'STATION_BLANK',
  'ANALYSIS_DATE_BLANK',
  'ANALYSIS_DATE_INVALID',
]);

function isAcceptable(issue) {
  if (issue.severity === 'warning') return true;
  return issue.severity === 'error' && ACCEPTABLE_ERROR_CODES.has(issue.code);
}

/** Errors not accepted: they block preview and export. */
function errorCount(report) {
  return report.issues.filter((i) => i.severity === 'error' && !i.accepted).length;
}

function currentReport() {
  if (!state.variant) return null;
  let report = clone(syntheticReport);
  if (state.filename) report.source_filename = state.filename;
  if (state.variant === 'errors') report = withErrors(report);
  else if (state.variant === 'value-errors') report = withValueErrors(report);
  else if (state.variant === 'no-tabs') report = withoutTabs(report);

  // As the server does: the report's id, issue ids "1".. in report order, which can be
  // accepted, which are, and the export rule (no error left unaccepted).
  report.report_id = state.reportId;
  report.issues.forEach((issue, index) => {
    issue.id = String(index + 1);
    issue.acceptable = isAcceptable(issue);
    issue.accepted = state.accepted.has(issue.id);
  });
  report.can_export = errorCount(report) === 0;
  return report;
}

function json(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const empty = (status) => new Response(null, { status });

const features = () => ({ outlook_email: outlookEmail });

/**
 * POST /api/report/issues/acceptance: accept (or undo) issues of the open report and
 * return it. Refusals are checked in the server's order, with its messages; a refused
 * request changes nothing. Duplicate ids count once, and repeating a change is harmless.
 */
function mockAcceptance(init) {
  let body = null;
  try {
    body = JSON.parse(init.body || 'null');
  } catch {
    body = null;
  }
  const wellFormed =
    body !== null &&
    typeof body === 'object' &&
    typeof body.report_id === 'string' &&
    Array.isArray(body.ids) &&
    body.ids.every((id) => typeof id === 'string') &&
    typeof body.accepted === 'boolean';
  if (!wellFormed) return json(422, { detail: 'The request could not be completed. Please check and try again.' });

  const report = currentReport();
  if (!report) return json(404, { detail: 'No workbook uploaded yet.' });
  if (!body.report_id || body.report_id !== report.report_id) {
    return json(409, { detail: 'This workbook is no longer open here. Upload it again.' });
  }
  if (body.ids.length === 0) return json(400, { detail: 'Choose at least one item.' });
  if (body.ids.length > report.issues.length) return json(400, { detail: 'Too many items in one request.' });
  const byId = new Map(report.issues.map((issue) => [issue.id, issue]));
  const wanted = new Set(body.ids);
  if (![...wanted].every((id) => byId.has(id))) {
    return json(400, { detail: 'Some of these items are no longer in the report. Upload the workbook again.' });
  }
  if (![...wanted].every((id) => byId.get(id).acceptable)) {
    return json(400, { detail: "This item can't be accepted. Fix it in the workbook and upload again." });
  }

  for (const id of wanted) {
    if (body.accepted) state.accepted.add(id);
    else state.accepted.delete(id);
  }
  return json(200, currentReport());
}

let outlookBusy = false;

/** POST /api/report/email: pretend to open a new Outlook email with the PDF attached. */
async function mockEmail(init) {
  const report = currentReport();
  if (!report) return json(404, { detail: 'No workbook uploaded yet.' });
  if (!report.can_export) {
    return json(409, { detail: 'Fix the errors listed before previewing or exporting.', error_count: errorCount(report) });
  }
  if (!outlookEmail) {
    return json(501, {
      detail:
        'Outlook can only open the email here when the app runs on your own computer with the classic Outlook app. Download the PDF and attach it to an email instead.',
    });
  }
  let body = {};
  try {
    body = JSON.parse(init.body || '{}');
  } catch {
    body = {};
  }
  const { recipients, error } = parseRecipients(typeof body.to === 'string' ? body.to : '');
  if (error) return json(400, { detail: error });
  const joined = recipients.join(' ').toLowerCase();
  if (outlookBusy || joined.includes('outlook-busy')) {
    return json(429, { detail: 'Outlook is still opening the previous email. Please wait a moment.' });
  }
  outlookBusy = true;
  try {
    await wait(1400);
  } finally {
    outlookBusy = false;
  }
  if (joined.includes('outlook-fail')) {
    return json(502, {
      detail:
        'Outlook could not open a new email. Make sure Outlook is installed and signed in, or download the PDF and attach it yourself.',
    });
  }
  // eslint-disable-next-line no-console
  console.info(`[mock] Outlook would open a new email for ${recipients.length} recipient(s).`);
  return json(200, { status: 'opened', recipients, attachment: report.pdf_filename });
}

export async function mockFetch(path, init = {}) {
  const method = (init.method || 'GET').toUpperCase();
  const url = new URL(path, window.location.origin);
  await wait(url.pathname === '/api/report/pdf' ? 900 : 250, init.signal);

  if (url.pathname === '/api/auth/login' && method === 'POST') {
    if (state.authMode === 'databricks') return json(400, { detail: 'Sign-in is handled by Databricks.' });
    const body = JSON.parse(init.body || '{}');
    if (body.password === 'locked') {
      return json(429, { detail: 'Too many sign-in attempts. Please wait 5 minutes and try again.' });
    }
    if (!body.username || !body.password || body.password === 'wrong') {
      return json(401, { detail: 'Incorrect username or password.' });
    }
    state.signedIn = true;
    save();
    return json(200, { user: { name: body.username }, auth_mode: 'local', features: features() });
  }

  if (!state.signedIn) return json(401, { detail: 'Please sign in.' });

  if (url.pathname === '/api/auth/me') {
    const name = state.authMode === 'databricks' ? 'synthetic.engineer@example.com' : 'admin';
    return json(200, { user: { name }, auth_mode: state.authMode, features: features() });
  }
  if (url.pathname === '/api/auth/logout' && method === 'POST') {
    state.signedIn = false;
    clearReport();
    save();
    return empty(204);
  }
  if (url.pathname === '/api/report') {
    const report = currentReport();
    return report ? json(200, report) : json(404, { detail: 'No workbook uploaded yet.' });
  }
  if (url.pathname === '/api/workbook' && method === 'DELETE') {
    clearReport();
    return empty(204);
  }
  if (url.pathname === '/api/report/pdf') {
    const report = currentReport();
    if (!report) return json(404, { detail: 'No workbook uploaded yet.' });
    if (!report.can_export) {
      return json(409, { detail: 'Fix the errors listed before previewing or exporting.', error_count: errorCount(report) });
    }
    return new Response(buildMockPdf(report), { status: 200, headers: { 'Content-Type': 'application/pdf' } });
  }
  if (url.pathname === '/api/report/email' && method === 'POST') {
    return mockEmail(init);
  }
  if (url.pathname === '/api/report/issues/acceptance' && method === 'POST') {
    return mockAcceptance(init);
  }
  return json(404, { detail: 'Not found.' });
}

export async function mockUpload(file, { onProgress, signal } = {}) {
  const { ApiError } = await import('../api/client.js');
  if (!state.signedIn) throw new ApiError('Your session has ended. Please sign in again.', { status: 401 });

  const name = file.name.toLowerCase();
  const steps = name.includes('slow') ? 40 : 12;
  for (let i = 1; i <= steps; i += 1) {
    await wait(70, signal);
    if (onProgress) onProgress(i / steps);
  }
  await wait(name.includes('slow') ? 3000 : 900, signal);

  if (name.includes('broken')) {
    throw new ApiError('This file could not be opened as an Excel workbook. Save it as .xlsx in Excel and try again.', {
      status: 400,
    });
  }
  // "value-error" also contains "error", so it is checked first.
  if (name.includes('no-tabs')) state.variant = 'no-tabs';
  else if (name.includes('value-error')) state.variant = 'value-errors';
  else if (name.includes('error')) state.variant = 'errors';
  else state.variant = 'ok';
  state.filename = file.name;
  // A new report: a new id, and nothing accepted.
  state.reportId = newReportId();
  state.accepted.clear();
  return currentReport();
}

let pdfUrl = null;

/** Object URL of the placeholder PDF for the preview frame. */
export function mockPdfUrl() {
  if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  pdfUrl = URL.createObjectURL(buildMockPdf(currentReport()));
  return pdfUrl;
}
