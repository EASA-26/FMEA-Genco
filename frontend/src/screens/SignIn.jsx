import { useState } from 'react';
import { ArrowRight, Eye, EyeOff, FileSpreadsheet, ListChecks, FileDown } from 'lucide-react';
import * as api from '../api/client.js';
import PulseMark from '../components/PulseMark.jsx';
import Spinner from '../components/Spinner.jsx';
import { Alert } from '../components/Feedback.jsx';
import GaugeMotif from '../components/GaugeMotif.jsx';

export default function SignIn({ notice, noticeLabel = 'Note', onSignedIn }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(event) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError('Enter your username and password.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await api.login(username.trim(), password);
      onSignedIn(result);
    } catch (err) {
      setError(err.message || 'Sign-in failed. Please try again.');
      setBusy(false);
    }
  }

  return (
    <div className="signin">
      <section className="signin-brand" aria-hidden="false">
        <div className="signin-grid" aria-hidden="true" />
        <GaugeMotif className="signin-motif" width={640} height={640} cx={540} cy={330} />
        <div className="signin-brand-top">
          <PulseMark size={36} tone="glass" />
          <span className="signin-brand-line">ALCM - Maintenance Strategy</span>
        </div>
        <div className="signin-brand-body">
          <h1 className="signin-hero">
            Failure Mode Effect
            <br />
            Analysis (FMEA) Report
          </h1>
          <p className="signin-hero-lead">
            Turn the FMEA workbook into a checked, print-ready report for your station.
          </p>
          <ol className="signin-flow">
            <li>
              <FileSpreadsheet size={18} aria-hidden="true" />
              <span>Upload the Excel workbook</span>
            </li>
            <li>
              <ListChecks size={18} aria-hidden="true" />
              <span>Review the data and checks</span>
            </li>
            <li>
              <FileDown size={18} aria-hidden="true" />
              <span>Preview and export the PDF</span>
            </li>
          </ol>
        </div>
      </section>

      <main className="signin-panel">
        <form className="signin-card" onSubmit={handleSubmit} noValidate>
          <div className="signin-card-head">
            <PulseMark size={40} />
            <div>
              <div className="signin-app">FMEA Report</div>
              <div className="signin-app-sub">ALCM - Maintenance Strategy</div>
            </div>
          </div>
          <h2 className="signin-title">Sign in</h2>
          <p className="signin-lead">Use the account given to you by your ALCM administrator.</p>

          {notice && !error && (
            <Alert tone="info" label={noticeLabel} className="signin-alert">
              {notice}
            </Alert>
          )}
          {error && (
            <Alert tone="error" label="Sign-in failed" className="signin-alert">
              {error}
            </Alert>
          )}

          <label className="field">
            <span className="field-label">Username</span>
            <input
              className="input"
              name="username"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={busy}
            />
          </label>

          <label className="field">
            <span className="field-label">Password</span>
            <span className="input-with-action">
              <input
                className="input"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
              />
              <button
                type="button"
                className="input-action"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </span>
          </label>

          <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
            {busy ? (
              <>
                <Spinner size={17} /> Signing in…
              </>
            ) : (
              <>
                Sign in <ArrowRight size={17} aria-hidden="true" />
              </>
            )}
          </button>
        </form>
        <p className="signin-foot">
          Workbooks are read in memory only and never saved. They are discarded when you sign out or leave the page.
        </p>
      </main>
    </div>
  );
}
