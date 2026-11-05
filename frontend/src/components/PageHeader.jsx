// `icon` (optional, decorative): shown in the theme's navy icon tile beside the heading.
// Only the home screen (Upload) passes one: the FMEA app icon.
export default function PageHeader({ eyebrow, title, children, actions, icon }) {
  return (
    <header className="page-header">
      {icon && (
        <span className="gt-icon-tile page-header-icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <div className="page-header-text">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className="page-title">{title}</h1>
        {children && <p className="page-lead">{children}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}
