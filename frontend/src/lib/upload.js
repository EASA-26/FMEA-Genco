import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB } from '../api/client.js';

/** Checks done in the browser before uploading. Returns a plain message, or null when the file looks fine. */
export function checkWorkbookFile(file) {
  if (!file) return 'Choose a workbook to upload.';
  const name = file.name || '';
  const lower = name.toLowerCase();
  if (name.startsWith('~$')) {
    return 'This is a temporary Excel lock file (it starts with "~$"). Choose the workbook itself.';
  }
  if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    if (lower.endsWith('.xls')) {
      return 'This is an older .xls workbook. Open it in Excel, save it as .xlsx and upload it again.';
    }
    return 'Please upload an Excel workbook (.xlsx or .xlsm).';
  }
  if (file.size === 0) return 'This file is empty. Check that the workbook was saved and try again.';
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `This file is larger than the ${MAX_UPLOAD_MB} MB upload limit.`;
  }
  return null;
}
