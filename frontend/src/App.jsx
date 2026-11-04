import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, WifiOff } from 'lucide-react';
import * as api from './api/client.js';
import SignIn from './screens/SignIn.jsx';
import Workspace from './screens/Workspace.jsx';
import PulseMark from './components/PulseMark.jsx';
import Spinner from './components/Spinner.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';

/** Optional features the server reports with the signed-in user (e.g. Outlook email). */
function featuresFrom(result) {
  const features = result && result.features && typeof result.features === 'object' ? result.features : {};
  return { outlook_email: features.outlook_email === true };
}

// Top-level auth gate: checks the session, shows sign-in (local mode only) or the
// workspace, and returns to sign-in whenever any request reports an ended session.
export default function App() {
  const [auth, setAuth] = useState({ status: 'checking' });
  const checking = useRef(false);

  const checkSession = useCallback(async (reason) => {
    if (checking.current) return;
    checking.current = true;
    setAuth({ status: 'checking' });
    try {
      const me = await api.getMe();
      setAuth({ status: 'signedIn', user: me.user, authMode: me.auth_mode, features: featuresFrom(me) });
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 401) {
        setAuth(
          reason === 'expired'
            ? { status: 'signedOut', noticeLabel: 'Session ended', notice: 'Your session has ended. Please sign in again.' }
            : { status: 'signedOut', notice: '' },
        );
      } else {
        setAuth({ status: 'unavailable', message: err.message || 'The FMEA service could not be reached.' });
      }
    } finally {
      checking.current = false;
    }
  }, []);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  useEffect(() => api.onUnauthorized(() => checkSession('expired')), [checkSession]);

  const handleSignedIn = useCallback((result) => {
    setAuth({ status: 'signedIn', user: result.user, authMode: result.auth_mode, features: featuresFrom(result) });
  }, []);

  const handleSignedOut = useCallback(() => {
    setAuth({ status: 'signedOut', noticeLabel: 'Signed out', notice: 'You have signed out.' });
  }, []);

  if (auth.status === 'checking') {
    return (
      <div className="splash" role="status" aria-live="polite">
        <PulseMark size={44} />
        <div className="splash-title">FMEA Report</div>
        <div className="splash-sub">
          <Spinner size={16} /> Opening your workspace…
        </div>
      </div>
    );
  }

  if (auth.status === 'unavailable') {
    return (
      <div className="splash">
        <div className="splash-card">
          <span className="icon-tile icon-tile-muted" aria-hidden="true">
            <WifiOff size={22} />
          </span>
          <h1>The FMEA service is not responding</h1>
          <p>{auth.message}</p>
          <button type="button" className="btn btn-primary" onClick={() => checkSession()}>
            <RefreshCw size={16} aria-hidden="true" /> Try again
          </button>
        </div>
      </div>
    );
  }

  if (auth.status === 'signedOut') {
    return <SignIn notice={auth.notice} noticeLabel={auth.noticeLabel} onSignedIn={handleSignedIn} />;
  }

  // If the workspace itself fails to draw, it is gone along with its pagehide handler:
  // discard the workbook on the server straight away (one-time use).
  return (
    <ErrorBoundary variant="page" onError={api.discardWorkbookOnExit}>
      <Workspace user={auth.user} authMode={auth.authMode} features={auth.features} onSignedOut={handleSignedOut} />
    </ErrorBoundary>
  );
}
