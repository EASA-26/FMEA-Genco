import { CircleCheck, Info, OctagonAlert, TriangleAlert } from 'lucide-react';

// Status colour is never used alone: every alert carries an icon and a written label.
const TONES = {
  error: { Icon: OctagonAlert, label: 'Error' },
  warning: { Icon: TriangleAlert, label: 'Check' },
  info: { Icon: Info, label: 'Note' },
  success: { Icon: CircleCheck, label: 'Ready' },
};

export function Alert({ tone = 'info', title, label, children, actions, className = '', id }) {
  const { Icon, label: defaultLabel } = TONES[tone];
  return (
    <div id={id} className={`alert alert-${tone} ${className}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon className="alert-icon" size={20} aria-hidden="true" />
      <div className="alert-body">
        <div className="alert-title">
          <span className="alert-label">{label || defaultLabel}</span>
          {title && <span>{title}</span>}
        </div>
        {children && <div className="alert-text">{children}</div>}
        {actions && <div className="alert-actions">{actions}</div>}
      </div>
    </div>
  );
}

export function SeverityIcon({ severity, size = 16 }) {
  const tone = TONES[severity] || TONES.info;
  const { Icon } = tone;
  return <Icon size={size} className={`sev-icon sev-${severity}`} aria-hidden="true" />;
}

export function EmptyState({ icon: Icon, title, children, actions, compact = false }) {
  return (
    <div className={`empty-state ${compact ? 'empty-state-compact' : ''}`}>
      {Icon && (
        <span className="icon-tile icon-tile-muted" aria-hidden="true">
          <Icon size={compact ? 18 : 22} />
        </span>
      )}
      <div className="empty-title">{title}</div>
      {children && <div className="empty-text">{children}</div>}
      {actions && <div className="empty-actions">{actions}</div>}
    </div>
  );
}
