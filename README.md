# FMEA Report Generator

**Open the app: [easa-26.github.io/FMEA-Genco](https://easa-26.github.io/FMEA-Genco/)**
(sign in with the account your administrator gave you; if nobody has used it
for a while, the first visit can take up to a minute while it wakes up).

A web app that turns an engineer's FMEA workbook (Excel) into the
**Failure Mode Effect Analysis (FMEA) Report** PDF. You upload the workbook,
review what the app read from it, preview the report and download the PDF.
Emailing the PDF is optional: on your own Windows computer with classic
Outlook, **Send via Outlook** opens a new email with the PDF already attached.

The app is **one-time use**. There is no database: the workbook is read in
memory and never saved, and the report, preview and PDF only last while you
have the page open. As the Upload step puts it: "Nothing is saved in this app.
Your workbook and report are cleared when you sign out or close this page."
(see [One-time use](#one-time-use)).

Accurate reading and counting is the main goal. The app never makes up data or
drops it without telling you, and it never counts a row twice. When something
in the workbook looks wrong, you get a plain-language message that names the
sheet, row and cell.

All examples in this document are SYNTHETIC (made up). None of them come from a
real station, person or plant record.

---

## Contents

1. [What the app does](#what-the-app-does)
2. [Features](#features)
3. [Project structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Local setup](#local-setup)
6. [Development mode](#development-mode)
7. [Running tests](#running-tests)
8. [How the workbook is read](#how-the-workbook-is-read)
9. [How the numbers are calculated](#how-the-numbers-are-calculated)
10. [Checks and messages](#checks-and-messages)
11. [The PDF](#the-pdf)
12. [Emailing the PDF](#emailing-the-pdf)
13. [Changing the workbook layout](#changing-the-workbook-layout)
14. [Deploying to Databricks Apps](#deploying-to-databricks-apps)
15. [Deploying to Render (public link)](#deploying-to-render-public-link)
16. [Security notes](#security-notes)
17. [Known limitations](#known-limitations)

---

## What the app does

```
Sign in  ->  1 Upload Excel  ->  2 Review Data  ->  3 Preview Report  ->  4 Export PDF  ->  Finish
```

1. **Upload Excel.** Drop an `.xlsx` or `.xlsm` workbook on the upload card, or
   browse for one. The workbook is read and checked straight away. Once it is
   read, the same card shows the file instead of the drop area: its name, the
   station, date and number of UOIRs (and any errors), a **Remove** button
   (trash-can icon) that discards it so you can pick another file, and
   **Proceed to Review Data**. The app stays on this step until you choose.
2. **Review Data.** What the app read from the workbook:
   - four fact cards: Station, Date of Analysis, number of UOIRs and number of
     team members;
   - a "Ready to export" or "Export blocked" banner;
   - the data checks (problems that must be fixed, things worth checking, and
     information);
   - a **Workbook data** panel with the actual data, so you can see it before
     the report preview: tabs **Team Members** (with Station and Date of
     Analysis), **Failure Details** and **Analysis** (one analysis tab at a
     time, with its notes and full table). It is **read-only**: to change anything, edit
     the workbook in Excel, remove it on the Upload step and upload it again.

   The sidebar's **Report sections** (Data Checks, Front Page, Introduction,
   Analysis, Recommendation) show each part of the report in more detail,
   including each analysis tab's summary and the recommendations. Under
   Analysis the sidebar lists one entry per analysis tab, showing its UOIR IDs
   (for example "901, 902") and title; hover over an entry to see the tab
   name. Review Data shows
   the values only and does not say which sheet or cell they came from: the
   fact cards, the Front Page, the Introduction and the Workbook data panel
   have no "sheet, cell" captions. (A data-check message still names the
   sheet, row and cell of the problem, so you can find it in Excel.)
3. **Preview Report.** The finished PDF is shown inside the page, **view
   only**. There is no download button on this step, and the browser's PDF
   viewer is asked to hide its own toolbar, so the PDF is downloaded once, on
   the next step.
4. **Export PDF.** **Download PDF** saves it with a standard file name.
   **Email the PDF (optional)** opens a new email for it: with classic Outlook
   on this PC, **Send via Outlook** attaches the PDF for you; otherwise the PDF
   is downloaded and you attach it by hand (see
   [Emailing the PDF](#emailing-the-pdf)). At the bottom right, **Upload
   another** clears the report and goes back to an empty Upload step, and
   **Finish** clears it and shows a short **Report complete** screen with a
   **Start a new report** button. Finish is offered only when the report can
   be exported. You stay signed in either way.

### Moving between the steps

Each step has its own **Back** and **Next** buttons, in a row at the top right
of the page (pages have no heading of their own: the page title is in the top
bar). Every Review Data page has them: Data Checks and each report section
(Front Page, Introduction, Analysis, Recommendation).

| Step | Back | Next |
|---|---|---|
| 1 Upload Excel | (none) | **Proceed to Review Data**, on the file card once the workbook is read |
| 2 Review Data (Data Checks and every report section) | **Upload Workbook** | **Preview Report** (locked while errors remain: "Fix 2 errors to preview") |
| 3 Preview Report | **Review Data** | **Export PDF Report** (locked while errors remain: "Fix 2 errors to export") |
| 4 Export PDF | **Preview Report** | (none: **Upload another** and, when the report can be exported, **Finish** at the bottom right) |

Going back keeps everything: Back from Review Data shows the Upload step with
the file card, not an empty drop area. Once a workbook is read, you can also
jump to any step from the **Workflow** list in the sidebar.

When the button you pressed (Back, Next, Proceed, Finish and so on) goes away
with its page, keyboard focus moves to the new page's title in the top bar, so
a screen reader reads out where you are.

If the PDF of this report has not been downloaded or emailed yet, **Upload
another** and **Finish** first ask "The PDF hasn't been downloaded or emailed
yet. When you continue, the report is cleared and can't be opened again."
Choose **Finish anyway** (or **Upload another anyway**), or **Cancel**. The app
remembers a download or email for as long as the report is open, so going Back
to Preview and Next again does not bring the question back. When the report has
blocking errors there is no finished report: only **Upload another** is
offered, and it acts straight away. While the report is being cleared
("Finishing…" / "Clearing the report…"), Download, the email form and Back are
locked too.

### Around every step

- **Top bar:** the page's title and a one-line subtitle (below), the check
  status (errors and warnings, or "Ready to export"; click to open Data
  Checks), and at the right the signed-in user with **Sign out**. With
  Databricks sign-in it says "Signed in with Databricks" and has no Sign out.
  There is no Export button in the top bar: exporting is step 4. A title or
  subtitle too long for the bar is cut with "…" and shown in full on hover. On
  narrow screens the title gets smaller, the check status moves to a second
  line, the user name is hidden and Sign out shrinks to its icon.
- **Sidebar:** the TNB GENCO · TED brandmark, then the product block: the FMEA
  app icon (a gear with a warning badge) in a small tile beside "FMEA Report",
  with "Failure Mode & Effects Analysis" underneath. Then the four steps, the
  report sections (once a workbook is read) and, at the bottom, the team that
  runs this process: **ALCM - Maintenance Strategy**. Once you are signed in,
  the app icon appears only here, never in the page itself.
- **The page:** no heading of its own. Its buttons (Back / Next and the like)
  sit in a row at the top right.
- **Stray files:** a file dropped anywhere outside the upload card is ignored.
  The browser does not open it, so you do not leave the page and lose the open
  workbook.

Each page's title and subtitle, as shown in the top bar:

| Page | Title | Subtitle |
|---|---|---|
| Upload Excel (and whenever no workbook is open, except after Finish) | Upload the FMEA workbook | Step 1 of 4 · Upload Excel |
| Review Data: Data Checks | Review data | Step 2 of 4 · What was read from *workbook file name* |
| Review Data: Front Page | Front Page | Report section · The cover of the report, as it will appear on the first page of the PDF |
| Review Data: Introduction | Introduction | Report section · Failure details and the analysis team, exactly as written in the workbook |
| Review Data: Analysis | Analysis | Report section · The FMEA Analysis table and FMEA Summary counts for each analysis tab |
| Review Data: Recommendation | Recommendation | Report section · Maintenance tasks for each analysis tab, grouped by Equipment and KKS |
| Preview Report | Preview report | Step 3 of 4 · *PDF file name*, exactly as it will be exported |
| Export PDF | Export PDF | Step 4 of 4 · Download the finished report, or email it |
| After Finish | Report complete | The workbook and report have been cleared from the app |

The workbook's file name is in the Step 2 subtitle, and the PDF's file name in
the Step 3 subtitle.

There is **no intermediate working file**. The upload is read in memory and
turned straight into report data. The review screens, the preview and the PDF
all come from that same data, so they always agree. Nothing is saved to disk
(the one exception is the short-lived copy of the PDF that **Send via
Outlook** hands to Outlook and deletes straight after) and nothing is written
back to your workbook. To change the report, fix the workbook in Excel, remove
it on the Upload step and upload it again.

### One-time use

The app keeps nothing between visits. There is no database and no file store.
In plain words, as the app says on the Upload step: "Nothing is saved in this
app. Your workbook and report are cleared when you sign out or close this
page." The sign-in page says the same: "Nothing is saved in this app.
Workbooks and reports are cleared when you sign out or close the page."

- The workbook you upload is read in memory only and **never saved**, on the
  server or anywhere else.
- The report, the preview and the PDF exist only for the **current page visit**
  while you are signed in. Moving between the app's own steps (Upload, Review
  Data and its sections, Preview, Export) keeps them.
- They are **discarded**, on the server too, when you:
  - sign out;
  - refresh the page;
  - close the tab or the browser;
  - go to another site;
  - open the app in another tab of the same browser (the new tab starts
    empty and closes the workbook of the first one);
  - press **Remove** on the Upload step, or **Upload another** or **Finish**
    on the Export step.
- Every visit starts on **Upload** with nothing open. To carry on later, upload
  the workbook again.
- If Remove, Upload another or Finish cannot reach the server, the report is
  kept and the app says so ("Not removed" / "Not cleared"); try again.
- If you press **Cancel** or leave the page while the workbook is still being
  read, nothing from that upload is kept.
- Closing another tab of the app that has no workbook open does not close the
  workbook you are working on.
- If a step finds that the workbook is gone (for example after you opened the
  app in another tab), the app returns to Upload with the message "This
  workbook is no longer open. It is closed when you sign out, refresh or leave
  the page, or open the app in another tab. Upload it again to continue."
- Download the PDF (or email it) before you leave the page. Once it is
  downloaded, the copy in your Downloads folder is yours to keep. Upload
  another and Finish remind you if you have not done either yet.

### Report structure

| # | Section | Page | Content |
|---|---|---|---|
| 1 | Cover | A4 portrait | "Failure Mode Effect Analysis (FMEA) Report", Station, Date of Analysis, blank PREPARED BY / APPROVED BY boxes |
| 2 | Introduction | A4 portrait | Failure Details table (one row per UOIR sheet row) and Team Members table |
| 3 | Analysis: FMEA Analysis (one per analysis tab) | A3 landscape | UOIR ID (every UOIR the tab covers, for example "901, 902"), Title, any notes, then the full analysis table exactly as in the tab |
| 4 | Analysis: FMEA Summary (one per analysis tab) | A4 portrait | Failure Mode / Maintenance Task / Task Executed cards, the Existing vs Revised pie and table, and the Work-Centre Execution table |
| 5 | Recommendation | A4 portrait | For each analysis tab, one table per KKS: Failure Mode, Task, Frequency |

Sections 3 and 4 repeat for every analysis tab, in the order its UOIRs are
listed on the UOIR sheet. A tab that covers several UOIRs gives one page pair,
not a pair for each UOIR.

---

## Features

- A guided four-step flow (Upload Excel, Review Data, Preview Report, Export
  PDF) with **Back** and **Next** buttons on every step (and on every Review
  Data page), and **Upload another** / **Finish** at the end. Each page's title
  and subtitle are in the top bar; the FMEA app icon sits in the sidebar.
- Upload by drag and drop or file browser. The browser checks the file type and
  size before sending it (it rejects `.xls` files, empty files and `~$` Excel
  lock files). After reading, the upload card shows the file with **Remove**
  and **Proceed to Review Data**.
- Reads the Team Member, UOIR and analysis sheets. Each analysis tab is a
  section of the report; the UOIR IDs in its name say which UOIRs it covers.
- Every check has a plain-language message with the sheet, row, column and
  cell. Errors block the preview and export; warnings and information do not.
  A **Show in table** button jumps to the row in question.
- A read-only **Workbook data** panel on Review Data (Team Members, Failure
  Details, Analysis tabs) shows the data itself before the report preview.
- Review screens for the Front Page, Introduction, Analysis and Recommendation:
  - the analysis table has a sticky header, horizontal scrolling, merged cells,
    and an extra "Row" column holding the Excel row number;
  - the summary uses the same colours as the PDF;
  - Recommendation has **New Task = Yes**, **New Task = No** and (only when
    needed) **New Task not set** filter tabs.
- A view-only PDF preview inside the page (no download there), then a
  one-click download on Export PDF with a standard file name.
- Optional **Email the PDF**: opens a new email with the recipients you typed.
  With classic Outlook on this PC, **Send via Outlook** attaches the PDF for
  you and checks that it is attached; with the new Outlook (or any other mail
  app) the PDF is downloaded and you attach it by hand. You check the email and
  press Send; the app never sends email itself.
- Counts follow fixed, documented rules: exact duplicate rows are counted once,
  non-breaking spaces count as blank, and merged cells are handled safely.
- The PDF has selectable text and embedded fonts, repeats table headers on
  every page, and splits tall rows and merged blocks cleanly.
- Two sign-in modes:
  - `local`: one username and password;
  - `databricks`: no login page; the user is identified by Databricks Apps.
- One-time use with no database: uploads, reports and PDFs are kept in memory
  for the current page visit only and never saved. (The only file ever written
  is a short-lived copy of the PDF for Outlook to attach; it is deleted right
  after.)
- A mock mode for frontend work with SYNTHETIC data and no backend.

---

## Project structure

```
app.py                      Starts the web server (reads HOST / PORT / DATABRICKS_APP_PORT)
start-app.bat               Windows: double-click to (re)start the app and open it in the browser
app.yaml                    Databricks Apps configuration (not used locally)
render.yaml                 Render configuration for the public link (not used locally)
requirements.txt            Runtime Python packages (pinned)
requirements-dev.txt        Test-only packages (pytest, httpx, PyMuPDF)
.env.example                Local settings template; copy to .env
pytest.ini                  Test settings
backend/
  settings.py               Settings from environment variables / .env
  config/mapping.py         Every sheet name, cell, header, code, strategy name and colour
  excel/reader.py           Opens the workbook in memory; cell text, merged cells, formulas
  excel/linking.py          Reads the UOIR IDs in "UOIR ID <id> ..." tab names; tab checks
  report/models.py          The Report data model shared by API, screens and PDF
  report/builder.py         build_report(): reads the sheets and runs every check
  report/summary.py         Counts, pie percentages, work centres, recommendations
  report/formatting.py      Dates, PDF file name, message helpers
  pdf/                      render_pdf(): cover, tables, pie chart, page layout (ReportLab)
  auth/                     Password hashing, sign-in rules, session cookie
  sessions/store.py         In-memory session store (report and cached PDF per session)
  api/                      Web endpoints (/api/...) and the in-memory upload reader
  mail/outlook.py           "Send via Outlook": opens a new classic-Outlook email with the PDF attached (Windows only)
  main.py                   Builds the FastAPI app, security headers, serves frontend/dist
  assets/                   Liberation Sans fonts and the logo used in the PDF
  tests/                    Automated tests (pytest)
frontend/
  src/                      React app (screens, views, components, styles, API client)
  src/styles/genco-theme.css  IZ's Genco Project Theme in plain CSS (tokens + gt- classes), reusable
  src/components/AppIcon.tsx  App icons; the FMEA one (gear + warning badge) is in the sidebar product block
  src/lib/pageHeading.js    Each page's title and subtitle, shown in the top bar
  public/favicon.svg        FMEA app icon (gear + warning triangle)
  src/mocks/                SYNTHETIC report and fake API for mock mode
  dist/                     Built frontend served by the backend (created by npm run build)
tools/
  check_outlook_script.py   Windows: PowerShell's parser checks the Outlook script (never runs it)
  hash_password.py          Prints an ADMIN_PASSWORD_HASH for a new password
  make_synthetic_workbook.py  Builds SYNTHETIC test workbooks (edge, clean, sample-like)
docs/CONTRACT.md            Detailed build contract (rules, API, PDF, frontend)
design-preview/             The approved front-page design reference
```

---

## Prerequisites

- **Python 3.11 or later.** Databricks Apps runs Python 3.11, so the code keeps
  to 3.11 syntax.
- **Node.js 20.19+ or 22.12+ (with npm).** You only need it to build or change
  the frontend. A built copy lives in `frontend/dist`. If that copy is up to
  date, you can run the app without Node.
- A modern browser (Edge, Chrome or Firefox) with a built-in PDF viewer for the
  preview.

---

## Local setup

Run all commands from the project root (the folder that holds `app.py`).

### Windows (PowerShell)

```powershell
# 1. Create and activate a virtual environment
py -3.11 -m venv .venv            # or: python -m venv .venv
.\.venv\Scripts\Activate.ps1
# If PowerShell refuses to run the script, allow it for this window only:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

# 2. Install the Python packages
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt   # only needed to run the tests

# 3. Create your local settings file
Copy-Item .env.example .env

# 4. Build the frontend (needs Node.js)
cd frontend
npm ci
npm run build
cd ..

# 5. Start the app
python app.py
```

### macOS / Linux

```bash
# 1. Create and activate a virtual environment
python3.11 -m venv .venv          # or: python3 -m venv .venv
source .venv/bin/activate

# 2. Install the Python packages
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt   # only needed to run the tests

# 3. Create your local settings file
cp .env.example .env

# 4. Build the frontend (needs Node.js)
(cd frontend && npm ci && npm run build)

# 5. Start the app
python app.py
```

### Start or restart with one double-click (Windows)

Day to day on Windows, double-click **`start-app.bat`** in the project folder
instead of typing the commands above. It:

1. uses `.venv` if it exists, otherwise the installed Python, and installs the
   Python packages only when some are missing;
2. rebuilds the frontend only when `frontend/dist` is missing or older than the
   frontend source (this needs Node.js; without it the last build is used);
3. stops the FMEA app if it is already running on the same port, so
   double-clicking it again is also how you restart the app. Any other program
   using that port is never stopped; the window names it instead;
4. starts the app and opens it in your default browser once it answers.

The window that opens is the server. Leave it open while you use the app, and
close it (or press `Ctrl+C`) to stop the app.

### Open the app and sign in

1. Open **http://127.0.0.1:8000** in your browser.
2. Sign in with the initial development account:
   - username: `admin`
   - password: `fmea26`

The server log shows a warning while this built-in password is in use. **Change
it before anyone else can reach the app.** To stop the server, press `Ctrl+C` in
its terminal.

### Change the password

1. Create a hash for the new password. The tool asks for the password twice and
   does not show it:

   ```
   python tools/hash_password.py
   ```

   It prints one line, for example:

   ```
   ADMIN_PASSWORD_HASH=scrypt$16384$8$1$<salt>$<key>
   ```

2. Paste that whole line into `.env`, replacing the commented-out
   `# ADMIN_PASSWORD_HASH=...` line. No quotes are needed.
3. Restart the app (`Ctrl+C`, then `python app.py`; or double-click
   `start-app.bat`).

Only the hash is stored, never the password itself. You can also change the
username with `ADMIN_USERNAME`. If the hash is not valid, the server logs an
error at startup and nobody can sign in.

### Settings

Settings come from environment variables. Locally they can also come from
`.env`; a real environment variable wins over `.env`.

| Setting | Default | Meaning |
|---|---|---|
| `AUTH_MODE` | `local` | `local` = username/password sign-in. `databricks` = identity from the Databricks Apps proxy (use only on Databricks). |
| `ADMIN_USERNAME` | `admin` | Sign-in name in `local` mode. |
| `ADMIN_PASSWORD_HASH` | built-in development hash | scrypt hash from `tools/hash_password.py`. |
| `SESSION_IDLE_MINUTES` | `60` | Sign a session out after this many idle minutes. |
| `MAX_SESSIONS` | `200` | Most sessions kept in memory; the least recently used is dropped first. |
| `MAX_UPLOAD_MB` | `20` | Largest workbook accepted by the server. |
| `COOKIE_SECURE` | `false` | Send the session cookie over HTTPS only. Set `true` whenever the app is served over HTTPS. |
| `SESSION_COOKIE_NAME` | `fmea_session` | Cookie name (letters, digits, `_`, `-`). An invalid name stops the app at startup. |
| `HOST` | `127.0.0.1` | Network address. `127.0.0.1` = this computer only. |
| `PORT` | `8000` | Port. `DATABRICKS_APP_PORT`, when set, takes priority. |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning` or `error`. |
| `OUTLOOK_EMAIL` | `auto` | **Send via Outlook** (PDF attached through classic Outlook). `auto` = offered only when the app runs on this computer (Windows, `AUTH_MODE=local` and `HOST` = `127.0.0.1`, `localhost` or `::1`) and classic Outlook is installed and in use (the "New Outlook" toggle off). `on` = always offered on Windows, without the Outlook check; Outlook opens on the computer running the server (a warning is logged when others can reach it). `off` = never offered. Whenever it is not offered, the page offers **Download PDF & open email** instead. Any other value stops the app at startup. |
| `FMEA_SAMPLE_WORKBOOK` | not set | Tests only: path to a workbook on your own machine for the opt-in smoke test (see [Running tests](#running-tests)). |

---

## Development mode

### Backend and frontend together

The Vite dev server reloads the page as soon as you edit a frontend file. It
forwards every `/api` call to the backend at `http://127.0.0.1:8000`, so
sign-in cookies work as they do in production.

```powershell
# Terminal 1 (project root, virtual environment active)
python app.py                     # must listen on port 8000

# Terminal 2
cd frontend
npm run dev                       # open the address it prints, usually http://localhost:5173
```

After frontend changes, run `npm run build` again so that `python app.py` on
its own serves the new version.

### Mock mode (no backend)

```powershell
cd frontend
npm run dev:mock                  # loads frontend/.env.mock, which sets VITE_MOCK=1
```

Mock mode serves a SYNTHETIC report from `frontend/src/mocks/` and fakes every
API call in the browser. It works only on the dev server; `npm run build` never
includes the mocks. As in the real app, the report lives only in the page: a
refresh starts again on Upload (only the mock sign-in is remembered). Useful
switches (all listed at the top of `frontend/src/mocks/mockServer.js`):

- `?mock_auth=databricks`: no sign-in page.
- `?mock_signed_in=1`: start signed in.
- `?mock_reset=1`: forget the remembered mock session.
- `?mock_outlook=0`: Outlook drafts are not offered, so the Export step shows
  **Download PDF & open email** instead of **Send via Outlook** (as on a
  hosted server).
- Sign in with any username. The password `wrong` gives the "incorrect" message
  and `locked` gives the "too many attempts" message.
- An upload whose file name contains `error` gives blocking errors, `no-tabs`
  gives a workbook with no analysis tabs, `broken` gives an unreadable-file
  message, and `slow` takes longer. Any other name gives the normal report
  (which has one analysis tab that covers two UOIRs).
- Email the PDF: a recipient containing `outlook-fail` gives the "Outlook could
  not open a new email" message, and `outlook-busy` the "still opening the
  previous email" message. Nothing is ever sent or opened in mock mode.
- In the browser console, `window.fmeaMock.expireSession()` ends the session
  (back to sign-in), and `window.fmeaMock.closeWorkbook()` discards the report
  as another tab would (the next preview, download or email shows the
  "Workbook closed" message).

---

## Running tests

```powershell
pip install -r requirements-dev.txt
python -m pytest                                        # whole suite
python -m pytest backend/tests/test_summary_counts.py   # one file
```

The tests use only SYNTHETIC (made-up) data: workbooks built in memory by
`tools/make_synthetic_workbook.py` and SYNTHETIC report objects. No engineer
workbook is needed, and none is kept in the project. There are three workbook
variants:

- `edge`: the awkward cases (merged cells, non-breaking-space blanks, duplicate
  rows, blocking errors and so on);
- `clean`: a small workbook with no messages at all;
- `sample`: a **sample-like** workbook with the sheets, layout and quirks of a
  full engineer workbook but entirely invented content (station "SYNTHETIC
  Station S9", UOIRs 712, 705 and 748). `backend/tests/test_excel_sample_workbook.py`
  and `backend/tests/test_e2e_report_consistency.py` check its expected results,
  through the parser, the API and the PDF. These tests always run.

To save one of those workbooks for a manual try:

```powershell
python tools/make_synthetic_workbook.py --variant clean SYNTHETIC_clean.xlsx
python tools/make_synthetic_workbook.py --variant edge SYNTHETIC_edge.xlsx
python tools/make_synthetic_workbook.py --variant sample SYNTHETIC_sample.xlsx
```

The PDF tests use PyMuPDF to inspect the generated PDFs. PyMuPDF is licensed
under AGPL, so it is a test-only package and is never deployed.

### Optional: check a real workbook on your own machine

`backend/tests/test_local_workbook_smoke.py` is an **opt-in** smoke test. It is
skipped unless `FMEA_SAMPLE_WORKBOOK` points at a workbook file. The file is
read where it is (never copied or saved), and the test checks only general
things, never the workbook's values: it opens, has a station and at least one
UOIR, gets a `FMEA_Report_....pdf` file name, can be exported exactly when there
are no errors, and renders to a PDF.

```powershell
$env:FMEA_SAMPLE_WORKBOOK = "D:\FMEA\workbook.xlsx"      # PowerShell
python -m pytest backend/tests/test_local_workbook_smoke.py
```

```bash
FMEA_SAMPLE_WORKBOOK=/data/fmea/workbook.xlsx python -m pytest backend/tests/test_local_workbook_smoke.py
```

Never copy values from a real workbook into tests, fixtures or documents.

### Email (Outlook) tests

`backend/tests/test_mail_outlook.py` and `backend/tests/test_api_email.py` use a
fake PowerShell runner, so the tests **never start PowerShell or Outlook**. On
Windows, a separate tool asks PowerShell to check the script's syntax (it only
parses the script and does not run it; Outlook is not started):

```powershell
python tools/check_outlook_script.py
```

---

## How the workbook is read

All of these rules live in `backend/config/mapping.py` (names, cells, headers,
codes) and `backend/report/builder.py` (checks).

### Mapping

| Sheet | Cell or header | Used for |
|---|---|---|
| `Team Member` | `B2` | **Station**: cover, page header, PDF file name |
| `Team Member` | `A2` (should contain "Station") | Layout check only |
| `Team Member` | `B3` | **Date of Analysis**: cover, PDF file name. Must be an Excel date or a readable text date. |
| `Team Member` | `A3` (should contain "Date of Analysis") | Layout check only |
| `Team Member` | Header row with `No`, `Name`, `Staff No`, `Section` | **Team Members** table |
| `UOIR` | Header row with `No`, `UOIR ID`, `Title`, `Date of fault`, `Date of UOIR`, `CA`, `PA`, `Equipment` | **Failure Details** table (shown as UOIR ID, Title, Faulty Date, UOIR ID Date, Corrective Action (CA), Preventive Action (PA), Equipment); the list of UOIRs; Equipment for recommendation headings |
| `UOIR ID <id> - <title>` tabs | `B1` | Title of a tab that covers several UOIRs (or an ID not on the UOIR sheet); for a one-UOIR tab it is only compared with the UOIR sheet title |
| `UOIR ID <id> - <title>` tabs | Header row containing `Failure Mode` and `RecommendedStrategy` | The **FMEA Analysis** table: every column and row, as written |
| analysis tab | `No.` | Row number only; ignored when deciding whether a row is blank or a duplicate |
| analysis tab | `Failure Mode` | Failure Mode count, Recommendation table (must not be empty) |
| analysis tab | `Failure Effect` | Must not be empty |
| analysis tab | `RecommendedStrategy` | Strategy code: Maintenance Task count, Existing vs Revised, pie (must not be empty) |
| analysis tab | `Task` | Recommendation table (must not be empty) |
| analysis tab | `Frequency` | Recommendation table (may be empty) |
| analysis tab | `Trade` | Work centre (must not be empty) |
| analysis tab | `KKS` | Recommendation grouping (must not be empty) |
| analysis tab | `New Task` | Yes/No: Existing/New, Task Executed, Executed/Pending |
| analysis tab | any other column (for example H, S, E, O, 1, 2, 3, H4, H5, S4, Review task, Maintenance Plan No, Remark) | Shown in the analysis table only |
| `Notifications`, `Sheet3` | (whole sheet) | Never opened |

**Finding sheets.** Sheet names match with surrounding spaces and upper/lower
case ignored. If `Team Member` or `UOIR` is missing, you get an error.

**Finding header rows.** The app looks for each header row within the first
**15 rows** of the sheet. Header names match with case, spaces and punctuation
ignored, so `Staff No.`, `staff no` and `StaffNo` are all the same header, and
so are `Recommended Strategy` and `RecommendedStrategy`. The report always
shows the header exactly as it is written in the workbook.

- **Team Member:** the header row needs `Name` and `Staff No`. `No` and
  `Section` must also exist.
- **UOIR sheet:** the header row needs `UOIR ID` and `Title`. The other six
  columns must also exist.
- **Analysis tab:** the header row needs `Failure Mode` and
  `RecommendedStrategy`. Every column in the mapping table above must exist
  except `No.`. The same mapped header must not appear twice.

**Text dates.** A date typed as text is accepted in these forms: `15/06/2026`,
`15-06-2026`, `15.06.2026`, `15-Jun-26`, `15-Jun-2026`, `15 June 2026`,
`15 Jun 2026`, `2026-06-15`. Dates are shown as "15 June 2026". On the UOIR
sheet, a date that can't be read is shown exactly as written, with a warning.

**Numbers as text.** Whole numbers lose Excel's ".0". A number format made only
of zeros (for example `00000000`) keeps the leading zeros, so a staff number
shows as `00001234`.

### Linking analysis tabs to UOIRs

Each analysis tab becomes **one section** of the report: one FMEA Analysis
page, one FMEA Summary page and one Recommendation block. A tab name can list
**several UOIR IDs**, so one tab can cover several UOIRs that are about the
same topic. Failure Details still has one row per UOIR sheet row.

Excel limits tab names to 31 characters, so a tab holds the UOIR IDs and only
part of the title. Examples (all SYNTHETIC):

| Tab name | UOIRs it covers |
|---|---|
| `UOIR ID 901 - Pump Trip due to` | 901 |
| `UOIR ID 901 902 - SYNTHETIC Pump trip` | 901 and 902 |
| `UOIR ID 901, 902 & 903 - Fan` | 901, 902 and 903 |
| `UOIR ID 901,902,903` | 901, 902 and 903 (the compact form saves room) |

- A tab is an analysis tab when its name starts with `UOIR ID`, then the ID
  digits, then anything else. Upper/lower case is ignored, the spaces are
  optional, and a `:`, `#` or `-` may follow `ID`.
- **The IDs in the name decide what a tab covers.** The first number is always
  an ID. A further number counts as an ID when it comes right after the
  previous ID, separated by spaces, commas or `&`, and it is a UOIR ID on the
  UOIR sheet. Reading stops at the first number or word that does not fit; the
  rest is the title part. So `UOIR ID 905 2 fans trip` covers 905 only (the 2
  is part of the title), and `132kV` is never an ID.
- A `-` is not a separator between IDs: in `UOIR ID 901 - 902 - Pump` only 901
  is read. If 902 is a UOIR that no tab names, you get the warning
  `UOIR_ID_NOT_READ` pointing at that name.
- IDs are compared with leading zeros ignored, so `0501` and `501` are the same
  UOIR, but `50` is not `501`.
- **Every analysis tab is read and checked**, including hidden tabs, tabs for
  an ID that is not on the UOIR sheet, and tabs that share an ID. An error
  inside any of them blocks export, so fix it or delete the tab.
- **A UOIR that no tab names** is only information (`ANALYSIS_SHEET_MISSING`).
  It is still in Failure Details, and it does not block the preview or export.
- **A tab whose ID is not on the UOIR sheet:** warning. The tab is **included**
  in the report.
- **One UOIR ID in two tabs:** warning. Both tabs are used.
- **A hidden tab:** warning. It is still included.
- **No analysis tab at all:** error (the report would have no FMEA Analysis).
- **A sheet named like an analysis tab but not readable as one**, for example
  `UOIR 901 - Fan` (no `ID`): warning, and the sheet is not in the report.
  Rename it, for example `UOIR ID 901 - Fan`.
- **The title of a section:**
  - A tab for **one listed UOIR** uses the UOIR sheet Title, as before. If that
    is empty, it uses `B1`, then the title part of the tab name.
  - Any other tab (several UOIRs, or an ID not on the UOIR sheet) uses `B1`
    first. If `B1` is empty, it uses the first non-empty UOIR sheet Title of the
    UOIRs it covers, then the title part of the tab name.
  - `B1` is not used as a title when it lies inside the table (header on row 1).
- The title part of the tab name is compared with `B1` and with the Title of
  every UOIR the tab covers. If it matches none of them anywhere in the text, you
  get a warning, but the tab is still used. The comparison ignores case, extra
  spaces and the characters Excel forbids in tab names (`[ ] : * ? / \`).
- For a one-UOIR tab, `B1` is also compared with the UOIR title (case and extra
  spaces ignored); if they differ you get a warning. This check is skipped when
  `B1` is empty, when the UOIR title is empty, or when `B1` lies inside the
  table. It is not made for tabs that cover several UOIRs.
- **Sections are in UOIR sheet order:** by the first UOIR on the sheet that the
  tab covers, then by tab order. Tabs for an ID not on the UOIR sheet come last.
- A UOIR ID listed on several rows of the UOIR sheet is **one UOIR** (every
  row still appears in Failure Details). Its different Equipment values are
  collected. The first non-empty Title is used; a different Title on a later
  row gives a warning.
- **Equipment in the Recommendation headings** is the Equipment values of every
  UOIR the tab covers, joined with " / ". A tab with no UOIR on the sheet has
  none, so its headings are just the KKS.

### Where each table ends

| Table | Data rows | End of the table |
|---|---|---|
| Team Members | Rows below the header | The first row where Name, Staff No and Section are all empty. A pre-filled `No` alone does not keep the list going. |
| UOIR list | Rows below the header | The first row where every mapped column except `No` is empty |
| Analysis table | Rows below the header | The first row where every cell from the first to the last header column is empty, not counting `No.` |

The analysis table's columns run from the first to the last filled header cell.
A column inside that range with an empty header is kept only if it holds data.

If rows with data appear **below** the empty row that ends a table, they are
not in the report. You get the warning `ROWS_AFTER_BLANK_ROW` asking you to
remove the empty rows in between. It is raised for:

- a team row with Name plus Staff No or Section;
- a UOIR row with UOIR ID plus Title;
- an analysis row with at least 3 of these filled: Failure Mode, Failure
  Effect, RecommendedStrategy, Task, Trade, KKS.

### Notes outside the table

Any non-empty cell of an analysis tab outside the table becomes a **Note**. The
table covers the header row to the last data row, first to last table column.
Notes appear as "Note : ..." lines above the table, in row order. `B1` (the
title) is never a note, and neither are row numbers pre-filled in the `No.`
column below the table.

### Blank cells and non-breaking spaces

A cell that holds only spaces, tabs, line breaks or **non-breaking spaces** is
empty. Inside text, a non-breaking space counts as a normal space, runs of
spaces become one space, and line breaks are kept. So a `No.` column filled with
non-breaking spaces reads as blank, and ` r-hardware` (with a leading
non-breaking space) is read as the code `R-HARDWARE`.

### Merged cells

- **In the displayed table,** a merged block is shown merged (in the app and in
  the PDF), and the cells it covers are empty.
- **For counts and checks,** a covered cell takes the merged value **only when
  the merge starts on a data row and the cell is in the same column as the
  merge's top-left cell** (the value carries *down* its own column). For
  example, Failure Mode merged over rows 3–5 gives all three rows that Failure
  Mode, and you get the information message `MERGED_CELLS_CARRIED`.
- Every other covered cell counts as **empty**. That includes a header merged
  down into the data, or a value merged sideways (for example Trade merged
  across KKS). This stops made-up values; the normal "is empty" error then
  points to the cell.
- The same rule applies to Team Member and UOIR sheet rows. Fixed cells (`A2`,
  `A3`, `B2`, `B3`, `B1`) are always read from the cell itself.

### Formulas

The app uses the **saved results** of formulas. It never calculates formulas and
never runs macros. If a formula cell has no saved result (for example a file
created by a script and never opened in Excel), you get a warning: open the file
in Excel, save it and upload again.

### Sheets that are ignored or not used

- `Notifications` and `Sheet3` are never opened, and they get no message.
- Every analysis tab is used.
- A sheet whose name starts with "UOIR" but cannot be read as an analysis tab
  (and is not the `UOIR` sheet) gets the warning `ANALYSIS_SHEET_NAME_UNREADABLE`.
- Any other sheet (including chart sheets) gets the information message
  "Sheet 'X' is not used in the report."
- If the name of a sheet that is not used holds the number of a UOIR that no
  analysis tab names (for example a misspelled `UIOR ID 902 - Pump`), that UOIR
  gets the warning `UOIR_ID_NOT_READ` pointing at the sheet, so the missing
  analysis is not overlooked.

---

## How the numbers are calculated

All counts are **per analysis tab**, from the rows of its analysis table. A
tab that covers several UOIRs has one set of counts. The number of UOIRs shown
in the app counts the different UOIR IDs on the UOIR sheet.

### Which rows count

Every analysis row counts once, **except an exact duplicate**: a row whose
every column (apart from `No.`) matches an earlier row of the same tab. For
the comparison, extra spaces are ignored but upper/lower case is not. A
duplicate row gets the warning `DUPLICATE_ROW` ("Row 9 is identical to row 6
and is counted once.") and is left out of every count and of the
Recommendation tables. It still appears in the analysis table.

A failure mode with several tasks counts once **per row**. Only exact
duplicates are dropped.

### The three cards

| Card | Rule |
|---|---|
| **Failure Mode** | Number of counted rows |
| **Maintenance Task** | Counted rows whose strategy is not `NSM` |
| **Task Executed** | Counted rows with New Task = **No** (an existing task already being executed) |

**New Task values.** `Yes`/`Y` means Yes and `No`/`N` means No; upper/lower
case and surrounding spaces don't matter. An empty cell means "not set".
Anything else is an error.

### Existing vs Revised

A table of strategy codes with **Existing** (New Task = No) and **New** (New
Task = Yes) counts:

1. The seven standard codes always appear, in this order, even with zero rows:
   OC, SR, SD, FF, NSM, R-SPARE, N/A.
2. Then any other code found, in the order it first appears.
3. Then a "Not specified" row, only if a counted row has no strategy.

Codes are read with spaces removed and in capitals, so `r-spare `, `R - SPARE`
and `R-Spare` are all `R-SPARE`.

| Code | Shown as | Colour |
|---|---|---|
| OC | OC - On Condition | `#2a78d6` |
| SR | SR - Schedule Restore | `#eb6834` |
| SD | SD - Schedule Discard | `#1baf7a` |
| FF | FF - Failure Finding | `#eda100` |
| NSM | NSM - No Schedule Maintenance | `#e87ba4` |
| R-SPARE | R-SPARE - Redesign Spare | `#008300` |
| N/A | Not Analysed | `#898781` |
| R-HARDWARE | R-HARDWARE - Redesign Hardware | `#4a3aa7` |
| R-SOFTWARE | R-SOFTWARE - Redesign Software | `#e34948` |
| R-PRO | R-PRO - Redesign Procedure | `#9085e9` |
| any other `R-` code, e.g. R-PUMP | R-PUMP - Redesign Pump (information message) | `#c3c2b7` (grey) |
| any other code, e.g. XYZ | XYZ (warning: check the spelling) | `#c3c2b7` (grey) |
| empty | Not specified (plus an error: the strategy is required) | `#c3c2b7` (grey) |

The same colours are used in the app and in the PDF.

### Pie chart ("Recommended Strategy")

- One slice per strategy row with at least one counted row. A slice counts
  **all** counted rows with that code, whatever their New Task value (NSM
  included).
- Percentages are rounded to one decimal place with the largest-remainder
  method, so the slices always add up to exactly **100.0%**. When remainders
  tie, the earlier slice gets the extra 0.1 (three equal slices show 33.4, 33.3
  and 33.3).
- The legend lists each slice's name, count and percentage. The PDF legend ends
  with a Total row; the app shows the total next to the chart title.
- With no counted rows, the pie is replaced by "No strategy values to chart."

### Work-Centre Execution

- Only counted rows with New Task = **Yes** or **No**.
- Grouped by Trade, with upper/lower case and extra spaces ignored. If
  different spellings are merged (`SYNMECH-A` and `synmech-a`), you get an
  information message. The name shown is the first spelling found.
- **Executed** = New Task No, **Pending** = New Task Yes, **Total** = Executed
  + Pending.
- Sorted by Total, largest first; ties keep the order of first appearance.
- An empty Trade shows as "Trade not specified" (and is also an error).

### Rows that are not counted

A counted row whose strategy is **not NSM** and whose New Task is **empty** or
**not Yes/No** is left out of Existing/New and Work-Centre Execution. It still
counts for Failure Mode and Maintenance Task, and for the pie. Each such row is
listed under the summary, for example:

> Not counted: row 6 (OC, SYNELEC-C) — New Task blank.

NSM rows normally leave New Task empty. That is expected, so they are not
listed and produce no message. If an NSM row does have Yes or No, you get a
warning and the row is counted by that value.

### Recommendation

- One block per analysis tab, in the section order above. Inside it, one table
  per **KKS**.
  Grouping ignores upper/lower case and extra spaces. Groups appear in order of
  first appearance, and rows keep workbook order.
- Every counted row is included (Failure Mode, Task, Frequency), whatever its
  New Task value. Duplicates are left out.
- Group heading: `<Equipment>, <KKS>`. Equipment is the Equipment values of every UOIR
  the tab covers, joined with " / ", for example "Pump A / Pump B, KKS-PUMP-A". If Equipment is
  empty, the heading is just the KKS.
- In the app, the tabs **New Task = Yes**, **New Task = No** and **New Task not
  set** only filter the screen. "Not set" holds every row that is not Yes or
  No, so each row is in exactly one tab. It appears only when such rows exist.
  NSM rows are tagged "NSM · not required". **The PDF always lists every row.**

### Worked example (SYNTHETIC)

UOIR 901, Equipment "SYNTHETIC Pump":

| Row | Failure Mode | Strategy | Trade | KKS | New Task |
|---|---|---|---|---|---|
| 3 | Seal leak | OC | SYNMECH-A | KKS-A | No |
| 4 | Seal leak | SR | SYNMECH-A | KKS-A | Yes |
| 5 | Bearing wear | NSM | SYNOPS-B | KKS-B | *(empty)* |
| 6 | Bearing wear | OC | SYNELEC-C | KKS-B | *(empty)* |
| 7 | Motor trip | R-SPARE | SYNELEC-C | KKS-B | Yes |
| 8 | Motor trip | R-SPARE | SYNELEC-C | KKS-B | Yes (same as row 7 in every column) |

- Row 8 is a duplicate of row 7, so the counted rows are 3–7.
- **Failure Mode 5**, **Maintenance Task 4** (all but NSM), **Task Executed 1**
  (row 3).
- Existing/New: OC 1/0, SR 0/1, SD 0/0, FF 0/0, NSM 0/0, R-SPARE 0/1, N/A 0/0.
- Pie (5 rows): OC 2 = 40.0%, SR 1 = 20.0%, NSM 1 = 20.0%, R-SPARE 1 = 20.0%.
- Work centres: SYNMECH-A total 2 (executed 1, pending 1); SYNELEC-C total 1
  (executed 0, pending 1). Row 6 (empty New Task) and the NSM row are left out.
- Under the summary: "Not counted: row 6 (OC, SYNELEC-C) — New Task blank." and
  "Row 8 is identical to an earlier row and was counted once."
- Recommendation: "SYNTHETIC Pump, KKS-A" (rows 3, 4) and
  "SYNTHETIC Pump, KKS-B" (rows 5, 6, 7).
- Messages: warning `NEW_TASK_BLANK` (row 6) and warning `DUPLICATE_ROW`
  (row 8).

---

## Checks and messages

Every message names the place in the workbook (sheet, row, column, cell) where
it can. The **Data Checks** screen groups them:

- **Must fix before export** (errors): preview and export are blocked until
  the workbook is fixed and uploaded again.
- **Please check** (warnings): the report can still be exported, but check
  these.
- **For information** (info): nothing to fix; this explains what the app did.
  Collapsed by default.

Messages are sorted errors first, then warnings, then information; within each
group, by sheet (tab order) and row.

### Errors (block export)

| Code | Plain meaning |
|---|---|
| `SHEET_MISSING` | The workbook has no `Team Member` or no `UOIR` sheet. |
| `STATION_BLANK` | Station (`Team Member` `B2`) is empty. |
| `ANALYSIS_DATE_BLANK` | Date of Analysis (`Team Member` `B3`) is empty. |
| `ANALYSIS_DATE_INVALID` | Date of Analysis is not a date the app can read. |
| `TEAM_HEADER_MISSING` | The team table header was not found, or one of No / Name / Staff No / Section is missing. |
| `UOIR_HEADER_MISSING` | The UOIR table header was not found, or one of its eight columns is missing. |
| `UOIR_VALUE_BLANK` | UOIR ID or Title is empty on a UOIR sheet row. |
| `UOIR_NONE` | No UOIR rows were found below the header. |
| `ANALYSIS_SHEET_NONE` | The workbook has no analysis tab at all, so the report would have no FMEA Analysis. |
| `ANALYSIS_HEADER_MISSING` | The analysis header row was not found, or a required column is missing. The table is still shown, but no counts are made. |
| `ANALYSIS_HEADER_DUPLICATE` | A mapped column (for example Task) appears twice in the header row. |
| `ANALYSIS_NO_ROWS` | The analysis tab has a header but no data rows. |
| `REQUIRED_VALUE_BLANK` | Failure Mode, Failure Effect, RecommendedStrategy, Task, Trade or KKS is empty on a row. |
| `NEW_TASK_INVALID` | New Task is something other than Yes, No, Y, N or empty. |

### Warnings (export allowed)

| Code | Plain meaning |
|---|---|
| `LABEL_UNEXPECTED` | `A2` / `A3` on Team Member no longer say "Station" / "Date of Analysis"; the layout may have changed. |
| `TEAM_EMPTY` | No team members were found below the header. |
| `ROWS_AFTER_BLANK_ROW` | Rows with data sit below the empty row that ends a table, so they are not in the report (a UOIR row below the gap is not in Failure Details). |
| `UOIR_DATE_NOT_DATE` | Date of fault or Date of UOIR is not a date; it is shown as written. |
| `UOIR_EQUIPMENT_BLANK` | Equipment is empty on a UOIR sheet row. |
| `UOIR_DUPLICATE_ID_CONFLICT` | The same UOIR ID is listed again with a different Title; the first Title is used. |
| `FORMULA_NO_VALUE` | A formula cell has no saved result, so it reads as empty. |
| `ANALYSIS_SHEET_TITLE_MISMATCH` | The tab name's title part matches neither `B1` nor the Title of any UOIR the tab covers; the tab is still used. |
| `ANALYSIS_TITLE_CELL_MISMATCH` | `B1` of a one-UOIR tab differs from the UOIR title. |
| `ANALYSIS_SHEET_HIDDEN` | The tab is hidden in Excel; it is still included. |
| `ANALYSIS_SHEET_UNLISTED` | A `UOIR ID <id>` tab's ID is not on the UOIR sheet; the tab is included in the report. |
| `ANALYSIS_SHEET_NAME_UNREADABLE` | A sheet looks like an analysis tab (its name starts with "UOIR") but is not named `UOIR ID` and a number, so it is not in the report. |
| `UOIR_ID_NOT_READ` | A UOIR that no tab names appears as a number in a tab or sheet name but was not read as one of its IDs (for example after a `-`, or in a misspelled name such as `UIOR ID 902`). |
| `UOIR_IN_SEVERAL_TABS` | A UOIR ID is named in two or more tabs; all of them are in the report. |
| `STRATEGY_UNKNOWN` | A strategy code is not known and does not start with `R-`; it is shown as written, so check the spelling. |
| `NEW_TASK_BLANK` | New Task is empty on a non-NSM row; the row is left out of Existing/New and Work-Centre counts. |
| `NSM_NEW_TASK_FILLED` | An NSM row has New Task Yes or No; it is counted by that value. |
| `DUPLICATE_ROW` | The row is identical to an earlier row and is counted once. |

### Information

| Code | Plain meaning |
|---|---|
| `SHEET_NOT_USED` | A sheet is not part of the report. |
| `ANALYSIS_SHEET_MISSING` | A UOIR on the UOIR sheet is not named in any analysis tab. It is only shown in Failure Details. Add its ID to the name of the tab that covers it if there is one. |
| `MERGED_CELLS_CARRIED` | Merged cells cover several data rows; the merged value is used for each row. |
| `STRATEGY_DERIVED_NAME` | An `R-` code not in the list gets the name "Redesign X". |
| `TRADE_SPELLING_MERGED` | Different spellings of one Trade are counted as one work centre. |

### Problems with the file itself

These messages appear on the Upload step, not in Data Checks, and nothing from
that file is kept. (While a workbook is open, the upload card shows that file
instead of the drop area; dropping another file on it only says "Remove the
current workbook first to upload a different one." A file dropped anywhere
else on the page is ignored, so the browser never opens it.) The browser runs the type
and size checks first, with similar wording; the server repeats them:

- "Please upload an Excel workbook (.xlsx or .xlsm)."
- "The file is larger than 20 MB. Please upload a smaller workbook." (the size
  follows `MAX_UPLOAD_MB`)
- "This file could not be opened as an Excel workbook. Save it as .xlsx in Excel
  and try again."
- "No file was received. Please choose an Excel workbook and try again." / "The
  upload did not finish. Please try again."

---

## The PDF

### Page order and sizes

1. **Cover**: A4 portrait. No page header or footer.
2. **Introduction**: A4 portrait. Failure Details, then Team Members.
3. For each analysis tab, in the section order above (one page pair per tab,
   even when it covers several UOIRs):
   - **Analysis: FMEA Analysis**: A3 landscape. "UOIR ID : 901, 902", "Title :
     ...", one "Note : ..." line per note, then the full analysis table.
   - **Analysis: FMEA Summary**: A4 portrait. The three cards, "Existing vs
     Revised" (pie with legend, then the Code / Strategy / Existing / New
     table), "Work-Centre Execution" (Work Centre / Total / Executed /
     Pending) and the not-counted / duplicate notes.
4. **Recommendation**: A4 portrait. It starts on a new page and then runs on:
   "UOIR ID <ids>: <title>" for each tab, then for each KKS group the heading and a table
   with a two-row header (Failure Mode | Recommendations: Task, Frequency).

### Header, footer and look

- Every page except the cover has the header **"FMEA Report · <Station>"**
  (small, top left, over a thin line). A very long station name is shortened
  with "…".
- The footer reads **"Page X of Y"** (bottom right). The cover counts as page 1.
- White, print-friendly pages with restrained blue. Table headers are blue
  with white bold text and are repeated on every page a table continues onto.
- The text is real text you can select and search, set in Liberation Sans (same
  letter widths as Arial), which is embedded in the file. Tick and cross
  symbols (✓ ✗) use the standard ZapfDingbats font.
- The PDF title is "Failure Mode Effect Analysis (FMEA) Report", and its
  subject is the station.

### Long content

- Long codes wrap at `/ - _` and similar break points. A word that is slightly
  too wide makes only that cell up to 20% smaller; longer words are broken
  between characters. Nothing runs outside its cell.
- A merged block small enough (up to 40% of a page) moves to the next page in
  one piece. A bigger block is split, and its value is repeated on the next
  page with "(cont.)".
- A row that does not fit in the space left moves to the next page. A row too
  tall for a whole page is split inside the row, and the continuation repeats
  the No. / Failure Mode with "(cont.)".
- If merged text is taller than a whole page, that one block is drawn unmerged
  so none of its text is lost.
- Headings are never left alone at the bottom of a page; they are kept with the
  table header and its first rows.
- A legend with dozens of strategies moves below the pie and continues on the
  next page.

### File name

```
FMEA_Report_<Station>_<YYYY-MM-DD>.pdf
```

- Spaces in the station name become `_`. Only letters, digits, `_` and `-` are
  kept, repeated `_` are merged, and `_` at either end is removed.
- A blank station becomes `Station`; a missing date becomes `undated`.
- Example: Station "SYNTHETIC Station #1", Date of Analysis 15 June 2026 →
  `FMEA_Report_SYNTHETIC_Station_1_2026-06-15.pdf`.

### Signature boxes

The cover's **PREPARED BY** and **APPROVED BY** boxes are always left blank for
signing on paper. The app never fills them.

---

## Emailing the PDF

On the **Export PDF** step, under the download card, the **Email the PDF
(optional)** card opens a new email for the report. Emailing is optional: you
can simply download the PDF. **The app never sends anything.** You check the
email and press **Send** yourself. It works in one of two ways, chosen
automatically:

| This computer has | Button | What happens |
|---|---|---|
| **Classic Outlook** in use, and the app runs on this PC | **Send via Outlook** | A new Outlook email opens with the recipients, subject and introduction filled in and **the PDF already attached** (below). Nothing is sent until you press Send in Outlook. |
| **New Outlook** (the "New Outlook" toggle is on), no classic Outlook, or the app runs on a server | **Download PDF & open email** | A new email opens in your default mail app with the recipients, subject and text filled in, and the PDF is saved to your Downloads folder. A mail link can never carry an attachment, so **the PDF is not attached: drag it into the email yourself**, then press Send. The card and the message after the click both say so. |

The new Outlook for Windows cannot be controlled by other programs, so the app
cannot attach the PDF there. The app checks which Outlook is in use each time
the page opens, so switching the "New Outlook" toggle takes effect after a
refresh, without restarting the app.

### How to use it

1. Fix any blocking errors first. The card only appears when the report can be
   exported.
2. Type the recipients in **Recipients**. The button stays disabled until
   something is typed; the hint under the box says "Enter at least one address
   to send. Separate several with a semicolon." (commas, spaces and new lines
   work too).
3. Click the button. With **Download PDF & open email**, the email opens in your
   mail app and the PDF is downloaded; the app then says "A new email opened in
   your mail app and <file name> was saved to your Downloads folder. The PDF is
   not attached yet: attach it to the email, then press Send." The rest of this
   section is about **Send via Outlook**, which shows "Opening Outlook…" while
   Outlook starts (a few seconds when Outlook was closed).
4. A new Outlook email opens with:
   - **To:** the addresses you typed;
   - **Subject:** `FMEA Report - <Station> - <Date of Analysis>`, for example
     `FMEA Report - SYNTHETIC Station #1 - 15 June 2026`;
   - a short introduction above your default Outlook signature: "Hello,
     Please find attached the Failure Mode Effect Analysis (FMEA) report for
     **SYNTHETIC Station #1** (Date of Analysis: 15 June 2026).";
   - the PDF attached under the report's file name.
5. The app shows "Outlook opened a new email with <file name> attached. Check
   it, then press Send in Outlook." Check the email, change anything you like,
   and press **Send** in Outlook.

The addresses are checked in your browser and again by the server:

- at least one address (typing only separators such as `;` gives "Enter at
  least one email address.");
- at most 20 addresses (and 2000 characters in all); repeats are dropped,
  ignoring upper/lower case;
- each one must look like `name@example.com`: one `@`, a dot in the part after
  it, at most 254 characters, and no spaces, invisible characters, double quotes
  (`"`), angle brackets, commas or semicolons inside it (an apostrophe, as in
  `o'name@example.com`, is fine);
- the message names the first address that is not valid.

### The PDF is always attached (Send via Outlook)

The Outlook script checks that the email really has the PDF: once straight
after attaching it, and again after the introduction has been put in. If the
PDF is missing, or any step fails, the script closes that half-made email
**without saving it** and the app shows "Outlook could not open a new
email...", with a **Download PDF & open email instead** button. So you are
never left with an Outlook email that is missing its PDF.

### When "Send via Outlook" is offered

- Only when the app runs on **your own Windows computer**, with the **classic
  Outlook** desktop app installed, signed in **and in use** (the "New Outlook"
  toggle off). It uses classic Outlook's automation interface, which the new
  Outlook for Windows and Outlook on the web do not offer. The app reads two
  registry values to decide: that classic Outlook is installed
  (`Outlook.Application`) and that `UseNewOutlook` under
  `HKCU\Software\Microsoft\Office\16.0\Outlook\Preferences` is not `1`.
- The `OUTLOOK_EMAIL` setting controls it (see [Settings](#settings)). With the
  default `auto` it is offered only with `AUTH_MODE=local` and `HOST` set to
  `127.0.0.1`, `localhost` or `::1`, that is, when your browser and Outlook are
  on the same PC, and only while classic Outlook is in use. `off` hides it. On
  Databricks, `app.yaml` sets `off`.
- `on` offers it on any Windows server **without** checking which Outlook is in
  use, and the email then opens in Outlook **on the computer running the
  server**, not on the user's computer. Use it only when those are the same PC.
  The server log shows a warning when `on` is used on a server others can reach.
- Whenever it is not offered, the card shows **Download PDF & open email**
  instead. If **Send via Outlook** fails, the error message has a **Download
  PDF & open email instead** button.

### Messages

| Message | What happened |
|---|---|
| "Outlook could not open a new email. Make sure Outlook is installed and signed in, or download the PDF and attach it yourself." | Outlook is missing, not signed in, refused the request, did not answer within 2 minutes, or the PDF could not be attached (that email is closed without saving). If Outlook asks whether to allow another program to use it, allow it; otherwise you get this message. Use **Download PDF & open email instead**. |
| "Enter at least one email address." | Only separators (such as `;`) were typed in Recipients. |
| "Outlook is still opening the previous email. Please wait a moment." | Only one email is opened at a time. Wait, then try again. |
| "Outlook can only open the email here when the app runs on your own computer with the classic Outlook app. Download the PDF and attach it to an email instead." | Outlook drafts are not available here (see above), for example after switching to the new Outlook while the page was open. Use **Download PDF & open email instead**. |
| Nothing opens after **Download PDF & open email** | No default mail app is set in Windows (Settings > Apps > Default apps > Email). The PDF is still downloaded; attach it to an email yourself. |
| "... is not a valid email address. Check it and try again." | Fix the address that is named. |
| "This workbook is no longer open. ..." | The workbook was discarded (see [One-time use](#one-time-use)). Upload it again. |

### What happens to the PDF

- To let Outlook attach it, the app writes the PDF into a new temporary folder
  (named `fmea-mail-…`, in the Windows temporary folder) and deletes that folder
  right after, whether Outlook succeeded or not. This is the only time the app
  writes anything to disk.
- Once attached, the PDF is part of the Outlook email. If you send it, or close
  the email and keep it as a draft, Outlook keeps that copy like any other
  attachment. Delete the draft if you decide not to send it. An email that
  failed half-way is closed by the app without saving, so it leaves no draft.
- The addresses you type are never written to the server log; only how many
  there were.

---

## Changing the workbook layout

If the engineers' workbook layout changes, edit **`backend/config/mapping.py`**.
It holds, in one place:

- sheet names (`TEAM_SHEET`, `UOIR_SHEET`, `IGNORED_SHEETS`) and the analysis
  tab name pattern (`ANALYSIS_SHEET_PATTERN`);
- fixed cells (`STATION_CELL`, `ANALYSIS_DATE_CELL`, `ANALYSIS_TITLE_CELL`, and
  the label cells);
- how far to search for header rows (`HEADER_SEARCH_ROWS`);
- column headers (`TEAM_COLUMNS`, `UOIR_COLUMNS`, `ANALYSIS_COLUMNS`), which
  columns identify the analysis header row, which columns must exist and which
  values must not be empty;
- the Failure Details labels used in the report;
- Yes/No spellings;
- strategy codes, names, the always-shown list and colours.

Change the **value**, not the key: for example, if the header "Trade" becomes
"Work Centre", set `"trade": "Work Centre"`. Header matching ignores case,
spaces and punctuation. The label words checked in `A2`/`A3` ("station", "date
of analysis") are in `backend/report/builder.py` (`_TEAM_LABELS`).

After a change:

1. Run `python -m pytest`, then upload a SYNTHETIC or real workbook and check
   the Data Checks screen.
2. Update `tools/make_synthetic_workbook.py` and the tests if the layout they
   build no longer matches.
3. Update `docs/CONTRACT.md` and this README.

---

## Deploying to Databricks Apps

On Databricks, users are already signed in to the workspace, so the app runs
with `AUTH_MODE=databricks`. There is **no login page**. The app takes each
user's identity from the `X-Forwarded-Email` header that the Databricks Apps
proxy adds (falling back to `X-Forwarded-Preferred-Username`, then
`X-Forwarded-User`).

### 1. Build the frontend first

The deployment does not build the frontend, so build it locally.
`frontend/dist` must exist in the folder you upload.

```powershell
cd frontend
npm ci
npm run build
cd ..
```

### 2. Check `app.yaml`

The provided `app.yaml`:

- runs `python app.py`;
- sets `HOST=0.0.0.0`, `AUTH_MODE=databricks` and `COOKIE_SECURE=true`;
- sets `SESSION_IDLE_MINUTES=60`, `MAX_SESSIONS=200`, `MAX_UPLOAD_MB=20` and
  `LOG_LEVEL=info`;
- sets `OUTLOOK_EMAIL=off`: a Databricks server has no Outlook, so users
  download the PDF and attach it to an email themselves.

The port comes from `DATABRICKS_APP_PORT`, which Databricks sets. Databricks
installs `requirements.txt` when it deploys.

**Secrets never go in `app.yaml`.** The admin password hash is only needed if
you switch the app to `AUTH_MODE=local`, which is not recommended on
Databricks. To do that:

1. Run `python tools/hash_password.py` locally.
2. Store the hash in a Databricks secret scope.
3. Add that secret to the app as a resource with the key `admin-password-hash`.
4. Uncomment the `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` entries at the end
   of `app.yaml`. The hash entry uses `valueFrom: 'admin-password-hash'`
   instead of `value`.

### 3. Upload and deploy

With the Databricks CLI configured for your workspace:

```bash
# Once: create the app
databricks apps create fmea-report

# Upload the project folder to the workspace
databricks sync . /Workspace/Users/<your.name@example.com>/fmea-report

# Deploy (and again after every change)
databricks apps deploy fmea-report --source-code-path /Workspace/Users/<your.name@example.com>/fmea-report
```

Then open the app from the Databricks **Apps** page and give the engineers
permission to use it.

Check what gets uploaded:

- **Databricks Apps accepts files of at most 10 MB each.** The app's own files
  are far smaller (the largest are the fonts, about 0.4 MB).
- `databricks sync` honours `.gitignore`, which excludes `.env`, `.venv/`,
  `frontend/node_modules/` and every `.xlsx` / `.xlsm` file, so local settings
  and engineer workbooks are not uploaded. Check the list of synced files the
  first time, and keep workbooks out of the project folder anyway.

### 4. Things to know

- **Run a single instance.** Sessions, reports and cached PDFs live in the
  memory of one process (one uvicorn worker). A restart or redeploy signs
  everyone out and clears their uploads; they upload again. Several instances
  would not share sessions.
- **One-time use applies here too.** Refreshing or leaving the page, or signing
  out, discards the user's workbook, report and PDF (see
  [One-time use](#one-time-use)).
- In Databricks mode each user can keep up to **5** sessions (browsers or
  devices). Starting a sixth ends that user's oldest one; other users are never
  affected.
- The app trusts the `X-Forwarded-*` identity headers only in Databricks mode.
  It must only be reachable through the Databricks proxy. Never run
  `AUTH_MODE=databricks` on a server people can reach directly.
- To check that the app is running, open `/api/health`, which returns
  `{"status":"ok"}`.

---

## Deploying to Render (public link)

[Render](https://render.com) runs the app from this GitHub repository and gives
it a public `https://….onrender.com` link. Anyone with the link sees the sign-in
page; only people with the password can use the app. `render.yaml` holds the
settings, and Render redeploys the app on every push to `main`.

**Before you start:** uploaded workbooks pass through Render's servers (outside
your company network). The app saves nothing, but check that this is allowed
for your data.

1. **Make your own password hash.** In a terminal in the project folder run
   `python tools/hash_password.py`, type a new password twice, and copy the
   printed `scrypt$…` value (without `ADMIN_PASSWORD_HASH=`). Never use the
   development password on a public server.
2. **Create the service.** Sign in at render.com with your GitHub account,
   choose **New → Blueprint**, pick this repository, and paste the hash when
   Render asks for `ADMIN_PASSWORD_HASH`. Click **Deploy Blueprint**.
3. **Check it.** When the deploy shows *Live*, open the link, sign in as `admin`
   with your new password, and run a SYNTHETIC workbook through to Export.
   `/api/health` returns `{"status":"ok"}`.
4. **Share it.** The public link is
   `https://easa-26.github.io/FMEA-Genco/`: a small page on the `gh-pages`
   branch, published by GitHub Pages (Settings → Pages → Deploy from a branch →
   `gh-pages` / root), that forwards visitors to the Render app
   (`https://fmea-genco.onrender.com`). Put it in the repository's
   **About → Website** box. If the Render link ever changes, update the link in
   `index.html` and `404.html` on the `gh-pages` branch.

Free plan limits: the app sleeps after 15 minutes without visitors, and the
next visit waits about a minute while it wakes; it has a small server (512 MB,
a tenth of a CPU), so building a PDF takes a few seconds longer than locally.
The "Email the PDF" Outlook option is off on Render; users download the PDF.
Render's proxy hides visitors' own addresses, so after five wrong passwords in
five minutes, sign-in pauses for five minutes for everyone.

To change the password later, run step 1 again and replace
`ADMIN_PASSWORD_HASH` in the Render dashboard (**Environment**), then redeploy.

---

## Security notes

- **Password.** Only an scrypt hash is stored (n=16384, r=8, p=1, 16-byte
  random salt), and it is compared in constant time. The built-in development
  password is for first use on your own computer only; replace it (see
  [Change the password](#change-the-password)). The server logs a warning while
  it is in use.
- **Sign-in limits.** After 5 failed sign-ins in 5 minutes for a username from
  one client, or 50 failed sign-ins from one client across all usernames,
  sign-in is refused for a while ("Too many sign-in attempts...", with a
  `Retry-After` header).
- **Session cookie.** A random 256-bit token in an `HttpOnly`, `SameSite=Lax`
  cookie, marked `Secure` when `COOKIE_SECURE=true` (always on Databricks).
  Sessions end on sign-out, after `SESSION_IDLE_MINUTES` without activity, or
  when the store is full (least recently used first). Signing in always starts
  a new session.
- **In memory only, one-time use.** There is no database. Uploads are streamed
  into memory and never written to a temporary file. Reports and PDFs live only
  in the session, for the current page visit: they are discarded when the app
  is opened again, when the page is refreshed, closed or left, on **Remove**,
  **Upload another** and **Finish**, and on sign-out, expiry, a new upload or a
  restart. The only exception is **Send via Outlook**, which writes the PDF
  into a new `fmea-mail-…` temporary folder just long enough for Outlook to
  attach it and always deletes the folder afterwards.
- **Email the PDF.** The app never sends email; **Send via Outlook** only asks
  classic Outlook on the same computer to show a new email. It runs a fixed
  PowerShell script (started by its full Windows path) and passes the
  addresses, subject, introduction and file path only through environment
  variables, so nothing a user types or a workbook contains can change what
  the script does. The script checks that the PDF is attached and, if anything
  fails, closes the half-made email without saving it. One email is opened at
  a time, and recipient addresses are never logged. With the default
  `OUTLOOK_EMAIL=auto`, Outlook drafts are off unless the app runs on the
  user's own Windows computer with classic Outlook in use. The **Download PDF
  & open email** fallback runs entirely in the browser: it opens a `mailto:`
  link (recipients, subject and text only; a mail link cannot carry the PDF)
  and downloads the PDF like the Download button; the server is not involved
  beyond serving the PDF.
- **No macros, no formulas, no links.** Workbooks are opened read-only with
  their saved values. Macros in `.xlsm` files are never run, formulas are never
  calculated, and external links are not followed.
- **Size limits.** Uploads above `MAX_UPLOAD_MB` are refused, early when the
  size is announced. Every other request body is limited to 64 KB.
- **Responses.** Errors are short plain messages with no stack traces (details
  go only to the server log). Security headers (`X-Content-Type-Options`,
  `Referrer-Policy`, `X-Frame-Options: SAMEORIGIN`) are set on every response,
  and API responses are not cached. The interactive API docs are turned off.
  Frontend file paths are checked name by name before the disk is touched.
- **CSRF.** There is no separate CSRF token. Protection relies on the
  `SameSite=Lax` cookie, JSON request bodies and same-origin requests. Keep the
  frontend and API on the same origin.
- **This computer only.** When the app runs locally (`AUTH_MODE=local` and
  `HOST` is `127.0.0.1`, `localhost` or `::1`, the default), it answers only to
  those addresses. A request sent under any other name, for example by a web
  page that points its own name at your computer, is refused ("This app only
  answers on this computer's own address..."), and so is a change (sign-in,
  upload, email) sent from a page on another address. This check is off when
  the app is shared on the network (`HOST=0.0.0.0`) or runs on Databricks.
- **Proxy headers.** `X-Forwarded-For` is honoured only in Databricks mode, so
  locally nobody can dodge the per-client sign-in limit by faking it.
- Never commit `.env` or engineer workbooks. `.gitignore` already excludes
  them.

---

## Known limitations

- **Python 3.11 not tested by running.** No Python 3.11 interpreter was
  available during development. The tests ran on Python 3.14, and 3.11
  compatibility was checked by parsing every file with Python 3.11 syntax rules
  (`ast.parse(feature_version=(3, 11))`). Run the test suite once on 3.11
  before relying on it.
- **Very wide tabs.** A tab with about 100 or more columns still renders, but
  the columns become too narrow to read in the PDF. The usual layout has 22
  columns.
- **Unknown strategy codes share one grey** (`#c3c2b7`). Two unknown codes next
  to each other in the pie can only be told apart by the legend and the thin
  white separator.
- **Unsupported characters.** Characters that neither Liberation Sans nor
  ZapfDingbats has (for example ⚠, ☐, Chinese/Japanese/Korean text, emoji)
  print as empty boxes in the PDF. ZapfDingbats is a standard PDF font and is
  not embedded.
- **Sessions are lost on restart**, and the app must run as **one worker / one
  instance**, because sessions live in memory.
- **Browser size check is fixed at 20 MB.** If you change `MAX_UPLOAD_MB`, the
  server enforces the new limit, but the browser still checks against 20 MB.
- **Two-row analysis headers** (a group header above the real headers) are not
  supported: the second header row is read as data and produces "is empty"
  errors.
- The `ROWS_AFTER_BLANK_ROW` check is a rule of thumb. A block of notes below
  the table that fills three or more of the required columns also triggers it
  (only a warning).
- A stray value far down a sheet (near row 1,048,576) makes reading that sheet
  about a second slower.
- PDF rendering takes about 6 ms per analysis row. Very large reports (thousands
  of rows) take several seconds; the PDF is then cached until the next upload.
- On some Windows PCs, `npm run build` stays open for about five minutes after
  it prints "built in ...". The build is already finished by then: Vite is
  waiting for a background `net use` lookup. You can press `Ctrl+C`, or use
  `start-app.bat`, which builds without that wait.
- The in-page preview needs the browser's built-in PDF viewer. If it is turned
  off, use "Open in new tab", or go on to Export PDF and download it.
- **Preview hides the PDF viewer's toolbar by request only.** The preview adds
  the standard PDF open parameters `#toolbar=0&navpanes=0`, and "Open in new
  tab" opens the same view-only address. A PDF viewer that ignores them still
  shows its own download and print buttons, and the browser's own save
  shortcut still works. The download meant to be used is the one on Export
  PDF.
- On narrow (tablet) screens, the side menu does not trap keyboard focus while
  it is open.
- **Use one tab at a time.** All tabs of one browser share one sign-in and one
  workbook. Opening the app in a second tab closes the first tab's workbook. If
  you then upload a workbook in the second tab and go back to the first tab
  without refreshing it, the first tab's Preview and Export would show the
  second tab's workbook.
- Discarding the workbook when you leave the page is best effort. If the
  browser crashes or the network drops at that moment, the server forgets it
  the next time you open the app, when you sign out, or after
  `SESSION_IDLE_MINUTES` without activity.
- **Send via Outlook** (PDF attached automatically) works only on Windows with
  classic Outlook in use, and only when the app runs on that same computer. With
  the new Outlook the app falls back to **Download PDF & open email**; a mail
  link can never carry an attachment, so there you attach the downloaded PDF
  yourself. Besides the automated tests and the PowerShell syntax check, the
  Outlook email has been tried on a PC with classic Outlook (test emails opened
  with the PDF attached). The introduction is placed above the default
  signature that Outlook adds when it shows the email.
- The **Workbook data** panel on Review Data is read-only. To correct the data,
  edit the workbook in Excel and upload it again.
- Signed-in users are trusted not to flood the server: several very large
  uploads at once from one session each use memory while they are read.
