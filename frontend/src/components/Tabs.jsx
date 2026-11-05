import { useRef } from 'react';

// Accessible tab strip (view filters). Arrow keys move between tabs.
export default function Tabs({ tabs, value, onChange, label, idPrefix }) {
  const refs = useRef({});

  function handleKey(event, index) {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const step = event.key === 'ArrowRight' ? 1 : -1;
    const next = tabs[(index + step + tabs.length) % tabs.length];
    onChange(next.id);
    if (refs.current[next.id]) refs.current[next.id].focus();
  }

  return (
    <div className="gt-tabs" role="tablist" aria-label={label}>
      {tabs.map((tab, index) => {
        const selected = tab.id === value;
        const Icon = tab.icon;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[tab.id] = el;
            }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel`}
            tabIndex={selected ? 0 : -1}
            className={`gt-tab ${selected ? 'is-active' : ''}`}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => handleKey(event, index)}
          >
            {Icon && <Icon size={16} aria-hidden="true" />}
            <span>{tab.label}</span>
            {tab.count !== undefined && <span className="gt-badge">{tab.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
