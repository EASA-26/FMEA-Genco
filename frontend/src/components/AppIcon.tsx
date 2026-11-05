import { createElement, useId, type ReactElement } from 'react';

// App icons: each app's main symbol with a small badge in the bottom-right corner, drawn
// from lucide shapes (ISC licence). Two are custom-drawn (welding-torch, trend) and two are
// trimmed lucide icons (coal-flame, cog-cut). A mask clears the main symbol under the badge,
// and around an overlay drawn on top of it, so the icon is one colour (currentColor) and
// works on any background. app-icons/*.svg and preview.html hold the same drawings; change
// them together. Registry and meaning: THEME-GUIDE.md section 11.

type Shape = [tag: string, attrs: Record<string, string>, children?: Shape[]];

const SHAPES: Record<string, Shape[]> = {
    'scroll-text': [
        ['path', { d: 'M15 12h-5' }],
        ['path', { d: 'M15 8h-5' }],
        ['path', { d: 'M19 17V5a2 2 0 0 0-2-2H4' }],
        ['path', { d: 'M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3' }],
    ],
    'sparkles': [
        ['path', { d: 'M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z' }],
        ['path', { d: 'M20 2v4' }],
        ['path', { d: 'M22 4h-4' }],
        ['circle', { cx: '4', cy: '20', r: '2' }],
    ],
    'welding-torch': [
        ['rect', { x: '2', y: '15.75', width: '9', height: '3.5', rx: '1.75', transform: 'rotate(-45 6.5 17.5)' }],
        ['path', { d: 'M10.6 13.4 13.6 10.4' }],
        ['path', { d: 'm12.4 9.2 2.4 2.4' }],
        ['g', { transform: 'translate(14.8 9.2) rotate(45) scale(0.55) translate(-12 -22)', strokeWidth: '3.4' }, [
            ['path', { d: 'M12 3q1 4 4 6.5t3 5.5a1 1 0 0 1-14 0 5 5 0 0 1 1-3 1 1 0 0 0 5 0c0-2-1.5-3-1.5-5q0-2 2.5-4' }],
        ]],
    ],
    'sheet': [
        ['rect', { width: '18', height: '18', x: '3', y: '3', rx: '2', ry: '2' }],
        ['line', { x1: '3', x2: '21', y1: '9', y2: '9' }],
        ['line', { x1: '3', x2: '21', y1: '15', y2: '15' }],
        ['line', { x1: '9', x2: '9', y1: '9', y2: '21' }],
        ['line', { x1: '15', x2: '15', y1: '9', y2: '21' }],
    ],
    'trend': [
        ['path', { d: 'm3 17 6-6 4 4 8-8' }],
        ['path', { d: 'M16 7h5v5' }],
    ],
    'cog-cut': [
        ['path', { d: 'M11 10.27 7 3.34' }],
        ['path', { d: 'm11 13.73-4 6.93' }],
        ['path', { d: 'M12 2v2' }],
        ['path', { d: 'm17 20.66-1-1.73' }],
        ['path', { d: 'm17 3.34-1 1.73' }],
        ['path', { d: 'M2 12h2' }],
        ['path', { d: 'm20.66 17-1.73-1' }],
        ['path', { d: 'm20.66 7-1.73 1' }],
        ['path', { d: 'm3.34 17 1.73-1' }],
        ['path', { d: 'm3.34 7 1.73 1' }],
        ['circle', { cx: '12', cy: '12', r: '2' }],
        ['circle', { cx: '12', cy: '12', r: '8' }],
    ],
    'triangle-alert': [
        ['path', { d: 'm21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3' }],
        ['path', { d: 'M12 9v4' }],
        ['path', { d: 'M12 17h.01' }],
    ],
    'coal-flame': [
        ['path', { d: 'M12 2c1 3 2.5 3.5 3.5 4.5A5 5 0 0 1 17 10a5 5 0 1 1-10 0c0-.3 0-.6.1-.9a2 2 0 1 0 3.3-2C8 4.5 11 2 12 2Z' }],
    ],
};

// shrink: the main symbol is drawn at 86% in the top-left, leaving more room for the badge.
type AppEntry = { main: string; overlay?: string; badge: string; shrink?: boolean };

// Adding an app here is all it takes: AppIconName is derived from these keys.
const APPS = {
    'px-tc': { main: 'scroll-text', badge: 'sparkles', shrink: true }, // PX-TC.ai: terms & conditions scroll + AI sparkles
    wps: { main: 'welding-torch', badge: 'sparkles', shrink: true }, // WPS.ai: welding torch with flame + AI sparkles
    fm: { main: 'sheet', overlay: 'trend', badge: 'sparkles', shrink: true }, // FM.ai: spreadsheet with a rising trend + AI sparkles
    fmea: { main: 'cog-cut', badge: 'triangle-alert' }, // FMEA: industrial gear + risk warning
    cra: { main: 'coal-flame', badge: 'sparkles', shrink: true }, // CRA.ai: coal flame + AI sparkles
} satisfies Record<string, AppEntry>;

export type AppIconName = keyof typeof APPS;

const SHRINK = 'scale(0.86)';
const BADGE = 'translate(12.75 12.75) scale(0.44)';

const draw = (shapes: Shape[]): ReactElement[] =>
    shapes.map(([tag, attrs, children], i) => createElement(tag, { key: i, ...attrs }, children && draw(children)));

type Props = {
    app: AppIconName;
    className?: string;
    // Give a title only when the icon stands alone; next to the app's name it is decorative.
    title?: string;
};

export default function AppIcon({ app, className = 'h-6 w-6', title }: Props) {
    const maskId = `app-icon-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
    const { main, overlay, badge, shrink }: AppEntry = APPS[app];
    const scale = shrink ? SHRINK : undefined;
    return (
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className={className}
            role={title ? 'img' : undefined}
            aria-label={title}
            aria-hidden={title ? undefined : true}
        >
            <mask id={maskId}>
                <rect width="24" height="24" fill="white" stroke="none" />
                <circle cx="18" cy="18" r="6.75" fill="black" stroke="none" />
                {overlay && <g transform={scale} stroke="black" strokeWidth={6.5}>{draw(SHAPES[overlay])}</g>}
            </mask>
            <g mask={`url(#${maskId})`}>
                <g transform={scale}>{draw(SHAPES[main])}</g>
            </g>
            {overlay && <g transform={scale}>{draw(SHAPES[overlay])}</g>}
            <g transform={BADGE} strokeWidth={3.6}>{draw(SHAPES[badge])}</g>
        </svg>
    );
}
