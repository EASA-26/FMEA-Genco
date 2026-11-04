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
//   ?mock_outlook=0           "Email the PDF" is not available (as on a hosted server)
//   ?mock_reset=1             forget the remembered mock session
// Sign in with any username; password "wrong" -> incorrect, "locked" -> too many attempts.
// Upload any .xlsx: a name containing "error" gives a report with blocking errors,
// "broken" gives an unreadable-workbook message, "slow" takes longer.
// Email the PDF: a recipient containing "outlook-fail" -> Outlook could not open,
// "outlook-busy" -> still opening the previous email; anything else opens "Outlook".
// In the browser console:
//   window.fmeaMock.expireSession()  ends the session so the next request gets 401
//                                    (the app should return to sign-in)
//   window.fmeaMock.closeWorkbook()  discards the report as another tab would, so the
//                                    next preview, download or email gets 404

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
  const state = { signedIn: Boolean(saved && saved.signedIn), authMode: saved && saved.authMode, variant: null, filename: null };
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

/** Adds blocking problems to the SYNTHETIC report: a UOIR without its tab and an empty required cell. */
function withErrors(report) {
  const sheet901 = report.uoirs[0].analysis.sheet;
  const row = report.uoirs[0].analysis.rows[3];
  row.cells[2] = '';
  report.uoirs[0].tasks[3].failure_effect = '';

  report.failure_details.push({
    no: '5',
    uoir_id: '904',
    title: 'SYNTHETIC - Ash conveyor belt misalignment trip',
    faulty_date: '2026-07-02',
    faulty_date_text: '2 July 2026',
    uoir_date: '2026-07-03',
    uoir_date_text: '3 July 2026',
    corrective_action: 'Realigned the belt and adjusted the tail pulley',
    preventive_action: 'Weekly belt tracking check',
    equipment: 'Ash Conveyor 3',
    source_row: 9,
  });
  report.uoirs.push({
    uoir_id: '904',
    title: 'SYNTHETIC - Ash conveyor belt misalignment trip',
    equipment: ['Ash Conveyor 3'],
    sheet_name: null,
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
      uoir_id: '901',
    },
    {
      severity: 'error',
      code: 'ANALYSIS_SHEET_MISSING',
      message: "No worksheet found for UOIR ID 904. Expected a tab named like 'UOIR ID 904 - Ash conveyor belt…'.",
      sheet: null,
      row: null,
      column: null,
      cell: null,
      uoir_id: '904',
    },
  );
  report.can_export = false;
  return report;
}

function currentReport() {
  if (!state.variant) return null;
  const report = clone(syntheticReport);
  if (state.filename) report.source_filename = state.filename;
  return state.variant === 'errors' ? withErrors(report) : report;
}

function json(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const empty = (status) => new Response(null, { status });

const features = () => ({ outlook_email: outlookEmail });

function errorCount(report) {
  return report.issues.filter((i) => i.severity === 'error').length;
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
        'Email through Outlook is only available when the app runs on your own computer. Download the PDF and attach it to an email instead.',
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
  state.variant = name.includes('error') ? 'errors' : 'ok';
  state.filename = file.name;
  return currentReport();
}

let pdfUrl = null;

/** Object URL of the placeholder PDF for the preview frame. */
export function mockPdfUrl() {
  if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  pdfUrl = URL.createObjectURL(buildMockPdf(currentReport()));
  return pdfUrl;
}
