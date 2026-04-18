// src/pages/OverView.jsx
import React, { useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Col, Container, ListGroup, Row, Spinner, Table } from "react-bootstrap";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import PartTree from "../components/PartTree";
import { FIELD_HELP } from "../content/fieldHelp";
import ImageSlider from "../shared/ImageSlider";
import InfoTip from "../shared/InfoTip";
import PieChart from "../shared/PieChart";
import ProcessMap from "../shared/ProcessMap";
import ReturningPlacesMap from "../shared/ReturningPlacesMap";
import { toApiURL } from "../shared/toApiURL";

export default function OverView() {
  const { instanceId } = useParams();
  const [summary, setSummary] = useState(null);
  const [instance, setInstance] = useState(null);
  const [processMap, setProcessMap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let on = true;
    setLoading(true);
    setErr(null);
    setSummary(null);
    setInstance(null);
    setProcessMap(null);

    (async () => {
      try {
        const s = await api.getOverviewSummary(instanceId);
        if (!on) return;
        setSummary(s);

        try {
          const m = await api.getProcessMap(instanceId);
          if (on) setProcessMap(m);
        } catch {
          if (on) setProcessMap(null);
        }

        try {
          const inst = await api.getInstance(instanceId);
          if (on) setInstance(inst);
        } catch {}
      } catch {
        try {
          const inst = await api.getInstance(instanceId);
          if (!on) return;
          setInstance(inst);
        } catch (e2) {
          if (!on) return;
          setErr(e2.message || String(e2));
        }
      } finally {
        if (on) setLoading(false);
      }
    })();

    return () => {
      on = false;
    };
  }, [instanceId]);

  useEffect(() => {
    if (!summary && !instance) return;
    try {
      window.__SNAPSHOT__ = {
        route: "user",
        instanceId,
        data: { summary, instance, processMap },
        generatedAt: new Date().toISOString(),
      };
    } catch {}
  }, [summary, instance, processMap, instanceId]);

  const linkedDppMap = useMemo(() => {
    const m = {};
    (summary?.linkedDpps || []).forEach((it) => {
      if (it?.partId && it?.dppId) m[it.partId] = { dppId: it.dppId, partName: it.partName };
    });
    return m;
  }, [summary]);

  if (loading)
    return (
      <Container className="py-4 text-center">
        <Spinner animation="border" />
      </Container>
    );
  if (err)
    return (
      <Container className="py-4">
        <Alert variant="danger">Error: {err}</Alert>
      </Container>
    );
  if (!summary && !instance) return <Container className="py-4">No data.</Container>;

  const title = summary?.productName || instance?.dppStaticLink?.name || "Product";
  const discontinued = !!instance?.discontinued;

  const images = (summary?.images || []).map((i) => {
    const raw = typeof i === "string" ? i : (i?.url ?? i?.src ?? "");
    return { src: toApiURL(raw), alt: (typeof i === "object" && (i.filename || i.title)) || "image" };
  });

  const counters = summary?.counters || {
    cleaning: summary?.cleaningCount ?? instance?.cleaningCount,
    chalk: summary?.chalkCount ?? instance?.chalkCount,
    brewing: summary?.brewingCount ?? instance?.brewingCount,
    grinding: summary?.coffeeGrindingCount ?? instance?.coffeeGrindingCount,
    operatingHRS: summary?.operatingHRS ?? instance?.operatingHRS,
  };

  const topPart = instance?.partInstanceLink
    ? {
        id: instance.partInstanceLink.id,
        name:
          instance.partInstanceLink?.partStaticLink?.name ||
          instance.partInstanceLink?.partStaticLink?.document?.name ||
          instance.partInstanceLink?.name ||
          instance.partInstanceLink?.id,
        hasFailstate: !!instance.partInstanceLink?.hasFailstate,
        isModular: !!instance.partInstanceLink?.isModular,
      }
    : null;

  const rootParts = topPart
    ? [topPart]
    : (Array.isArray(summary?.parts?.firstLevel) && summary.parts.firstLevel.length > 0
        ? summary.parts.firstLevel
        : instance?.partInstanceLink?.compositeParts) || [];

  const matByName = summary?.materials?.byName || [];
  const matByNameRecycled = summary?.materials?.byNameRecycled || [];
  const overallRecycledPct = Number(summary?.materials?.overallRecycledPercent || 0);
  const rareEarthPct = Number(summary?.materials?.rareEarthPercent || 0);

  const topLevelPie = matByName.map((m) => ({
    label: m.name,
    value: Number(m.mass ?? 0) || Number(m.percent ?? 0),
  }));

  const extra = summary?.extraStatic || {};
  const processSteps = summary?.processSteps || {};
  const ghg = summary?.ghg || { unit: "kgCO2e", scopes: {}, byCategory: {} };

  const declDate = summary?.dateOfDeclaration;
  const endG = summary?.endOfGuarantee;
  const pubDate = summary?.dateOfPublication;

  const fmtDate = (v) => {
    if (!v) return "—";
    try {
      const d = new Date(v);
      if (Number.isNaN(d.getTime())) return String(v);
      return d.toLocaleDateString();
    } catch {
      return String(v);
    }
  };

  const orgLine = (org) => {
    if (!org) return "—";
    const bits = [];
    const nameEl = org.url ? (
      <a href={org.url} target="_blank" rel="noreferrer">
        {org.name || org.id}
      </a>
    ) : (
      org.name || org.id
    );
    bits.push(nameEl);
    if (org.eoriNumber) bits.push(<span key="e"> • EORI {org.eoriNumber}</span>);
    if (org.lucidNumber) bits.push(<span key="l"> • LUCID {org.lucidNumber}</span>);
    return <>{bits}</>;
  };

  const hasFails = !!summary?.failState?.hasAny;
  const failCount = Number(summary?.failState?.count || 0);
  const totalPartsInTree = Number(summary?.parts?.totalCount || 0);
  const healthyCount = Math.max(0, totalPartsInTree - failCount);

  const tdistRaw = summary?.transportDistance ?? summary?.transport?.distance ?? null;
  const km = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    return n.toLocaleString(undefined, { maximumFractionDigits: 3 });
  };
  const distTotals = {
    total: (tdistRaw && (tdistRaw.totalKM ?? tdistRaw.total_km ?? tdistRaw.total)) ?? null,
    parts: (tdistRaw && (tdistRaw.partsKM ?? tdistRaw.parts_km ?? tdistRaw.parts)) ?? null,
    materials: (tdistRaw && (tdistRaw.materialsKM ?? tdistRaw.materials_km ?? tdistRaw.materials)) ?? null,
  };

  return (
    <Container className="py-3 pb-5">
      <style>{`.wrap { white-space: normal !important; word-break: break-word !important; overflow-wrap: anywhere !important; }`}</style>

      {/* Header */}
      <Row className="align-items-center mb-2">
        <Col>
          <h2 className="mb-0 d-flex align-items-center gap-2">
            <span>{title}</span>
            <Badge bg={discontinued ? "secondary" : "success"}>{discontinued ? "Discontinued" : "Active"}</Badge>
          </h2>
          <div className="text-muted">
            <span className="me-3">
              <b>Declaration</b>: {fmtDate(declDate)}
              <InfoTip className="ms-2" text={FIELD_HELP["dates.declaration"]} />
            </span>
            <span className="me-3">
              <b>Published</b>: {fmtDate(pubDate)}
              <InfoTip className="ms-2" text={FIELD_HELP["dates.published"]} />
            </span>
          </div>
        </Col>
        <Col xs="auto" className="d-flex align-items-center gap-2">
          <Button as={Link} to="/" variant="link">
            ← Back to selection
          </Button>
        </Col>
      </Row>

      {/* Status */}
      <Row className="mb-3">
        <Col>
          <Card>
            <Card.Body className="py-2 d-flex align-items-center">
              {hasFails ? (
                <span className="text-danger me-2" title="Issues detected" style={{ fontSize: 18 }}>
                  ⚠️
                </span>
              ) : (
                <span className="text-success me-2" title="All systems OK" style={{ fontSize: 18 }}>
                  ✅
                </span>
              )}
              <div className="fw-semibold me-2">Status:</div>
              <div>
                <b>{healthyCount}</b>/<b>{totalPartsInTree}</b> {healthyCount === 1 ? "part" : "parts"} OK
                <InfoTip className="ms-2" text={FIELD_HELP["status.overall"]} />
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Top row */}
      <Row className="gy-3">
        <Col xs={12} lg={4}>
          {/* General information */}
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>General information</span>
              <InfoTip text={FIELD_HELP["general.title"]} placement="left" />
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <KV label="GTIN" tipKey="general.gtin">
                  <span className="wrap">{summary?.gtin || "—"}</span>
                </KV>

                <KV label="GS1 Digital Link" tipKey="general.gs1">
                  {summary?.gs1DigitalLink ? (
                    <a className="wrap" href={summary.gs1DigitalLink} target="_blank" rel="noreferrer">
                      {summary.gs1DigitalLink}
                    </a>
                  ) : (
                    <span className="wrap">—</span>
                  )}
                </KV>

                <KV label="Responsible operator" tipKey="org.responsible">
                  <span className="wrap">{orgLine(summary?.responsibleOperator)}</span>
                </KV>

                <KV label="Manufacturer" tipKey="org.manufacturer">
                  <span className="wrap">{orgLine(summary?.manufacturer)}</span>
                </KV>

                <KV label="Importer" tipKey="org.importer">
                  <span className="wrap">{orgLine(summary?.importer)}</span>
                </KV>
              </ListGroup>
            </Card.Body>
          </Card>

          {/* Specs */}
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Specs</span>
              <InfoTip text={FIELD_HELP["specs.title"]} placement="left" />
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <KV label="Height" tipKey="specs.heightCM">
                  {extra.heightCM ?? "—"} cm
                </KV>
                <KV label="Width" tipKey="specs.widthCM">
                  {extra.widthCM ?? "—"} cm
                </KV>
                <KV label="Depth" tipKey="specs.depthCM">
                  {extra.depthCM ?? "—"} cm
                </KV>
                <KV label="Weight" tipKey="specs.weightGRM">
                  {extra.weightGRM ?? "—"} g
                </KV>
                <KV label="TARIC code" tipKey="specs.taricCode">
                  {extra.taricCode ?? "—"}
                </KV>
              </ListGroup>
            </Card.Body>
          </Card>

          {/* Guarantee */}
          <Card className="mb-3">
            <Card.Header className="h6">Guarantee</Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <KV label="Valid until" tipKey="guarantee.validUntil">
                  {fmtDate(endG)}
                </KV>
              </ListGroup>

              {summary?.guaranteeDescription ? (
                <>
                  <div className="h6 mt-3 mb-1 d-flex align-items-center justify-content-between">
                    <span>Details</span>
                    <InfoTip text={FIELD_HELP["guarantee.description"]} placement="left" />
                  </div>
                  <div className="text-muted wrap">{summary.guaranteeDescription}</div>
                </>
              ) : null}
            </Card.Body>
          </Card>

          {/* Usage counters */}
          <Card className="mb-3">
            <Card.Header className="h6">Usage counters</Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <KV label="Operating hours" tipKey="counters.operatingHRS">
                  {safeNum(counters?.operatingHRS)}
                </KV>
                <KV label="Cleaning cycles" tipKey="counters.cleaning">
                  {safeNum(counters?.cleaning)}
                </KV>
                <KV label="Descaling (chalk)" tipKey="counters.chalk">
                  {safeNum(counters?.chalk)}
                </KV>
                <KV label="Brewing cycles" tipKey="counters.brewing">
                  {safeNum(counters?.brewing)}
                </KV>
                <KV label="Grinding cycles" tipKey="counters.grinding">
                  {safeNum(counters?.grinding)}
                </KV>
              </ListGroup>
            </Card.Body>
          </Card>
        </Col>

        {/* Images */}
        <Col xs={12} lg={8}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Images</span>
              <InfoTip text={FIELD_HELP["images.title"]} placement="left" />
            </Card.Header>
            <Card.Body>
              <div style={{ maxWidth: 640 }}>
                <ImageSlider images={images} placeholderHeight={320} />
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Materials */}
      <Row className="gy-3">
        <Col xs={12} lg={8}>
          <Card className="mb-3">
            <Card.Header className="h6">
              Materials <InfoTip className="ms-1" text={FIELD_HELP["materials.title"]} />
            </Card.Header>
            <Card.Body>
              <Row className="gy-3">
                <Col xs={12} md="auto">
                  <div style={{ minWidth: 320 }}>
                    <div className="fw-semibold mb-2">
                      Distribution by name <InfoTip className="ms-1" text={FIELD_HELP["materials.distribution"]} />
                    </div>
                    <PieChart
                      width={320}
                      height={320}
                      data={topLevelPie}
                      showLegendPerc
                      showSliceLabels
                      minLabelPercent={1}
                    />
                  </div>
                </Col>
                <Col>
                  <div className="fw-semibold">Summary</div>
                  <div>
                    <b>Overall recycled</b>: {overallRecycledPct.toFixed(1)}%
                    <InfoTip className="ms-1" text={FIELD_HELP["materials.recycled"]} />
                  </div>
                  <div>
                    <b>Rare earth content</b>: {rareEarthPct.toFixed(2)}%
                    <InfoTip className="ms-1" text={FIELD_HELP["materials.rare"]} />
                  </div>

                  <div className="fw-semibold mt-3 mb-1">
                    Per material <InfoTip className="ms-1" text={FIELD_HELP["materials.perMaterial"]} />
                  </div>
                  {matByName.length ? (
                    <Table size="sm" bordered responsive>
                      <thead>
                        <tr>
                          <th>Material</th>
                          <th className="text-end">Mass (g)</th>
                          <th className="text-end">Recycled %</th>
                        </tr>
                      </thead>
                      <tbody>
                        {matByName.map((base) => {
                          const rec = (matByNameRecycled || []).find((x) => x.name === base.name);
                          return (
                            <tr key={base.name}>
                              <td className="wrap">{base.name}</td>
                              <td className="text-end">{Number(base.mass ?? 0).toLocaleString()}</td>
                              <td className="text-end">{Number(rec?.recycledPercent ?? 0).toFixed(1)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </Table>
                  ) : (
                    <div className="text-muted">No data.</div>
                  )}
                </Col>
              </Row>
            </Card.Body>
          </Card>

          {/* Parts */}
          <Card className="mb-3">
            <Card.Header className="h6">
              Parts <InfoTip className="ms-1" text={FIELD_HELP["parts.title"]} />
            </Card.Header>
            <Card.Body>
              <div className="mb-2 d-flex align-items-center gap-3 flex-wrap">
                <div>
                  <strong>Total parts in device</strong>{" "}
                  <InfoTip className="ms-1" text={FIELD_HELP["parts.totalInTree"]} />:{" "}
                  {summary?.parts?.totalCount ?? "—"}
                </div>
                <div className="d-flex align-items-center">
                  <span className={`me-2 ${hasFails ? "text-danger" : "text-success"}`} style={{ fontSize: 16 }}>
                    {hasFails ? "⚠️" : "✅"}
                  </span>
                  <span>
                    <strong>Status of entire product</strong>{" "}
                    <InfoTip className="ms-1" text={FIELD_HELP["parts.statusOverall"]} />:{" "}
                    <>
                      <b>{healthyCount}</b>/<b>{totalPartsInTree}</b> OK
                    </>
                  </span>
                </div>
              </div>
              {/* Map mitgeben */}
              <PartTree rootParts={rootParts} showModular={false} linkedDppMap={linkedDppMap} />
            </Card.Body>
          </Card>
          {/* Production journey map */}
          <Card className="mb-3">
            <Card.Header className="h6">
              Production journey map <InfoTip className="ms-1" text={FIELD_HELP["journey.title"]} />
            </Card.Header>
            <Card.Body>
              {processMap?.nodes?.length ? (
                <>
                  <div className="mb-2">
                    <ProcessMap data={processMap} height={360} />
                  </div>
                  <div className="text-muted small">
                    <span className="me-3">
                      <span style={{ color: "#2ca02c" }}>■</span> Production
                    </span>
                    <span className="me-3">
                      <span style={{ color: "#1f77b4" }}>■</span> Transport
                    </span>
                    <span className="me-3">
                      <span style={{ color: "#d62728" }}>■</span> Secondary
                    </span>
                  </div>
                </>
              ) : (
                <div className="text-muted">No map data.</div>
              )}
            </Card.Body>
          </Card>

          {/* Process steps summary + GHG + Distance */}
          <Card className="mb-3">
            <Card.Header className="h6">
              Process steps <InfoTip className="ms-1" text={FIELD_HELP["process.title"]} />
            </Card.Header>
            <Card.Body>
              <Row>
                <Col xs={12} md={6}>
                  <ListGroup variant="flush">
                    <KV label="Total" tipKey="process.total">
                      {processSteps.total ?? 0}
                    </KV>
                    <KV label="Production" tipKey="process.production">
                      {processSteps.production ?? 0}
                    </KV>
                    <KV label="Transport" tipKey="process.transport">
                      {processSteps.transport ?? 0}
                    </KV>
                    <KV label="Secondary value steps" tipKey="process.secondary">
                      {processSteps.secondary ?? 0}
                    </KV>
                  </ListGroup>
                </Col>
                <Col xs={12} md={6}>
                  <div className="fw-semibold d-flex align-items-center justify-content-between">
                    <span>GHG emissions ({ghg.unit || "kgCO2e"})</span>
                    <InfoTip text={FIELD_HELP["ghg.header"]} placement="left" />
                  </div>
                  {(() => {
                    const scopes = ghg.scopes || {};
                    const total = Number(ghg.total ?? Object.values(scopes).reduce((a, b) => a + Number(b || 0), 0));
                    return (
                      <>
                        <ListGroup variant="flush" className="mb-2">
                          <KV label="Total" tipKey="ghg.total">
                            {Number.isFinite(total) ? total.toLocaleString() : "—"}
                          </KV>
                        </ListGroup>
                        <div className="fw-semibold small text-muted d-flex align-items-center justify-content-between">
                          <span>By scope</span>
                          <InfoTip text={FIELD_HELP["ghg.scopes"]} placement="left" />
                        </div>
                        <ListGroup variant="flush" className="mb-2">
                          {Object.entries(scopes).map(([k, v]) => (
                            <ListGroup.Item
                              key={k}
                              className="px-0 d-flex justify-content-between align-items-start gap-2"
                            >
                              <div className="wrap">
                                <span className="text-muted">{k}</span>:{" "}
                                <span className="ms-1">{Number(v).toLocaleString()}</span>
                              </div>
                            </ListGroup.Item>
                          ))}
                        </ListGroup>
                      </>
                    );
                  })()}
                  {Object.keys(ghg.byCategory || {}).length ? (
                    <>
                      <div className="fw-semibold mt-3 d-flex align-items-center justify-content-between">
                        <span>By scope 3 category</span>
                        <InfoTip text={FIELD_HELP["ghg.byCategory"]} placement="left" />
                      </div>
                      <ListGroup variant="flush">
                        {Object.entries(ghg.byCategory).map(([k, v]) => (
                          <ListGroup.Item
                            key={k}
                            className="px-0 d-flex justify-content-between align-items-start gap-2"
                          >
                            <div className="wrap">
                              <span className="text-muted">{k}</span>:{" "}
                              <span className="ms-1">{Number(v).toLocaleString()}</span>
                            </div>
                          </ListGroup.Item>
                        ))}
                      </ListGroup>
                    </>
                  ) : null}

                  {tdistRaw ? (
                    <>
                      <div className="fw-semibold mt-3 d-flex align-items-center justify-content-between">
                        <span>Transport distance (km)</span>
                        <InfoTip text={FIELD_HELP["transport.header"]} placement="left" />
                      </div>
                      <ListGroup variant="flush">
                        <KV label="Total" tipKey="transport.total">
                          {km(distTotals.total)}
                        </KV>
                        <KV label="Parts steps" tipKey="transport.parts">
                          {km(distTotals.parts)}
                        </KV>
                        <KV label="Material steps" tipKey="transport.materials">
                          {km(distTotals.materials)}
                        </KV>
                      </ListGroup>
                    </>
                  ) : null}
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>

        {/* Right column */}
        <Col xs={12} lg={4}>
          <Card className="mb-3">
            <Card.Header className="h6">
              Compliance certificates <InfoTip className="ms-1" text={FIELD_HELP["compliance.title"]} />
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush" className="mb-2">
                {[
                  ...(summary?.compliance?.ceConformityDeclaration ? [summary.compliance.ceConformityDeclaration] : []),
                  ...(summary?.compliance?.ecodesignConformityDeclaration
                    ? [summary.compliance.ecodesignConformityDeclaration]
                    : []),
                ].length ? (
                  [
                    ...(summary?.compliance?.ceConformityDeclaration
                      ? [summary.compliance.ceConformityDeclaration]
                      : []),
                    ...(summary?.compliance?.ecodesignConformityDeclaration
                      ? [summary.compliance.ecodesignConformityDeclaration]
                      : []),
                  ].map((c, i) => (
                    <ListGroup.Item
                      key={i}
                      className="px-0 wrap d-flex justify-content-between align-items-start gap-2"
                    >
                      <div className="wrap">
                        {c?.url ? (
                          <a href={c.url} target="_blank" rel="noreferrer">
                            {c?.name || c.url}
                          </a>
                        ) : (
                          c?.name || "—"
                        )}
                      </div>
                    </ListGroup.Item>
                  ))
                ) : (
                  <div className="text-muted">No certificates.</div>
                )}
              </ListGroup>

              <div className="h6 d-flex align-items-center justify-content-between">
                <span>Documents</span>
                <InfoTip text={FIELD_HELP["documents.title"]} placement="left" />
              </div>
              {Array.isArray(summary?.documents) && summary.documents.length ? (
                <ListGroup variant="flush">
                  {summary.documents.map((d, i) => (
                    <ListGroup.Item
                      key={i}
                      className="px-0 wrap d-flex justify-content-between align-items-start gap-2"
                    >
                      <div className="wrap">
                        {d?.url ? (
                          <a href={d.url} target="_blank" rel="noreferrer">
                            {d?.name || d.url}
                          </a>
                        ) : (
                          d?.name || "—"
                        )}
                      </div>
                    </ListGroup.Item>
                  ))}
                </ListGroup>
              ) : (
                <div className="text-muted">No documents.</div>
              )}
            </Card.Body>
          </Card>

          <Card className="mb-3">
            <Card.Header className="h6">
              Returning places <InfoTip className="ms-1" text={FIELD_HELP["returning.title"]} />
            </Card.Header>
            <Card.Body>
              <div className="mb-3">
                <ReturningPlacesMap places={summary?.returningPlaces ?? []} height={260} />
              </div>
              {(summary?.returningPlaces ?? []).length ? (
                <ListGroup variant="flush">
                  {(summary?.returningPlaces ?? []).map((p, i) => (
                    <ListGroup.Item
                      key={i}
                      className="px-0 wrap d-flex justify-content-between align-items-start gap-2"
                    >
                      <div className="wrap">
                        {p.name}{" "}
                        {p.latitude && p.longitude
                          ? `(${Number(p.latitude).toFixed(3)}, ${Number(p.longitude).toFixed(3)})`
                          : ""}
                        {p.gln ? ` • GLN ${p.gln}` : ""}
                      </div>
                    </ListGroup.Item>
                  ))}
                </ListGroup>
              ) : (
                <div className="text-muted">No returning places.</div>
              )}
            </Card.Body>
          </Card>

          <Card className="mb-5">
            <Card.Header className="h6">
              Backup <InfoTip className="ms-1" text={FIELD_HELP["backup.title"]} />
            </Card.Header>
            <Card.Body>
              {summary?.backupLink ? (
                <a className="wrap" href={summary.backupLink} target="_blank" rel="noreferrer">
                  {summary.backupLink}
                </a>
              ) : (
                <div className="text-muted">No backup link.</div>
              )}
            </Card.Body>
          </Card>
        </Col>

        {/* Linked DPPs for sub-parts */}
        <Card className="mb-3">
          <Card.Header className="h6 d-flex align-items-center justify-content-between">
            <span>Linked DPPs (sub-parts)</span>
            <InfoTip text={FIELD_HELP["dpplinks.header"]} placement="left" />
          </Card.Header>
          <Card.Body>
            {Array.isArray(summary?.linkedDpps) && summary.linkedDpps.length ? (
              <ListGroup variant="flush">
                {summary.linkedDpps.map((it) => (
                  <ListGroup.Item key={`${it.partId}-${it.dppId}`} className="px-0 wrap">
                    <Link to={`/dpp/${it.dppId}/overview`} className="wrap">
                      {it.partName || it.partId}
                    </Link>
                  </ListGroup.Item>
                ))}
              </ListGroup>
            ) : (
              <div className="text-muted">No linked DPPs found.</div>
            )}
          </Card.Body>
        </Card>
      </Row>
    </Container>
  );
}

/* ========= Helpers ========= */

function safeNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v : "—";
}

/**
 * Key/Value List item that pins the (i) tip to the FAR RIGHT.
 * Usage:
 * <KV label="Height" tipKey="specs.heightCM">45 cm</KV>
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
