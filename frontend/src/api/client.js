// Thin client for the FMEA backend API (docs/CONTRACT.md section 4).
//
// Every failure becomes an ApiError carrying a plain-language message that can be
// shown to engineers as-is. Status codes, JSON and server internals never reach
// the screen. A 401 from any signed-in call notifies the app so it can return to
// the sign-in page.
//
// Mock mode (VITE_MOCK=1, development server only) routes every call to the
// SYNTHETIC mock server in src/mocks. The `import.meta.env.DEV` guard is replaced
// with `false` in production builds, so the mocks are dropped from the bundle.

/** Upload limit checked in the browser. The server enforces its own MAX_UPLOAD_MB. */
export const MAX_UPLOAD_MB = 20;
export const ACCEPTED_EXTENSIONS = ['.xlsx', '.xlsm'];

const MESSAGES = {
  network: 'The FMEA service could not be reached. Check your connection and try again.',
  badResponse: 'The server sent an unexpected reply. Please try again.',
  400: 'The request could not be completed. Please check and try again.',
  401: 'Your session has ended. Please sign in again.',
  403: 'You do not have access to this action.',
  404: 'Nothing was found for this request.',
  409: 'Fix the errors listed before previewing or exporting.',
  413: `This file is larger than the ${MAX_UPLOAD_MB} MB upload limit.`,
  429: 'Too many attempts. Please wait a few minutes and try again.',
  500: 'Something went wrong on the server. Please try again.',
  // The service itself is down or restarting (proxy / gateway replies).
  502: 'The FMEA service is not available right now. Please try again in a moment.',
  503: 'The FMEA service is not available right now. Please try again in a moment.',
  504: 'The FMEA service took too long to answer. Please try again in a moment.',
};

export class ApiError extends Error {
  constructor(message, { status = 0, network = false, data = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.network = network;
    this.data = data;
  }
}

let unauthorizedListener = null;

/** Register the handler called when a signed-in request gets 401. Returns an unsubscribe function. */
export function onUnauthorized(listener) {
  unauthorizedListener = listener;
  return () => {
    if (unauthorizedListener === listener) unauthorizedListener = null;
  };
}

function notifyUnauthorized() {
  if (unauthorizedListener) unauthorizedListener();
}

/** Server messages are plain language by contract; anything that looks technical is replaced. */
function plainMessage(detail, status) {
  if (typeof detail === 'string') {
    const text = detail.trim();
    const looksTechnical = /traceback|exception|stack|[{}<>]|\bat line\b/i.test(text);
    if (text && text.length <= 400 && !looksTechnical) return text;
  }
  if (MESSAGES[status]) return MESSAGES[status];
  return status >= 500 ? MESSAGES[500] : MESSAGES[400];
}

async function transport(path, init) {
  if (import.meta.env.DEV && import.meta.env.VITE_MOCK === '1') {
    const mock = await import('../mocks/mockServer.js');
    return mock.mockFetch(path, init);
  }
  return fetch(path, { credentials: 'same-origin', ...init });
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function request(path, { method = 'GET', json, signal, signedIn = true } = {}) {
  const headers = { Accept: 'application/json' };
  if (json !== undefined) headers['Content-Type'] = 'application/json';

  let response;
  try {
    response = await transport(path, {
      method,
      headers,
      body: json !== undefined ? JSON.stringify(json) : undefined,
      signal,
    });
  } catch (err) {
    if (err && err.name === 'AbortError') throw err;
    throw new ApiError(MESSAGES.network, { network: true });
  }

  if (response.ok) return response;

  const data = await readJson(response);
  if (response.status === 401 && signedIn) notifyUnauthorized();
  throw new ApiError(plainMessage(data && data.detail, response.status), { status: response.status, data });
}

async function requestJson(path, options) {
  const response = await request(path, options);
  const data = await readJson(response);
  if (data === null) throw new ApiError(MESSAGES.badResponse, { status: response.status });
  return data;
}

// --------------------------------------------------------------------------- //
// Auth
// --------------------------------------------------------------------------- //

/** Current user and auth mode. Throws ApiError with status 401 when not signed in. */
export function getMe() {
  return requestJson('/api/auth/me', { signedIn: false });
}

export function login(username, password) {
  return requestJson('/api/auth/login', { method: 'POST', json: { username, password }, signedIn: false });
}

export async function logout() {
  await request('/api/auth/logout', { method: 'POST', signedIn: false });
}

// --------------------------------------------------------------------------- //
// Workbook and report
//
// One-time use: the workbook is read in memory only and never saved. The report
// and its PDF exist only for the current page visit; the app discards them when
// it opens, when the page is left (pagehide) and when the user signs out.
// --------------------------------------------------------------------------- //

/** Shown when the server no longer holds the report this page was showing. */
export const WORKBOOK_CLOSED_MESSAGE =
  'This workbook is no longer open. It is closed when you sign out, refresh or leave the page, or open the app in another tab. Upload it again to continue.';

/** True when a report request failed because the session no longer holds a report (404). */
export function isWorkbookClosed(err) {
  return err instanceof ApiError && err.status === 404;
}

/** Discard the session's workbook, report and PDF. Nothing to discard (404) is fine. */
export async function discardWorkbook() {
  try {
    await request('/api/workbook', { method: 'DELETE' });
  } catch (err) {
    if (isWorkbookClosed(err)) return;
    throw err;
  }
}

/**
 * Best-effort discard while the page is being left (pagehide). `keepalive` lets the
 * request outlive the page; every error is swallowed because nobody is left to see it.
 */
export function discardWorkbookOnExit() {
  // The mock's report lives in this page's memory and goes away with it.
  if (import.meta.env.DEV && import.meta.env.VITE_MOCK === '1') return;
  try {
    fetch('/api/workbook', {
      method: 'DELETE',
      keepalive: true,
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    }).catch(() => {});
  } catch {
    // Leaving the page anyway; the server also forgets the report when the session ends.
  }
}

/**
 * Upload a workbook and resolve with the Report.
 * `onProgress(fraction)` reports the transfer (0..1); once it reaches 1 the server is reading the file.
 */
export async function uploadWorkbook(file, { onProgress, signal } = {}) {
  if (import.meta.env.DEV && import.meta.env.VITE_MOCK === '1') {
    const mock = await import('../mocks/mockServer.js');
    return mock.mockUpload(file, { onProgress, signal });
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/workbook');
    xhr.setRequestHeader('Accept', 'application/json');

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    };
    xhr.upload.onload = () => onProgress && onProgress(1);

    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        data = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (data && typeof data === 'object') resolve(data);
        else reject(new ApiError(MESSAGES.badResponse, { status: xhr.status }));
        return;
      }
      if (xhr.status === 401) notifyUnauthorized();
      reject(new ApiError(plainMessage(data && data.detail, xhr.status), { status: xhr.status, data }));
    };
    xhr.onerror = () => reject(new ApiError(MESSAGES.network, { network: true }));
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'));

    if (signal) {
      if (signal.aborted) {
        reject(new DOMException('Upload cancelled', 'AbortError'));
        return;
      }
      signal.addEventListener('abort', () => xhr.abort(), { once: true });
    }

    const form = new FormData();
    form.append('file', file, file.name);
    xhr.send(form);
  });
}

// --------------------------------------------------------------------------- //
// PDF
// --------------------------------------------------------------------------- //

export function pdfPath(download) {
  return `/api/report/pdf?download=${download ? 1 : 0}`;
}

/**
 * Ask the server to prepare the PDF and confirm it can be shown, without keeping the
 * bytes: once the response headers say "ok" the body is abandoned. The server caches
 * the rendered PDF, so the preview frame that loads next is fast. Errors (409, 500...)
 * arrive as ApiError with a plain message.
 */
export async function preparePdf() {
  const controller = new AbortController();
  const response = await request(pdfPath(false), { signal: controller.signal });
  controller.abort();
  return response.ok;
}

/** URL for the preview frame. In mock mode this is a local placeholder PDF. */
export async function previewSource() {
  if (import.meta.env.DEV && import.meta.env.VITE_MOCK === '1') {
    const mock = await import('../mocks/mockServer.js');
    return mock.mockPdfUrl();
  }
  return pdfPath(false);
}

/** Download the PDF and save it under `filename`. */
export async function downloadPdf(filename) {
  const response = await request(pdfPath(true));
  let blob;
  try {
    blob = await response.blob();
  } catch {
    throw new ApiError(MESSAGES.network, { network: true });
  }
  if (!blob || blob.size === 0) throw new ApiError(MESSAGES.badResponse, { status: response.status });

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || 'FMEA_Report.pdf';
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Give the browser time to start the download before releasing the file.
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

// --------------------------------------------------------------------------- //
// Email (Outlook on this computer)
// --------------------------------------------------------------------------- //

/**
 * Ask the server to open a new Outlook email with the PDF attached (the user presses
 * Send in Outlook). `to` may be empty. Resolves with
 * { status: "opened", recipients: [...], attachment: "<file name>" }.
 */
export function emailPdf(to) {
  return requestJson('/api/report/email', { method: 'POST', json: { to: typeof to === 'string' ? to : '' } });
}
