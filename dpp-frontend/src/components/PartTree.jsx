// src/components/PartTree.jsx
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, ListGroup, Spinner } from "react-bootstrap";
import Table from "react-bootstrap/Table";
import { Link } from "react-router-dom";

import { api } from "../api";
import { FIELD_HELP } from "../content/fieldHelp";
import InfoTip from "../shared/InfoTip";
import PieChart from "../shared/PieChart";
import StructureTree from "../shared/StructureTree";

export default function PartTree({
  rootParts = [],
  showModular = false,
  showAvvDispose = false,
  showPurity = false,
  linkedDppMap = {},
}) {
  if (!Array.isArray(rootParts) || rootParts.length === 0) {
    return <div className="text-muted">No subparts.</div>;
  }
  const isSingleRoot = rootParts.length === 1;
  return (
    <div className="d-flex flex-column">
      {rootParts.map((part) => (
        <PartNode
          key={part.id}
          node={part}
          showModular={showModular}
          showAvvDispose={showAvvDispose}
          showPurity={showPurity}
          linkedDppMap={linkedDppMap}
          isRoot={isSingleRoot}
        />
      ))}
    </div>
  );
}

function getPartName(raw) {
  return (
    raw?.partStaticLink?.name ||
    raw?.partStaticLink?.document?.name ||
    raw?.name ||
    raw?.partStatic?.name ||
    raw?.id ||
    "Part"
  );
}

function normalizeChildren(rawChildren) {
  const list = Array.isArray(rawChildren) ? rawChildren : Array.isArray(rawChildren?.items) ? rawChildren.items : [];
  return list.map((child) => ({
    id: child?.id || child?._id || child,
    name: getPartName(child),
    hasFailstate: !!child?.hasFailstate,
    isModular: !!child?.isModular,
  }));
}

function extractMaterialItems(materials) {
  return materials?.materials || materials?.data || materials?.list || [];
}

function toPieSegments(items) {
  return (items || []).map((row) => ({
    label: row.material_name || row.name || "Material",
    value:
      typeof row.share_pct === "number"
        ? row.share_pct
        : typeof row.percent === "number"
          ? row.percent
          : Number(row.weight_g || 0),
  }));
}

function toPurityPct(row) {
  const f = (v) => (Number.isFinite(v) ? Number(v) : NaN);
  if (Number.isFinite(row?.purity_percent)) {
    return Number(row.purity_percent) * 100;
  }

  const frac =
    f(row?.purityPercent) ??
    f(row?.avg_purity_fraction) ??
    (Number.isFinite(row?.purityLevel) && row.purityLevel <= 1 ? f(row.purityLevel) : NaN);

  if (Number.isFinite(frac)) return frac * 100;

  const pct = f(row?.avg_purity_pct);
  if (Number.isFinite(pct)) return pct;

  const level = f(row?.purityLevel);
  if (Number.isFinite(level)) {
    return level <= 1 ? level * 100 : level;
  }

  return NaN;
}

function toRecycledRows(items) {
  return (items || []).map((row) => ({
    name: row.material_name || row.name || "Material",
    grams: Number(row.weight_g ?? row.mass ?? 0) || 0,
    recycledPercent:
      typeof row.recycled_share_pct === "number"
        ? row.recycled_share_pct
        : typeof row.recycledPercent === "number"
          ? row.recycledPercent
          : 0,
    virginPercent:
      typeof row.recycled_share_pct === "number"
        ? Math.max(0, 100 - row.recycled_share_pct)
        : typeof row.virginPercent === "number"
          ? row.virginPercent
          : 0,
    purityPct: toPurityPct(row),
  }));
}

function getTotalWeight(materials) {
  if (typeof materials?.total_weight_g === "number") return materials.total_weight_g;
  if (typeof materials?.total === "number") return materials.total;
  return null;
}
function getOverallRecycled(materials) {
  if (typeof materials?.total_recycled_share_pct === "number") return materials.total_recycled_share_pct;
  if (typeof materials?.overallRecycledPercent === "number") return materials.overallRecycledPercent;
  return 0;
}
function getRareEarthShare(materials) {
  if (typeof materials?.rare_earth_share_pct === "number") return materials.rare_earth_share_pct;
  if (typeof materials?.rareEarthPercent === "number") return materials.rareEarthPercent;
  return 0;
}

function isRareMaterialName(name) {
  return /ndfeb|magnet|rare/i.test(String(name || ""));
}

async function fetchAvvCode(partId) {
  try {
    const full = await api.getPartInstance(partId);
    const staticLike = full?.partStaticLink?.document || full?.partStaticLink || full?.partStatic || null;
    return staticLike?.avv_dispose || staticLike?.avvDispose || staticLike?.AVV || null;
  } catch {
    return null;
  }
}

function PartNode({ node, showModular, showAvvDispose, showPurity, linkedDppMap, isRoot = false }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const [materials, setMaterials] = useState(null);
  const [materialsError, setMaterialsError] = useState(null);
  const [children, setChildren] = useState(null);

  const [avvCode, setAvvCode] = useState(null);
  const [avvLoaded, setAvvLoaded] = useState(false);

  const nodeName = getPartName(node);
  const nodeId = node?.id;
  const dppEntry = nodeId ? linkedDppMap?.[nodeId] : null;

  useEffect(() => {
    let alive = true;
    if (!showAvvDispose || !nodeId) {
      setAvvLoaded(false);
      setAvvCode(null);
      return;
    }
    (async () => {
      setAvvLoaded(false);
      const code = await fetchAvvCode(nodeId);
      if (!alive) return;
      setAvvCode(code || null);
      setAvvLoaded(true);
    })();
    return () => {
      alive = false;
    };
  }, [nodeId, showAvvDispose]);

  useEffect(() => {
    let alive = true;
    if (!isExpanded || !nodeId) return;

    async function loadExpanded() {
      setIsLoading(true);
      setMaterialsError(null);

      const loadMaterials = (async () => {
        try {
          const json = await api.getPartMaterials(nodeId);
          if (!alive) return;
          setMaterials(json || null);
        } catch (err) {
          if (!alive) return;
          const msg = String(err?.message || "");
          if (msg.startsWith("404")) {
            setMaterials(null);
            setMaterialsError(null);
          } else {
            setMaterials(null);
            setMaterialsError(msg);
          }
        }
      })();

      const loadChildren = (async () => {
        try {
          const kids = await api.getPartChildren(nodeId);
          if (!alive) return;
          setChildren(normalizeChildren(kids));
        } catch {
          try {
            const full = await api.getPartInstance(nodeId);
            if (!alive) return;
            setChildren(normalizeChildren(full?.compositeParts || []));
          } catch {
            if (!alive) return;
            setChildren([]);
          }
        }
      })();

      await Promise.all([loadMaterials, loadChildren]);
      if (alive) setIsLoading(false);
    }

    loadExpanded();
    return () => {
      alive = false;
    };
  }, [isExpanded, nodeId]);

  const items = useMemo(() => extractMaterialItems(materials), [materials]);
  const pieData = useMemo(() => toPieSegments(items), [items]);
  const recycledRows = useMemo(() => toRecycledRows(items), [items]);

  const totalWeight = getTotalWeight(materials);
  const overallRecycled = getOverallRecycled(materials);
  const rareEarthShare = getRareEarthShare(materials);

  const onToggleExpand = useCallback(() => setIsExpanded((v) => !v), []);

  const purityVariant = (purityPct) => {
    if (!Number.isFinite(purityPct)) return null;
    if (purityPct >= 99) return "success";
    if (purityPct >= 95) return "warning";
    return "danger";
  };
  const recycledVariant = (recycledPct) => {
    if (!Number.isFinite(recycledPct)) return null;
    if (recycledPct >= 50) return "success";
    if (recycledPct >= 20) return "warning";
    return "danger";
  };

  return (
    <Card className="mb-3" data-part-id={nodeId}>
      {/* Header */}
      <Card.Header className="d-flex align-items-center justify-content-between">
        <div className="d-flex align-items-center gap-2" style={{ minWidth: 0 }}>
          {dppEntry ? (
            <Link
              to={`/dpp/${dppEntry.dppId}/user`}
              className="fw-semibold text-truncate"
              title={nodeName}
              style={{ textDecoration: "none" }}
            >
              {nodeName}
            </Link>
          ) : (
            <span className="fw-semibold text-truncate" title={nodeName}>
              {nodeName}
            </span>
          )}

          <span className={`badge ${node?.hasFailstate ? "bg-danger" : "bg-success"}`}>
            {node?.hasFailstate ? "fail" : "no-fail"}
          </span>

          {/* DPP badge – NICHT beim Root anzeigen */}
          {!isRoot && (
            <span className={`badge ${dppEntry ? "bg-info text-dark" : "bg-secondary"}`}>
              {dppEntry ? "dpp" : "no-dpp"}
            </span>
          )}

          {showModular && (
            <span className={`badge ${node?.isModular ? "bg-primary" : "bg-secondary"}`}>
              {node?.isModular ? "modular" : "non-modular"}
            </span>
          )}

          {showAvvDispose && (
            <span className="badge bg-light text-dark" title="AVV (disposal code)">
              AVV: {avvLoaded ? (avvCode ? String(avvCode) : "not available") : "…"}
            </span>
          )}
        </div>

        <Button size="sm" variant="outline-secondary" onClick={onToggleExpand}>
          {isExpanded ? "Collapse" : "Expand"}
        </Button>
      </Card.Header>

      {isExpanded && (
        <Card.Body style={{ overflowX: "auto" }}>
          {isLoading && (
            <div className="py-2 text-center">
              <Spinner animation="border" size="sm" />
            </div>
          )}

          {!isLoading && (
            <>
              <div className="fw-semibold mb-2 d-flex align-items-center justify-content-between">
                <span>Material composition</span>
                <InfoTip
                  text={FIELD_HELP["materials.distribution"] || FIELD_HELP["materials.title"]}
                  placement="left"
                />
              </div>

              {dppEntry && (
                <div className="mb-3">
                  <div className="fw-semibold d-flex align-items-center justify-content-between">
                    <span>Linked DPP</span>
                    <InfoTip text={FIELD_HELP["dpplinks.header"]} placement="left" />
                  </div>
                  <div>
                    <Link to={`/dpp/${dppEntry.dppId}/user`} className="wrap">
                      {dppEntry.productName || dppEntry.partName || dppEntry.dppId}
                    </Link>
                  </div>
                </div>
              )}

              {materialsError ? (
                <Alert variant="danger">Materials error: {materialsError}</Alert>
              ) : items && items.length > 0 ? (
                <div
                  className="d-flex flex-column flex-md-row align-items-start gap-3 mb-3"
                  style={{ contain: "layout paint", overflow: "visible" }}
                >
                  {/* Pie chart */}
                  <div
                    style={{
                      flex: "0 0 auto",
                      width: 320,
                      height: 320,
                      display: "grid",
                      placeItems: "center",
                      overflow: "visible",
                    }}
                  >
                    <PieChart
                      width={320}
                      height={320}
                      data={pieData}
                      showLegend={false}
                      showLegendPerc
                      showSliceLabels
                      minSliceLabelPercent={1}
                    />
                  </div>

                  <div className="flex-grow-1" style={{ minWidth: 0, wordBreak: "break-word" }}>
                    <div className="fw-semibold mb-1 d-flex align-items-center justify-content-between">
                      <span>Summary</span>
                      <InfoTip text={FIELD_HELP["materials.title"]} placement="left" />
                    </div>

                    <ListGroup variant="flush" className="mb-2">
                      {typeof totalWeight === "number" && (
                        <KV label="Total" tipKey="materials.totalWeight">
                          {totalWeight.toFixed(1)} g
                        </KV>
                      )}
                      <KV label="Overall recycled" tipKey="materials.recycled">
                        {Number(overallRecycled).toFixed(1)}%
                      </KV>
                      <KV label="Rare earth content" tipKey="materials.rare">
                        {Number(rareEarthShare).toFixed(2)}%
                      </KV>
                    </ListGroup>
                    <div className="fw-semibold mt-2 mb-2 d-flex align-items-center justify-content-between">
                      <span>Per material</span>
                      <InfoTip text={FIELD_HELP["materials.perMaterial"]} placement="left" />
                    </div>

                    <div className="table-responsive">
                      <Table bordered size="sm" className="mb-0 align-middle">
                        <thead>
                          <tr>
                            <th style={{ width: showPurity ? "40%" : "45%" }}>Material</th>
                            <th style={{ width: "20%" }} className="text-end">
                              Mass (g)
                            </th>
                            <th style={{ width: showPurity ? "13.5%" : "17.5%" }} className="text-end">
                              <div className="d-flex align-items-center justify-content-end gap-2">
                                <span>Recycled %</span>
                                <InfoTip text={FIELD_HELP["materials.recycled"]} placement="left" />
                              </div>
                            </th>
                            {showPurity && (
                              <th style={{ width: "13.5%" }} className="text-end">
                                <div className="d-flex align-items-center justify-content-end gap-2">
                                  <span>Avg. Purity %</span>
                                  <InfoTip text={FIELD_HELP["purity.avg"]} placement="left" />
                                </div>
                              </th>
                            )}
                            <th style={{ width: "13.5%" }} className="text-end">
                              New %
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {recycledRows.map((row) => {
                            const rare = isRareMaterialName(row.name);
                            const recPct = Number(row.recycledPercent || 0);
                            const purityPct = Number(row.purityPct);

                            const recBg = recycledVariant(recPct);
                            const purityBg = purityVariant(purityPct);

                            return (
                              <tr key={row.name}>
                                <td
                                  className="d-flex align-items-center gap-2"
                                  style={rare ? { background: "var(--warn-bg)" } : undefined}
                                >
                                  {rare && (
                                    <Badge bg="warning" text="dark">
                                      rare-earth
                                    </Badge>
                                  )}
                                  <span style={{ fontWeight: rare ? 600 : 400 }}>{row.name}</span>
                                </td>
                                <td className="text-end">{row.grams.toFixed(1)}</td>
                                <td className="text-end">
                                  {Number.isFinite(recPct) ? <Badge bg={recBg}>{recPct.toFixed(1)}%</Badge> : "—"}
                                </td>
                                {showPurity && (
                                  <td className="text-end">
                                    {Number.isFinite(purityPct) ? (
                                      <Badge bg={purityBg}>{purityPct.toFixed(1)}%</Badge>
                                    ) : (
                                      "—"
                                    )}
                                  </td>
                                )}
                                <td className="text-end">{Number(row.virginPercent || 0).toFixed(1)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </Table>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-muted">No materials available.</div>
              )}
              <div style={{ height: 8 }} />
              {children && children.length > 0 && (
                <>
                  <div className="fw-semibold mt-2 mb-2 d-flex align-items-center justify-content-between">
                    <span>Structure of parts</span>
                    <InfoTip text={FIELD_HELP["componenttree.title"]} placement="left" />
                  </div>
                  <div className="mb-2">
                    <StructureTree
                      root={{
                        id: nodeId,
                        name: nodeName,
                        hasFailstate: !!node?.hasFailstate,
                        isModular: !!node?.isModular,
                      }}
                      initialChildren={children}
                      dppMap={linkedDppMap}
                      loadChildren={async (partId) => {
                        try {
                          const kids = await api.getPartChildren(partId);
                          return normalizeChildren(kids);
                        } catch {
                          try {
                            const full = await api.getPartInstance(partId);
                            return normalizeChildren(full?.compositeParts || []);
                          } catch {
                            return [];
                          }
                        }
                      }}
                      onNodeClick={(n) => {
                        const el = document.querySelector(`[data-part-id="${n.id}"]`);
                        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
                      }}
                    />
                  </div>
                </>
              )}
              <div className="fw-semibold mt-2 mb-2 d-flex align-items-center justify-content-between">
                <span>Subparts</span>
                <InfoTip text={FIELD_HELP["parts.subparts"] || FIELD_HELP["parts.title"]} placement="left" />
              </div>

              {children && children.length > 0 ? (
                <div className="d-flex flex-column">
                  {children.map((child) => (
                    <PartNode
                      key={child.id}
                      node={child}
                      showModular={showModular}
                      showAvvDispose={showAvvDispose}
                      showPurity={showPurity}
                      linkedDppMap={linkedDppMap}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-muted">No subparts.</div>
              )}
            </>
          )}
        </Card.Body>
      )}
    </Card>
  );
}

/**
 * Key/Value List item.
 */
function KV({ label, tipKey, children, tipPlacement = "left" }) {
  return (
    <ListGroup.Item className="px-0 d-flex justify-content-between align-items-start gap-2">
      <div className="wrap">
        <span className="text-muted">{label}</span>: <span className="ms-1">{children ?? "—"}</span>
      </div>
      <InfoTip text={FIELD_HELP[tipKey]} placement={tipPlacement} className="ms-2 text-muted flex-shrink-0" />
    </ListGroup.Item>
  );
}
