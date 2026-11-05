import { useState } from 'react';
import { Eye, EyeOff, FileDown, FileSpreadsheet, LogIn, ShieldCheck } from 'lucide-react';
import * as api from '../api/client.js';
import Spinner from '../components/Spinner.jsx';
import { Alert } from '../components/Feedback.jsx';
import LoginScreen from '../components/LoginScreen.jsx';

// The sign-in page's story (IZ's Genco Project Theme login, left side).
const STORY = {
  headline: 'Failure modes and effects,',
  accent: 'analysed in one place',
  summary: 'Upload FMEA worksheets, check and review the data, and turn it into a report you can preview and export.',
  features: [
    { icon: FileSpreadsheet, label: 'Upload Excel worksheets' },
    { icon: ShieldCheck, label: 'Run data checks' },
    { icon: FileDown, label: 'Preview and export the report' },
  ],
};

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
    <LoginScreen
      appName="FMEA Report"
      description="Failure Mode & Effects Analysis"
      icon="fmea"
      story={STORY}
      onSubmit={handleSubmit}
      footer="Nothing is saved in this app. Workbooks and reports are cleared when you sign out or close the page."
    >
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
        <span className="gt-label">Username</span>
        <input
          className="gt-input"
          name="username"
          autoComplete="username"
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          disabled={busy}
        />
      </label>

      <label className="field">
        <span className="gt-label">Password</span>
        <span className="input-with-action">
          <input
            className="gt-input"
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

      <button type="submit" className="gt-btn-hero signin-submit" disabled={busy}>
        {busy ? (
          <>
            <Spinner size={18} /> Signing in…
          </>
        ) : (
          <>
            <LogIn size={18} aria-hidden="true" /> Sign in
          </>
        )}
      </button>
    </LoginScreen>
  );
}
