import React, { useMemo } from "react";

export default function PieChart({
  data = [],
  width = 320,
  height = 320,
  showLegend = true,
  showLegendPerc = true,
  showSliceLabels = false,
  minSliceLabelPercent = 1,
  minLabelPercent,
}) {
  const normalizedData = Array.isArray(data) ? data : [];

  const { computedSlices, totalValue } = useMemo(() => {
    const items = normalizedData.map((d) => ({
      label: String(d?.label ?? "Item"),
      value: Number(d?.value ?? 0),
    }));

    const sum = items.reduce((acc, item) => acc + (Number.isFinite(item.value) ? item.value : 0), 0);

    const TWO_PI = Math.PI * 2;
    let cumulativeShare = 0;

    const slices = items.map((item) => {
      const share = sum > 0 ? item.value / sum : 0;
      const start = cumulativeShare * TWO_PI;
      cumulativeShare += share;
      const end = cumulativeShare * TWO_PI;
      return { ...item, start, end, share, percent: share * 100 };
    });

    return { computedSlices: slices, totalValue: sum };
  }, [normalizedData]);

  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) / 2 - 8;

  const effectiveMinLabelPercent = Number.isFinite(Number(minLabelPercent))
    ? Number(minLabelPercent)
    : Number(minSliceLabelPercent);

  const buildSlicePath = (cx, cy, r, start, end) => {
    const angle = end - start;
    const FULL = Math.PI * 2;
    if (angle >= FULL - 1e-6) return null;

    const largeArc = angle > Math.PI ? 1 : 0;
    const x0 = cx + r * Math.cos(start);
    const y0 = cy + r * Math.sin(start);
    const x1 = cx + r * Math.cos(end);
    const y1 = cy + r * Math.sin(end);
    return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${largeArc} 1 ${x1} ${y1} Z`;
  };

  const getLabelPosition = (cx, cy, r, start, end) => {
    const mid = (start + end) / 2;
    const labelR = r * 0.62;
    return { x: cx + labelR * Math.cos(mid), y: cy + labelR * Math.sin(mid) };
  };

  const getColorForIndex = (i) => {
    const hue = (i * 57) % 360;
    return `hsl(${hue} 70% 60%)`;
  };

  const hasData = totalValue > 0 && computedSlices.some((s) => (s.value ?? 0) > 0);

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
      <svg width={width} height={height} role="img" aria-label="Pie chart">
        {hasData ? (
          computedSlices.map((slice, i) => {
            const d = buildSlicePath(centerX, centerY, radius, slice.start, slice.end);
            const fill = getColorForIndex(i);
            const pctText = `${slice.percent.toFixed(slice.percent < 10 ? 1 : 0)}%`;
            const { x, y } = getLabelPosition(centerX, centerY, radius, slice.start, slice.end);
            const drawLabel = showSliceLabels && slice.percent >= (effectiveMinLabelPercent ?? 1);

            if (d === null) {
              return (
                <g key={i}>
                  <circle cx={centerX} cy={centerY} r={radius} fill={fill}>
                    <title>
                      {slice.label}: {pctText}
                    </title>
                  </circle>
                  {drawLabel && (
                    <text
                      x={centerX}
                      y={centerY}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fontSize="12"
                      fill="#1f2937"
                      style={{ paintOrder: "stroke", stroke: "white", strokeWidth: 2 }}
                    >
                      {pctText}
                    </text>
                  )}
                </g>
              );
            }

            return (
              <g key={i}>
                <path d={d} fill={fill} stroke="white" strokeWidth="1">
                  <title>
                    {slice.label}: {pctText}
                  </title>
                </path>
                {drawLabel && (
                  <text
                    x={x}
                    y={y}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize="12"
                    fill="#1f2937"
                    style={{ paintOrder: "stroke", stroke: "white", strokeWidth: 2 }}
                  >
                    {pctText}
                  </text>
                )}
              </g>
            );
          })
        ) : (
          <g>
            <circle cx={centerX} cy={centerY} r={radius} fill="#f1f3f5" />
            <text x={centerX} y={centerY} textAnchor="middle" dominantBaseline="middle" fontSize="13" fill="#6c757d">
              No data
            </text>
          </g>
        )}
      </svg>

      {showLegend && (
        <div style={{ minWidth: 200 }}>
          <div className="fw-semibold mb-2">Legend</div>
          {hasData ? (
            <ul className="list-unstyled mb-0" style={{ lineHeight: 1.5 }}>
              {computedSlices.map((slice, i) => (
                <li key={i} className="d-flex align-items-center gap-2">
                  <span
                    aria-hidden
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: 2,
                      background: getColorForIndex(i),
                      display: "inline-block",
                      flex: "0 0 auto",
                    }}
                  />
                  <span title={`${slice.label}: ${slice.percent.toFixed(1)}%`}>
                    {slice.label}
                    {showLegendPerc ? ` — ${slice.percent.toFixed(slice.percent < 10 ? 1 : 0)}%` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-muted">No data.</div>
          )}
        </div>
      )}
    </div>
  );
}
