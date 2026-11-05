// The title and subtitle of the page on screen. They are shown only in the top bar
// (the title is the page's only h1); pages carry no heading of their own.

const SECTION_HEADINGS = {
  front: { title: 'Front Page', text: 'The cover of the report, as it will appear on the first page of the PDF' },
  intro: {
    title: 'Introduction',
    text: 'Failure details and the analysis team, exactly as written in the workbook',
  },
  analysis: { title: 'Analysis', text: 'The FMEA Analysis table and FMEA Summary counts for each UOIR' },
  recommendation: { title: 'Recommendation', text: 'Maintenance tasks for each UOIR, grouped by Equipment and KKS' },
};

/**
 * { title, subtitle } for the workspace's current step / report section.
 * `nav` is Workspace's { step, section }; `report` may be null (nothing uploaded).
 */
export function pageHeading(nav, report) {
  if (nav.step === 'done' && !report) {
    return { title: 'Report complete', subtitle: 'The workbook and report have been cleared from the app' };
  }
  if (nav.step === 'upload' || !report) {
    return { title: 'Upload the FMEA workbook', subtitle: 'Step 1 of 4 · Upload Excel' };
  }
  if (nav.step === 'preview') {
    return {
      title: 'Preview report',
      subtitle: `Step 3 of 4 · ${report.pdf_filename}, exactly as it will be exported`,
    };
  }
  if (nav.step === 'export') {
    return { title: 'Export PDF', subtitle: 'Step 4 of 4 · Download the finished report, or email it' };
  }
  const section = SECTION_HEADINGS[nav.section];
  if (section) return { title: section.title, subtitle: `Report section · ${section.text}` };
  return { title: 'Review data', subtitle: `Step 2 of 4 · What was read from ${report.source_filename}` };
}
