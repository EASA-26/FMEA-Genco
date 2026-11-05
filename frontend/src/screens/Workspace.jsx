import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import * as api from '../api/client.js';
import { countIssues } from '../lib/report.js';
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

const IDLE_UPLOAD = { status: 'idle', progress: 0, fileName: '', fileSize: 0, error: '' };

// The signed-in workspace: owns the report, the upload in progress and which
// step / section / UOIR is on screen.
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
  const [pendingExport, setPendingExport] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [upload, setUpload] = useState(IDLE_UPLOAD);
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

  const applyReport = useCallback(
    (next) => {
      holdsReport.current = Boolean(next);
      setReport(next);
      setFocus(null);
      setAnalysisTab('analysis');
      setRecommendationTab('yes');
      setUoirId(next && next.uoirs.length ? next.uoirs[0].uoir_id : null);
      if (next) goTo('review', 'checks');
      else goTo('upload');
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

  // The server answered 404 for the report: it was discarded (sign-out, another tab...).
  const workbookClosed = useCallback(() => {
    setClosedNotice(api.WORKBOOK_CLOSED_MESSAGE);
    setPendingExport(false);
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

  const removeWorkbook = useCallback(async () => {
    await api.discardWorkbook();
    applyReport(null);
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

  const requestExport = useCallback(() => {
    setPendingExport(true);
    goTo('export');
  }, [goTo]);

  async function signOut() {
    try {
      await api.logout();
    } catch {
      // Whatever happened, the sign-in page is the right place to go next.
    }
    onSignedOut();
  }

  const busyUploading = upload.status === 'uploading' || upload.status === 'processing';
  const selectedUoir = report ? report.uoirs.find((u) => u.uoir_id === uoirId) || report.uoirs[0] || null : null;

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
          onExport={requestExport}
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
          autoStart={pendingExport}
          onAutoStartDone={() => setPendingExport(false)}
          onShowChecks={() => goTo('review', 'checks')}
          onPreview={() => goTo('preview')}
          onWorkbookClosed={workbookClosed}
        />
      );
    }
    switch (nav.section) {
      case 'front':
        return <FrontPageView report={report} />;
      case 'intro':
        return <IntroductionView report={report} />;
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
            onShowChecks={() => goTo('review', 'checks')}
          />
        );
      default:
        return (
          <ChecksView
            report={report}
            counts={counts}
            onShowInTable={showInTable}
            onOpenSection={openSection}
            onPreview={() => goTo('preview')}
          />
        );
    }
  }

  const viewKey = `${nav.step}:${nav.step === 'review' ? nav.section : ''}`;

  return (
    <div className={`shell ${menuOpen ? 'menu-open' : ''}`}>
      <Sidebar
        report={report}
        counts={counts}
        nav={nav}
        uoirId={selectedUoir ? selectedUoir.uoir_id : null}
        user={user}
        authMode={authMode}
        uploadBusy={busyUploading}
        onStep={(step) => goTo(step)}
        onSection={openSection}
        onSignOut={signOut}
        onClose={closeMenu}
      />
      <div className="shell-scrim" onClick={closeMenu} aria-hidden="true" />
      <div className="shell-main">
        <TopBar
          report={report}
          counts={counts}
          uploadBusy={busyUploading}
          onMenu={() => setMenuOpen(true)}
          onShowChecks={() => goTo('review', 'checks')}
          onUploadAnother={() => goTo('upload')}
          onExport={requestExport}
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
