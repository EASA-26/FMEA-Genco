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
 * An empty box is fine: the user chooses recipients in Outlook.
 */
export function parseRecipients(text) {
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
  return { recipients, error: '' };
}

/**
 * The recipient text sent to the server: the checked addresses joined with ";", which is
 * never longer than what was typed (so it stays within the length checked above).
 */
export function recipientsText(recipients) {
  return recipients.join(';');
}
