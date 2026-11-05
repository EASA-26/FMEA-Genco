import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import * as api from '../api/client.js';
import { countIssues } from '../lib/report.js';
import { pageHeading } from '../lib/pageHeading.js';
import { checkWorkbookFile } from '../lib/upload.js';
import Sidebar from '../components/Sidebar.jsx';
import TopBar from '../components/TopBar.jsx';
import Spinner from '../components/Spinner.jsx';
import ErrorBoundary from '../components/ErrorBoundary.jsx';
import { Alert } from '../components/Feedback.jsx';
import UploadView from '../views/UploadView.jsx';
import ChecksView from '../views/ChecksView.jsx';
import FrontPageView from '../views/FrontPageView.jsx';
import IntroductionView from '../views/IntroductionView.jsx';
import AnalysisView from '../views/AnalysisView.jsx';
import RecommendationView from '../views/RecommendationView.jsx';
import PreviewView from '../views/PreviewView.jsx';
import ExportView from '../views/ExportView.jsx';
import CompleteView from '../views/CompleteView.jsx';

const IDLE_UPLOAD = { status: 'idle', progress: 0, fileName: '', fileSize: 0, error: '' };

/** The top bar's h1 (#page-title): the page title, focusable from script only. */
function focusPageTitle() {
  const title = document.getElementById('page-title');
  if (title) title.focus({ preventScroll: true });
}

// The signed-in workspace: owns the report, the upload in progress and which
// step / section / UOIR is on screen.
//
// Steps (nav.step): 'upload' | 'review' | 'preview' | 'export', plus 'done' (the
// "Report complete" screen after Finish). Each step has its own Back / Next buttons.
//
// One-time use: the report lives only in this page visit. Opening the workspace
// discards anything the session still holds, leaving the page (sign-out, refresh,
// closing the tab, another site) discards it on the server too, and moving between
// the app's own steps keeps it.
export default function Workspace({ user, authMode, features, onSignedOut }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [closedNotice, setClosedNotice] = useState('');
  const [nav, setNav] = useState({ step: 'upload', section: 'checks' });
  const [uoirId, setUoirId] = useState(null);
  const [analysisTab, setAnalysisTab] = useState('analysis');
  const [recommendationTab, setRecommendationTab] = useState('yes');
  const [focus, setFocus] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [upload, setUpload] = useState(IDLE_UPLOAD);
  // The PDF of this report was downloaded, or an email with it opened (Export step).
  // Kept here, not in the Export view, so going Back and Next again remembers it.
  const [delivered, setDelivered] = useState(false);
  const uploadAbort = useRef(null);
  // True while this page shows a report. Only then (or while an upload is running)
  // does leaving the page discard the session's workbook, so closing an older tab of
  // the app that holds nothing does not close the workbook open in another tab.
  const holdsReport = useRef(false);

  const counts = useMemo(() => countIssues(report ? report.issues : []), [report]);

  const goTo = useCallback((step, section) => {
    setNav((current) => ({ step, section: section || current.section }));
    setMenuOpen(false);
    window.scrollTo({ top: 0 });
  }, []);

  // Show a new report, or none. A new report does not change the step: after an
  // upload the engineer stays on Upload to check the file, then picks Proceed.
  // With no report the app goes to `emptyStep` (Upload, or 'done' after Finish).
  const applyReport = useCallback(
    (next, emptyStep = 'upload') => {
      holdsReport.current = Boolean(next);
      setReport(next);
      setDelivered(false);
      setFocus(null);
      setAnalysisTab('analysis');
      setRecommendationTab('yes');
      setUoirId(next && next.uoirs.length ? next.uoirs[0].uoir_id : null);
      if (!next) goTo(emptyStep);
    },
    [goTo],
  );

  // Start every visit on Upload with nothing open. The upload area stays hidden
  // (loading) until the discard has finished, so a new upload cannot race it.
  const startFresh = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      await api.discardWorkbook();
      applyReport(null);
    } catch (err) {
      if (!(err instanceof api.ApiError && err.status === 401)) setLoadError(err.message);
    } finally {
      setLoading(false);
    }
  }, [applyReport]);

  useEffect(() => {
    startFresh();
  }, [startFresh]);

  // Cancel an upload still running when the workspace closes (e.g. sign-out).
  useEffect(() => () => uploadAbort.current && uploadAbort.current.abort(), []);

  // Leaving the page (refresh, closing the tab, another site) discards the workbook on
  // the server as well. A page restored from the back/forward cache would show a report
  // the server no longer holds, so it reloads and starts fresh.
  useEffect(() => {
    const onPageHide = () => {
      const uploading = Boolean(uploadAbort.current);
      if (uploading) uploadAbort.current.abort();
      if (uploading || holdsReport.current) api.discardWorkbookOnExit();
    };
    const onPageShow = (event) => {
      if (event.persisted) window.location.reload();
    };
    window.addEventListener('pagehide', onPageHide);
    window.addEventListener('pageshow', onPageShow);
    return () => {
      window.removeEventListener('pagehide', onPageHide);
      window.removeEventListener('pageshow', onPageShow);
    };
  }, []);

  // A file dropped anywhere outside the upload card would make the browser open it,
  // leaving the page, which discards the open workbook. Only the upload card takes
  // file drops (it handles its own events); everywhere else a dropped file does
  // nothing. Other drags (text into the Recipients box) work as before.
  useEffect(() => {
    const blockStrayDrop = (event) => {
      const types = event.dataTransfer ? Array.from(event.dataTransfer.types || []) : [];
      if (!types.includes('Files')) return;
      if (event.target instanceof Element && event.target.closest('.dropzone')) return;
      // The page takes the drag ("no drop" cursor), so the browser never opens the file.
      event.preventDefault();
      if (event.type === 'dragover') event.dataTransfer.dropEffect = 'none';
    };
    window.addEventListener('dragover', blockStrayDrop);
    window.addEventListener('drop', blockStrayDrop);
    return () => {
      window.removeEventListener('dragover', blockStrayDrop);
      window.removeEventListener('drop', blockStrayDrop);
    };
  }, []);

  // The server answered 404 for the report: it was discarded (sign-out, another tab...).
  const workbookClosed = useCallback(() => {
    setClosedNotice(api.WORKBOOK_CLOSED_MESSAGE);
    applyReport(null);
  }, [applyReport]);

  // Tablet drawer: move keyboard focus into the menu when it opens, and let Escape close it.
  useEffect(() => {
    if (!menuOpen) return undefined;
    const closeButton = document.querySelector('.sidebar .sidebar-close');
    if (closeButton) closeButton.focus();
    const onKey = (event) => {
      if (event.key === 'Escape') closeMenu();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  /** Close the drawer and give focus back to the menu button that opened it. */
  function closeMenu() {
    setMenuOpen(false);
    const menuButton = document.querySelector('.topbar-menu');
    if (menuButton) menuButton.focus();
  }

  const startUpload = useCallback(
    async (file) => {
      const problem = checkWorkbookFile(file);
      if (problem) {
        setUpload({ ...IDLE_UPLOAD, status: 'error', fileName: file ? file.name : '', error: problem });
        return;
      }
      const controller = new AbortController();
      uploadAbort.current = controller;
      setClosedNotice('');
      setUpload({ status: 'uploading', progress: 0, fileName: file.name, fileSize: file.size, error: '' });
      try {
        const next = await api.uploadWorkbook(file, {
          signal: controller.signal,
          onProgress: (fraction) =>
            setUpload((u) =>
              u.status === 'uploading' || u.status === 'processing'
                ? { ...u, progress: fraction, status: fraction >= 1 ? 'processing' : 'uploading' }
                : u,
            ),
        });
        setUpload(IDLE_UPLOAD);
        applyReport(next);
      } catch (err) {
        if (err && err.name === 'AbortError') {
          setUpload(IDLE_UPLOAD);
        } else {
          setUpload((u) => ({ ...u, status: 'error', error: err.message || 'The upload did not finish. Please try again.' }));
        }
      } finally {
        uploadAbort.current = null;
      }
    },
    [applyReport],
  );

  const cancelUpload = useCallback(() => {
    if (uploadAbort.current) uploadAbort.current.abort();
  }, []);

  // Remove (Upload step) and Upload another (Export step): discard the workbook, then
  // show an empty Upload step. A failed discard keeps the report and reaches the caller,
  // which says so on screen.
  const removeWorkbook = useCallback(async () => {
    await api.discardWorkbook();
    applyReport(null);
  }, [applyReport]);

  // Finish (Export step): discard the workbook, then show "Report complete".
  const finishReport = useCallback(async () => {
    await api.discardWorkbook();
    applyReport(null, 'done');
  }, [applyReport]);

  const selectUoir = useCallback((id) => {
    setUoirId(id);
    setFocus(null);
  }, []);

  const openSection = useCallback(
    (section, id) => {
      if (id) selectUoir(id);
      // A row picked earlier in Data checks is highlighted once, not every time the table reopens.
      setFocus(null);
      goTo('review', section);
    },
    [goTo, selectUoir],
  );

  const changeAnalysisTab = useCallback((tab) => {
    setAnalysisTab(tab);
    setFocus(null);
  }, []);

  const showInTable = useCallback(
    (issue) => {
      setUoirId(issue.uoir_id);
      setAnalysisTab('analysis');
      setFocus({ uoirId: issue.uoir_id, row: issue.row, cell: issue.cell, key: Date.now() });
      goTo('review', 'analysis');
    },
    [goTo],
  );

  async function signOut() {
    try {
      await api.logout();
    } catch {
      // Whatever happened, the sign-in page is the right place to go next.
    }
    onSignedOut();
  }

  const markDelivered = useCallback(() => setDelivered(true), []);

  const busyUploading = upload.status === 'uploading' || upload.status === 'processing';
  const selectedUoir = report ? report.uoirs.find((u) => u.uoir_id === uoirId) || report.uoirs[0] || null : null;
  // While the workspace is being prepared (or could not be), there is no page yet.
  let heading = pageHeading(nav, report);
  if (loading) heading = { title: 'Upload the FMEA workbook', subtitle: '' };
  else if (loadError) heading = { title: 'Workspace not ready', subtitle: '' };
  const viewKey = `${nav.step}:${nav.step === 'review' ? nav.section : ''}`;

  // Back / Next, Proceed, Finish and the like live inside the page they leave, so the
  // pressed button disappears with it and keyboard focus would fall to the page body.
  // Then focus goes to the new page's title in the top bar, which screen readers read
  // out. Focus that a page placed itself (the Analysis table after "Show in table", the
  // Upload card's buttons) or that is still on a sidebar link stays where it is.
  // Compared with the last page shown (not a first-run flag), so React's development
  // double run of effects does not count as a page change.
  const shownView = useRef(viewKey);
  useEffect(() => {
    if (shownView.current === viewKey) return;
    shownView.current = viewKey;
    const active = document.activeElement;
    if (active && active !== document.body) return;
    focusPageTitle();
  }, [viewKey]);

  // Picking a page in the tablet drawer closes the drawer, hiding the link that had
  // focus; focus then goes to the new page's title too.
  const navigateFromSidebar = (go) => (...args) => {
    const fromDrawer = menuOpen;
    go(...args);
    if (fromDrawer) focusPageTitle();
  };

  function renderView() {
    if (loading) {
      return (
        <div className="view-loading" role="status">
          <Spinner size={22} /> Preparing your workspace…
        </div>
      );
    }
    if (loadError) {
      return (
        <div className="view-narrow">
          <Alert
            tone="error"
            label="Not ready"
            title="The workspace could not be prepared"
            actions={
              <button type="button" className="gt-btn-secondary" onClick={startFresh}>
                <RefreshCw size={16} aria-hidden="true" /> Try again
              </button>
            }
          >
            {loadError}
          </Alert>
        </div>
      );
    }
    // Checked before Upload: after Finish there is no report, but the engineer should
    // see that the report is complete rather than an empty Upload step.
    if (nav.step === 'done' && !report) {
      return <CompleteView onStartNew={() => goTo('upload')} />;
    }
    if (nav.step === 'upload' || !report) {
      return (
        <UploadView
          report={report}
          upload={upload}
          notice={closedNotice}
          onFile={startUpload}
          onCancel={cancelUpload}
          onDismissError={() => setUpload(IDLE_UPLOAD)}
          onDismissNotice={() => setClosedNotice('')}
          onContinue={() => goTo('review', 'checks')}
          onRemove={removeWorkbook}
        />
      );
    }
    if (nav.step === 'preview') {
      return (
        <PreviewView
          report={report}
          counts={counts}
          onShowChecks={() => goTo('review', 'checks')}
          onBack={() => goTo('review', 'checks')}
          onNext={() => goTo('export')}
          onWorkbookClosed={workbookClosed}
        />
      );
    }
    if (nav.step === 'export') {
      return (
        <ExportView
          report={report}
          counts={counts}
          features={features}
          delivered={delivered}
          onDelivered={markDelivered}
          onShowChecks={() => goTo('review', 'checks')}
          onBack={() => goTo('preview')}
          onWorkbookClosed={workbookClosed}
          onUploadAnother={removeWorkbook}
          onFinish={finishReport}
        />
      );
    }
    // Every Review Data page (Data checks and each report section) has the same
    // Back (Upload Workbook) / Next (Preview Report) buttons.
    const reviewNav = { counts, onBack: () => goTo('upload'), onNext: () => goTo('preview') };
    switch (nav.section) {
      case 'front':
        return <FrontPageView report={report} {...reviewNav} />;
      case 'intro':
        return <IntroductionView report={report} {...reviewNav} />;
      case 'analysis':
        return (
          <AnalysisView
            report={report}
            uoir={selectedUoir}
            onSelectUoir={selectUoir}
            tab={analysisTab}
            onTab={changeAnalysisTab}
            focus={focus && selectedUoir && focus.uoirId === selectedUoir.uoir_id ? focus : null}
            onShowChecks={() => goTo('review', 'checks')}
            {...reviewNav}
          />
        );
      case 'recommendation':
        return (
          <RecommendationView
            report={report}
            uoir={selectedUoir}
            onSelectUoir={selectUoir}
            tab={recommendationTab}
            onTab={setRecommendationTab}
            {...reviewNav}
          />
        );
      default:
        return <ChecksView report={report} onShowInTable={showInTable} {...reviewNav} />;
    }
  }

  return (
    <div className={`shell ${menuOpen ? 'menu-open' : ''}`}>
      <Sidebar
        report={report}
        counts={counts}
        nav={nav}
        uoirId={selectedUoir ? selectedUoir.uoir_id : null}
        uploadBusy={busyUploading}
        onStep={navigateFromSidebar((step) => goTo(step))}
        onSection={navigateFromSidebar(openSection)}
        onClose={closeMenu}
      />
      <div className="shell-scrim" onClick={closeMenu} aria-hidden="true" />
      <div className="shell-main">
        <TopBar
          heading={heading}
          report={report}
          counts={counts}
          user={user}
          authMode={authMode}
          onMenu={() => setMenuOpen(true)}
          onShowChecks={() => goTo('review', 'checks')}
          onSignOut={signOut}
        />
        <main className="content" id="main">
          <div className="view" key={viewKey}>
            <ErrorBoundary
              variant="section"
              resetKey={`${selectedUoir ? selectedUoir.uoir_id : ''}:${analysisTab}:${recommendationTab}:${report ? report.generated_at : ''}:${report ? report.source_filename : ''}`}
            >
              {renderView()}
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  );
}
