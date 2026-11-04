import { Cell, Pie, PieChart, Tooltip } from 'recharts';

function SliceTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const slice = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-value">
        <span className="chart-tooltip-key" style={{ background: slice.color }} aria-hidden="true" />
        {slice.count} {slice.count === 1 ? 'row' : 'rows'} · {slice.percent.toFixed(1)}%
      </div>
      <div className="chart-tooltip-label">{slice.label}</div>
    </div>
  );
}

// Recommended Strategy pie. Colours, counts and percentages come straight from the
// report (Summary.pie), the same values the PDF draws. White 2px gaps separate slices.
// It is drawn without animation: the panel already fades in, and the chart must be
// complete straight away (screenshots, printing, background tabs).
// recharts' own keyboard layer is switched off: it adds unlabelled tab stops, and the
// legend next to the chart already lists every slice with its count and percent.
export default function StrategyPie({ slices, size = 232, activeIndex, onActiveChange }) {
  return (
    <PieChart width={size} height={size} accessibilityLayer={false}>
      <Pie
        rootTabIndex={-1}
        data={slices}
        dataKey="count"
        nameKey="label"
        cx="50%"
        cy="50%"
        outerRadius={size / 2 - 6}
        startAngle={90}
        endAngle={-270}
        stroke="#ffffff"
        strokeWidth={2}
        isAnimationActive={false}
        onMouseEnter={(_, index) => onActiveChange && onActiveChange(index)}
        onMouseLeave={() => onActiveChange && onActiveChange(null)}
      >
        {slices.map((slice, index) => (
          <Cell
            key={slice.code || 'not-specified'}
            fill={slice.color}
            fillOpacity={activeIndex === null || activeIndex === undefined || activeIndex === index ? 1 : 0.35}
          />
        ))}
      </Pie>
      <Tooltip content={<SliceTooltip />} isAnimationActive={false} />
    </PieChart>
  );
}
