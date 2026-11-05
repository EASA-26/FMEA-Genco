// Recipient check for "Email the PDF", run in the browser before asking the server.
// It applies exactly the server's rules (parse_recipients in backend/mail/outlook.py,
// used by POST /api/report/email, which checks again) and gives the same messages:
//   - the typed text at most 2000 characters
//   - split on ; , and any whitespace or new line (JavaScript \s), drop empties
//   - each address: exactly one @, something before it, a domain with a dot and no
//     empty parts, at most 254 characters, and no spaces, control or format
//     characters (Unicode C* and Z*), double quotes, angle brackets, commas or
//     semicolons; an apostrophe is fine (o'name@...)
//   - de-duplicate ignoring case, keeping the first spelling; at most 20 addresses
// Lengths count characters (code points), as Python does.

export const MAX_RECIPIENTS = 20;
export const MAX_RECIPIENTS_TEXT = 2000;
const MAX_ADDRESS_LENGTH = 254;
const SHOWN_ADDRESS_LENGTH = 80;
const SEPARATORS = /[;,\s]+/u;
const FORBIDDEN = /[\s"<>,;\p{C}\p{Z}]/u;
const CONTROL_OR_SPACE = /[\s\p{C}\p{Z}]/u;

export const MSG_RECIPIENTS_TOO_LONG = `The list of email addresses is too long. Enter at most ${MAX_RECIPIENTS} addresses.`;
export const MSG_TOO_MANY_RECIPIENTS = `Enter at most ${MAX_RECIPIENTS} email addresses.`;
export const MSG_NO_RECIPIENTS = 'Enter at least one email address.';

function length(text) {
  return Array.from(text).length;
}

function isValidAddress(address) {
  if (!address || length(address) > MAX_ADDRESS_LENGTH || FORBIDDEN.test(address)) return false;
  const parts = address.split('@');
  if (parts.length !== 2) return false;
  const [local, domain] = parts;
  if (!local) return false;
  const labels = domain.split('.');
  return labels.length >= 2 && labels.every((label) => label.length > 0);
}

/** The address as quoted back in a message: printable and not too long (as on the server). */
function shown(address) {
  let chars = Array.from(address).map((ch) => (CONTROL_OR_SPACE.test(ch) ? '?' : ch));
  if (chars.length > SHOWN_ADDRESS_LENGTH) chars = [...chars.slice(0, SHOWN_ADDRESS_LENGTH - 3), '...'];
  return chars.join('');
}

export function invalidAddressMessage(address) {
  return `"${shown(address)}" is not a valid email address. Check it and try again.`;
}

/**
 * Parse what was typed in the Recipients box.
 * Returns { recipients: string[], error: string }; error is a plain message (empty when fine).
 * The server accepts no recipients (Outlook opens with an empty To line); the Export
 * step passes `required` because its Send button needs at least one address.
 */
export function parseRecipients(text, { required = false } = {}) {
  const raw = typeof text === 'string' ? text : '';
  if (length(raw) > MAX_RECIPIENTS_TEXT) return { recipients: [], error: MSG_RECIPIENTS_TOO_LONG };

  const seen = new Set();
  const recipients = [];
  for (const address of raw.split(SEPARATORS)) {
    if (!address) continue;
    if (!isValidAddress(address)) return { recipients: [], error: invalidAddressMessage(address) };
    const key = address.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    recipients.push(address);
  }
  if (recipients.length > MAX_RECIPIENTS) return { recipients: [], error: MSG_TOO_MANY_RECIPIENTS };
  // Only separators typed (e.g. ";"): nothing to send to.
  if (required && recipients.length === 0) return { recipients: [], error: MSG_NO_RECIPIENTS };
  return { recipients, error: '' };
}

/**
 * The recipient text sent to the server: the checked addresses joined with ";", which is
 * never longer than what was typed (so it stays within the length checked above).
 */
export function recipientsText(recipients) {
  return recipients.join(';');
}

// --------------------------------------------------------------------------- //
// Fallback when Outlook cannot open a draft (new Outlook, or the app is not on this PC):
// the browser downloads the PDF and opens a new email in the default mail app.
// A mailto: link can never carry an attachment, so the user attaches the PDF by hand.
// Subject and text match the server's email_subject / email_intro_html.
// --------------------------------------------------------------------------- //

const SUBJECT_PREFIX = 'FMEA Report';

/** Text made safe for one line: control and space characters become single spaces. */
function oneLine(text) {
  if (typeof text !== 'string') return '';
  return text.replace(/[\s\p{C}\p{Z}]+/gu, ' ').trim();
}

/** "FMEA Report - <station> - <date>"; missing parts are left out. */
export function emailSubject(station, analysisDateText) {
  return [SUBJECT_PREFIX, oneLine(station), oneLine(analysisDateText)].filter(Boolean).join(' - ');
}

/** Plain-text version of the server's introduction. */
export function emailBody(station, analysisDateText) {
  const stationText = oneLine(station);
  const dateText = oneLine(analysisDateText);
  let sentence = 'Please find attached the Failure Mode Effect Analysis (FMEA) report';
  if (stationText) sentence += ` for ${stationText}`;
  if (dateText) sentence += ` (Date of Analysis: ${dateText})`;
  return `Hello,\r\n\r\n${sentence}.\r\n\r\n`;
}

/** Percent-encode for a mailto: URL, keeping "@" readable (RFC 6068 allows either). */
function mailtoEncode(text) {
  return encodeURIComponent(text).replace(/%40/g, '@');
}

/**
 * mailto: link for a new email with the checked recipients, subject and text filled in.
 * Recipients come from parseRecipients, so they hold no separators, quotes or spaces.
 */
export function mailtoLink(recipients, station, analysisDateText) {
  const to = (recipients || []).map(mailtoEncode).join(',');
  const subject = mailtoEncode(emailSubject(station, analysisDateText));
  const body = mailtoEncode(emailBody(station, analysisDateText));
  return `mailto:${to}?subject=${subject}&body=${body}`;
}
