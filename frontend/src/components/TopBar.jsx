import { CircleCheck, LogOut, Menu, OctagonAlert, TriangleAlert } from 'lucide-react';
import { plural } from '../lib/report.js';

// The top bar carries the page's title and subtitle (pages have no heading of their
// own, so this h1 is the page's only one), the data-check status and who is signed in.
// Exporting is step 4 of the workflow (with Back / Next on every step), so there is no
// Export button here. The workspace focuses the title (#page-title) when a step's own
// button that moved on has disappeared, so it is focusable from script only.
export default function TopBar({ heading, report, counts, user, authMode, onMenu, onShowChecks, onSignOut }) {
  const userName = (user && user.name) || 'Engineer';

  return (
    <header className="topbar gt-topbar">
      <button type="button" className="gt-icon-btn topbar-menu" onClick={onMenu} aria-label="Open menu">
        <Menu size={20} />
      </button>

      {/* Long titles and subtitles (file names) are cut with "…"; the full text shows on hover. */}
      <div className="topbar-heading">
        <h1 id="page-title" className="gt-topbar-title topbar-title" tabIndex={-1} title={heading.title}>
          {heading.title}
        </h1>
        {heading.subtitle && (
          <p className="gt-topbar-subtitle topbar-subtitle" title={heading.subtitle}>
            {heading.subtitle}
          </p>
        )}
      </div>

      {report && (
        <div className="topbar-chips" aria-label="Data check status">
          {counts.error > 0 && (
            <button type="button" className="chip chip-error" onClick={onShowChecks}>
              <OctagonAlert size={15} aria-hidden="true" />
              {plural(counts.error, 'error')}
            </button>
          )}
          {counts.warning > 0 && (
            <button type="button" className="chip chip-warning" onClick={onShowChecks}>
              <TriangleAlert size={15} aria-hidden="true" />
              {plural(counts.warning, 'warning')}
            </button>
          )}
          {counts.error === 0 && (
            <button type="button" className="chip chip-ok" onClick={onShowChecks}>
              <CircleCheck size={15} aria-hidden="true" />
              Ready to export
            </button>
          )}
        </div>
      )}

      {/* Signed-in user. On narrow screens the name is hidden from view (screen readers
          still hear it) and Sign out shrinks to its icon. */}
      <div className="topbar-user">
        <span className="gt-avatar" aria-hidden="true">
          {userName.slice(0, 1).toUpperCase()}
        </span>
        <div className="topbar-user-text">
          <div className="topbar-user-name" title={userName}>
            {userName}
          </div>
          <div className="topbar-user-meta">{authMode === 'databricks' ? 'Signed in with Databricks' : 'Signed in'}</div>
        </div>
        {/* Databricks handles sign-in itself, so there is nothing to sign out of here. */}
        {authMode !== 'databricks' && (
          <button type="button" className="gt-btn-secondary topbar-signout" onClick={onSignOut}>
            <LogOut size={16} aria-hidden="true" />
            <span className="topbar-signout-label">Sign out</span>
          </button>
        )}
      </div>
    </header>
  );
}
