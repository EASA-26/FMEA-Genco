// SYNTHETIC placeholder PDF for mock mode. It stands in for the report the backend
// renders, so the preview frame can be checked without the server. One A4 page,
// built by hand with correct cross-reference offsets.

function ascii(text) {
  return String(text)
    .replace(/[^\x20-\x7E]/g, '?')
    .replace(/[\\()]/g, (ch) => `\\${ch}`);
}

export function buildMockPdf(report) {
  const lines = [
    ['F2', 26, 'SYNTHETIC mock PDF'],
    ['F1', 13, 'Placeholder for the FMEA report rendered by the backend.'],
    ['F1', 13, `Station : ${report ? report.station : '-'}`],
    ['F1', 13, `Date of Analysis : ${report ? report.analysis_date_text : '-'}`],
    ['F1', 13, `File : ${report ? report.pdf_filename : '-'}`],
  ];

  let y = 700;
  const text = lines
    .map(([font, size, value], i) => {
      const line = `BT /${font} ${size} Tf 1 1 1 rg 56 ${y} Td (${ascii(value)}) Tj ET`;
      y -= i === 0 ? 44 : 22;
      return line;
    })
    .join('\n');

  // Blue page with the cover gradient's first colour and a pale signature band.
  const stream = [
    '0.102 0.353 0.604 rg 0 0 595 842 re f',
    '0.957 0.969 0.984 rg 44 38 507 104 re f',
    text,
    'BT /F2 9 Tf 0.102 0.353 0.604 rg 58 118 Td (PREPARED BY / APPROVED BY - placeholder) Tj ET',
  ].join('\n');

  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>',
  ];

  let body = '%PDF-1.4\n';
  const offsets = [];
  objects.forEach((obj, i) => {
    offsets.push(body.length);
    body += `${i + 1} 0 obj\n${obj}\nendobj\n`;
  });
  const xrefStart = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  body += offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`).join('');
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF\n`;

  return new Blob([body], { type: 'application/pdf' });
}
