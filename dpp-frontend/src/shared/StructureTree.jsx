// src/shared/StructureTree.jsx
import React, { useCallback, useEffect, useMemo, useState } from "react";
export default function StructureTree({
  root,
  initialChildren = [],
  loadChildren,
  dppMap = {},
  onNodeClick,
  className,
  style,
  autoExpandAll = true,
  maxAutoExpandNodes = 2000,
}) {
  const [nodesById, setNodesById] = useState(() => new Map());
  const [childrenById, setChildrenById] = useState(() => new Map());
  const [expanded, setExpanded] = useState(() => new Set([root?.id]));
  const [loading, setLoading] = useState(() => new Set());

  useEffect(() => {
    const map = new Map();
    map.set(root.id, { ...root });
    const add = new Map(map);
    (initialChildren || []).forEach((n) => add.set(n.id, n));
    setNodesById(add);

    const c = new Map();
    c.set(root.id, initialChildren || []);
    setChildrenById(c);

    setExpanded(new Set([root.id]));
  }, [root?.id]);

  // helper: load children for one id
  const loadChildrenFor = useCallback(
    async (id) => {
      if (childrenById.has(id)) return childrenById.get(id) || [];
      if (typeof loadChildren !== "function") {
        const empty = [];
        setChildrenById((prev) => new Map(prev).set(id, empty));
        return empty;
      }
      if (loading.has(id)) return childrenById.get(id) || [];

      setLoading((prev) => new Set(prev).add(id));
      try {
        const kids = (await loadChildren(id)) || [];
        setChildrenById((prev) => {
          const next = new Map(prev);
          next.set(id, kids);
          return next;
        });
        setNodesById((prev) => {
          const next = new Map(prev);
          kids.forEach((k) => next.set(k.id, k));
          return next;
        });
        return kids;
      } finally {
        setLoading((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [childrenById, loadChildren, loading],
  );

  useEffect(() => {
    if (!autoExpandAll || !root?.id) return;
    let cancelled = false;

    (async () => {
      const toVisit = [root.id];
      const seen = new Set([root.id]);
      const nextExpanded = new Set([root.id]);
      let visitedCount = 0;

      while (toVisit.length && !cancelled && visitedCount < maxAutoExpandNodes) {
        const id = toVisit.shift();
        visitedCount += 1;

        const kidsKnown = childrenById.get(id);
        const kids = typeof kidsKnown !== "undefined" ? kidsKnown : await loadChildrenFor(id);
        if (kids && kids.length) {
          nextExpanded.add(id);
          for (const k of kids) {
            if (!seen.has(k.id)) {
              seen.add(k.id);
              toVisit.push(k.id);
            }
          }
        }
      }

      if (!cancelled) {
        setExpanded(nextExpanded);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [autoExpandAll, root?.id, childrenById, loadChildrenFor, maxAutoExpandNodes]);
  // ---------------------------------------------------------------------------

  const toggleExpand = useCallback(
    async (id) => {
      await loadChildrenFor(id);
      setExpanded((prev) => {
        const s = new Set(prev);
        if (s.has(id)) s.delete(id);
        else s.add(id);
        return s;
      });
    },
    [loadChildrenFor],
  );

  // ---- layout ----
  const layout = useMemo(() => {
    const dx = 46; // vertical spacing
    const dy = 140; // horizontal spacing per depth
    const margin = { top: 20, right: 20, bottom: 20, left: 24 };

    // build visible tree from state
    const build = (id, depth = 0) => {
      const me = nodesById.get(id);
      if (!me) return null;
      const children = expanded.has(id) ? childrenById.get(id) || [] : [];
      const childNodes = children.map((c) => build(c.id, depth + 1)).filter(Boolean);
      return { id, node: me, depth, children: childNodes };
    };
    const rootTree = root?.id ? build(root.id, 0) : null;
    if (!rootTree) return { nodes: [], links: [], width: 0, height: 0, margin, dx, dy };

    let row = 0;
    const all = [];
    const assign = (n) => {
      n.children.forEach(assign);
      if (n.children.length === 0) {
        n.x = row * dx + margin.top;
        row += 1;
      } else {
        const min = Math.min(...n.children.map((c) => c.x));
        const max = Math.max(...n.children.map((c) => c.x));
        n.x = (min + max) / 2;
      }
      n.y = n.depth * dy + margin.left;
      all.push(n);
    };
    assign(rootTree);

    const nodes = all.map((n) => ({
      id: n.id,
      data: nodesById.get(n.id),
      depth: n.depth,
      x: n.x,
      y: n.y,
    }));

    const links = all.flatMap((n) =>
      n.children.map((c) => ({
        source: { x: n.x, y: n.y },
        target: { x: c.x, y: c.y },
      })),
    );

    const approxTextWidth = (txt, fs = 12) => String(txt ?? "").length * fs * 0.6;
    const extraRight = nodes.reduce((max, n) => {
      const nameW = approxTextWidth(n.data?.name || n.id, 12);
      const w = 24 + nameW;
      return Math.max(max, w);
    }, 0);
    const width = Math.max(...nodes.map((n) => n.y + extraRight), 0) + margin.right;
    const height = (row || 1) * dx + margin.bottom;

    return { nodes, links, width, height, margin, dx, dy };
  }, [nodesById, childrenById, expanded, root?.id]);

  // ---- drawing helpers ----
  const pathFor = (s, t) => {
    const hx = (t.y - s.y) / 2;
    return `M${s.y},${s.x} C${s.y + hx},${s.x} ${t.y - hx},${t.x} ${t.y},${t.x}`;
  };
  const hasDpp = (id) => !!dppMap?.[id];

  const handleClick = (n) => {
    toggleExpand(n.id);
    if (onNodeClick) onNodeClick(n.data || n);
  };

  return (
    <div className={className} style={{ ...style, overflowX: "auto" }}>
      <svg
        width="100%"
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        preserveAspectRatio="xMinYMin meet"
        style={{ display: "block" }}
      >
        {/* links */}
        <g fill="none" stroke="var(--bs-secondary)" strokeOpacity="0.6">
          {layout.links.map((l, i) => (
            <path key={i} d={pathFor(l.source, l.target)} />
          ))}
        </g>

        {/* nodes */}
        <g>
          {layout.nodes.map((n) => {
            const dpp = hasDpp(n.id);
            const fail = !!n.data?.hasFailstate;
            const modular = !!n.data?.isModular;
            const fill = fail ? "var(--bs-danger)" : "var(--bs-success)";
            const kidsKnown = childrenById.get(n.id);
            const hasKids =
              (Array.isArray(kidsKnown) && kidsKnown.length > 0) ||
              (typeof kidsKnown === "undefined" && typeof loadChildren === "function");
            const symbol = loading.has(n.id) ? "…" : expanded.has(n.id) ? "−" : hasKids ? "+" : "";
            return (
              <g
                key={n.id}
                transform={`translate(${n.y},${n.x})`}
                style={{ cursor: hasKids ? "pointer" : "default" }}
                onClick={() => (hasKids ? handleClick(n) : onNodeClick?.(n.data || n))}
                role="button"
              >
                {/* Hauptkreis (Status via Füllfarbe) */}
                <circle r="8" fill={fill} stroke="var(--bs-secondary)" strokeWidth="1.5" />

                {/* innerer Ring = DPP */}
                {dpp ? <circle r="12" fill="none" stroke="var(--bs-info)" strokeWidth="2" /> : null}

                {/* äußerer, gestrichelter Ring = modular */}
                {modular ? (
                  <circle r="16" fill="none" stroke="var(--bs-primary)" strokeDasharray="4 3" strokeWidth="2" />
                ) : null}
                {/* expand indicator (links) */}
                {symbol ? (
                  <text
                    x="-14"
                    dy="0.32em"
                    fontSize="10"
                    textAnchor="end"
                    fill="var(--bs-secondary)"
                    pointerEvents="none"
                  >
                    {symbol}
                  </text>
                ) : null}
                {/* Label rechts neben dem Knoten */}
                <text x="20" dy="0.32em" fontSize="12" fill="var(--bs-body-color)" pointerEvents="none">
                  {n.data?.name || n.id}
                </text>
                {/* Tooltip */}
                <title>{`${n.data?.name || n.id}
fail: ${fail ? "yes" : "no"}
dpp: ${dpp ? "yes" : "no"}
modular: ${modular ? "yes" : "no"}`}</title>
              </g>
            );
          })}
        </g>
      </svg>
      {/* Legende */}
      <div
        style={{
          fontSize: 12,
          opacity: 0.9,
          marginTop: 8,
          display: "flex",
          gap: 16,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <LegendIcon label="Status OK">
          <NodeIcon fail={false} dpp={false} modular={false} />
        </LegendIcon>
        <LegendIcon label="Status FAIL">
          <NodeIcon fail />
        </LegendIcon>
        <LegendIcon label="Linked DPP">
          <NodeIcon dpp />
        </LegendIcon>
        <LegendIcon label="modular">
          <NodeIcon modular />
        </LegendIcon>
        <span style={{ color: "var(--bs-secondary)" }}>Klick = expand/collapse · optional onNodeClick</span>
      </div>
    </div>
  );
}
function NodeIcon({ fail = false, dpp = false, modular = false }) {
  const fill = fail ? "var(--bs-danger)" : "var(--bs-success)";
  return (
    <svg width="40" height="32" viewBox="-20 -16 40 32" aria-hidden="true">
      <circle r="8" fill={fill} stroke="var(--bs-secondary)" strokeWidth="1.5" />
      {dpp ? <circle r="12" fill="none" stroke="var(--bs-info)" strokeWidth="2" /> : null}
      {modular ? <circle r="16" fill="none" stroke="var(--bs-primary)" strokeDasharray="4 3" strokeWidth="2" /> : null}
    </svg>
  );
}
function LegendIcon({ label, children }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      {children}
      <span>{label}</span>
    </span>
  );
}
