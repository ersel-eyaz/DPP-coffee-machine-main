import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  ListGroup,
  Modal,
  Row,
  Spinner,
  Table,
} from "react-bootstrap";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import PartTree from "../components/PartTree";
import { FIELD_HELP } from "../content/fieldHelp";
import InfoTip from "../shared/InfoTip";
import PieChart from "../shared/PieChart";

export default function EolView() {
  const { instanceId } = useParams();
  const [data, setData] = useState(null);
  const [inst, setInst] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  const [showModal, setShowModal] = useState(false);
  const [places, setPlaces] = useState([]);
  const [placeId, setPlaceId] = useState("");
  const [beginDate, setBeginDate] = useState(() => new Date().toISOString().slice(0, 16));
  const [reason, setReason] = useState("End-of-life recycling");
  const [costEur, setCostEur] = useState("");
  const [diagnose, setDiagnose] = useState("");
  const [symptoms, setSymptoms] = useState("");
  const [posting, setPosting] = useState(false);
  const [postErr, setPostErr] = useState("");

  useEffect(() => {
    let on = true;
    setLoading(true);
    setErr(null);
    setData(null);
    setInst(null);

    (async () => {
      try {
        const [d, i] = await Promise.allSettled([api.getEolSummary(instanceId), api.getInstance(instanceId)]);
        if (!on) return;
        if (d.status === "fulfilled") setData(d.value);
        if (i.status === "fulfilled") setInst(i.value);
        if (d.status !== "fulfilled" && i.status !== "fulfilled") {
          throw new Error(i.reason?.message || d.reason?.message || "Load failed");
        }
      } catch (e) {
        if (!on) return;
        setErr(e?.message || String(e));
      } finally {
        if (on) setLoading(false);
      }
    })();

    return () => {
      on = false;
    };
  }, [instanceId]);

  useEffect(() => {
    let on = true;
    api
      .getPlaces?.()
      .then((json) => {
        if (!on) return;
        setPlaces(Array.isArray(json) ? json : (json?.items ?? []));
      })
      .catch(() => {});
    return () => {
      on = false;
    };
  }, []);

  const parsedSymptoms = useMemo(
    () =>
      String(symptoms || "")
        .split(/[;,]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    [symptoms],
  );

  const refetchAll = useCallback(async () => {
    const [d, i] = await Promise.allSettled([api.getEolSummary(instanceId), api.getInstance(instanceId)]);
    if (d.status === "fulfilled") setData(d.value);
    if (i.status === "fulfilled") setInst(i.value);
  }, [instanceId]);

  const onSubmitRecycle = useCallback(async () => {
    setPostErr("");
    if (!placeId) {
      setPostErr("Please select a Place.");
      return;
    }
    const beginISO = (() => {
      try {
        return new Date(beginDate).toISOString();
      } catch {
        return new Date().toISOString();
      }
    })();

    const payload = {
      type: "RecyclingStep",
      beginDate: beginISO,
      endDate: beginISO,
      processedAt: { id: placeId, collection: "place" },
      costEur: Number(costEur || 0),
      diagnose: String(diagnose || ""),
      observedSymptoms: parsedSymptoms,
      reason: String(reason || "Recycling"),
    };

    try {
      setPosting(true);
      await api.serviceRecycling(instanceId, payload);
      setShowModal(false);
      await refetchAll();
    } catch (e) {
      setPostErr(e?.message || String(e));
    } finally {
      setPosting(false);
    }
  }, [instanceId, placeId, beginDate, costEur, diagnose, parsedSymptoms, reason, refetchAll]);
  const linkedDppMap = useMemo(() => {
    const m = {};
    (data?.linkedDpps || []).forEach((it) => {
      if (it?.partId && it?.dppId) {
        m[it.partId] = { dppId: it.dppId, partName: it.partName, productName: it.productName };
      }
    });
    return m;
  }, [data]);

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
  if (!data && !inst) return <Container className="py-4">No data.</Container>;

  const title = data?.productName || inst?.dppStaticLink?.name || "Product";

  const matByName = data?.materials?.byName || [];
  const matByNameRecycled = data?.materials?.byNameRecycled || [];
  const overallRecycledPct = Number(data?.materials?.overallRecycledPercent || 0);
  const rareEarthPct = Number(data?.materials?.rareEarthPercent || 0);

  const rareNameSet = new Set((data?.rareEarthParts || []).map((x) => x.material));

  const topLevelPie = matByName.map((m) => ({
    label: m.name,
    value: Number(m.mass ?? 0) || Number(m.percent ?? 0),
  }));

  const topPart = inst?.partInstanceLink
    ? {
        id: inst.partInstanceLink.id,
        name:
          inst.partInstanceLink?.partStaticLink?.name ||
          inst.partInstanceLink?.partStaticLink?.document?.name ||
          inst.partInstanceLink?.name ||
          inst.partInstanceLink?.id,
        hasFailstate: !!inst.partInstanceLink?.hasFailstate,
        isModular: !!inst.partInstanceLink?.isModular,
      }
    : null;

  const firstLevelParts = topPart
    ? [topPart]
    : (Array.isArray(data?.parts?.firstLevel) && data.parts.firstLevel.length > 0
        ? data.parts.firstLevel
        : inst?.partInstanceLink?.compositeParts) || [];

  const counters = data?.counters || {
    cleaning: inst?.cleaningCount,
    chalk: inst?.chalkCount,
    brewing: inst?.brewingCount,
    grinding: inst?.coffeeGrindingCount,
    operatingHRS: inst?.operatingHRS,
  };

  const topFail = !!inst?.partInstanceLink?.hasFailstate;
  const levelFailCount = (data?.parts?.firstLevel || []).filter((p) => !!p.hasFailstate).length;
  const productHasFail = topFail || levelFailCount > 0;
  const productFailCount = (topFail ? 1 : 0) + levelFailCount;
  const totalPartsInTree = Number(data?.parts?.totalCount || 0);
  const healthyCount = Math.max(0, totalPartsInTree - productFailCount);

  const orgLine = (org) => {
    if (!org) return "—";
    const nameEl = org.url ? (
      <a href={org.url} target="_blank" rel="noreferrer">
        {org.name || org.id}
      </a>
    ) : (
      org.name || org.id
    );
    return <>{nameEl}</>;
  };

  const docLink = (d) =>
    !d || (!d.url && !d.name) ? (
      "—"
    ) : d.url ? (
      <a href={d.url} target="_blank" rel="noreferrer">
        {d.name || "Document"}
      </a>
    ) : (
      d.name || "—"
    );

  const toFixedMaybe = (n, d = 1) => {
    const v = Number(n);
    return Number.isFinite(v) ? v.toFixed(d) : "—";
  };

  const eur = (n) => {
    const v = Number(n);
    if (!Number.isFinite(v)) return "—";
    return v.toLocaleString(undefined, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
  };

  const mtbf = Number(data?.expectedMtbfHRS ?? NaN);
  const opHrs = Number(counters?.operatingHRS ?? NaN);
  const hasBoth = Number.isFinite(mtbf) && Number.isFinite(opHrs);
  const diffHrs = hasBoth ? Math.max(0, mtbf - opHrs) : null;
  const exceeded = hasBoth ? opHrs >= mtbf : false;

  const renderPath = (pathStr) => {
    const parts = String(pathStr || "")
      .split("→")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!parts.length) return null;
    return (
      <span className="path-breadcrumb">
        {parts.map((seg, idx) => (
          <span key={`${seg}-${idx}`} className="path-seg">
            {seg}
            {idx < parts.length - 1 && (
              <span className="path-arrow" aria-hidden>
                ›
              </span>
            )}
          </span>
        ))}
      </span>
    );
  };
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
  const asPercent = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return NaN;
    if (n >= 0 && n <= 1.5) return n * 100;
    return n;
  };
  const svcTotals = {
    costEUR: Number(data?.service?.totals?.costEUR ?? 0),
    Repair: Number(data?.service?.totals?.Repair ?? 0),
    Replace: Number(data?.service?.totals?.Replace ?? 0),
    Cleaning: Number(data?.service?.totals?.Cleaning ?? 0),
    Remanufacturing: Number(data?.service?.totals?.Remanufacturing ?? 0),
    Refurbishment: Number(data?.service?.totals?.Refurbishment ?? 0),
  };

  return (
    <Container className="py-3">
      {/* Header */}
      <Row className="align-items-center mb-2">
        <Col>
          <h2 className="mb-0">
            {title} — End-of-Life <InfoTip className="ms-1" placement="right" text={FIELD_HELP["eol.header"]} />
          </h2>
          <div className="text-muted">{data?.productClass || "—"}</div>
        </Col>
        <Col xs="auto" className="d-flex align-items-center gap-2">
          {inst?.discontinued ? (
            <Badge bg="secondary">Discontinued</Badge>
          ) : (
            <Button variant="danger" onClick={() => setShowModal(true)}>
              Mark as recycled / discontinue
            </Button>
          )}
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
              {productHasFail ? (
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

      <Row className="gy-3">
        {/* Left column */}
        <Col xs={12} lg={4}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>EoL & compliance</span>
              <InfoTip placement="left" text={FIELD_HELP["eol.compliance"]} />
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <KV label="Responsible operator" tipKey="org.responsible">
                  {orgLine(data?.responsibleOperator)}
                </KV>
                <KV label="WEEE number" tipKey="weee.number">
                  {data?.weeeRegistrationNumber ?? "—"}
                </KV>
                <KV label="Expected MTBF" tipKey="mtbf.expected">
                  {toFixedMaybe(mtbf, 0)} h
                </KV>
                <KV label="Operating hours" tipKey="counters.operatingHRS">
                  {toFixedMaybe(opHrs, 0)} h
                </KV>

                {hasBoth && (
                  <ListGroup.Item className="px-0">
                    {exceeded ? (
                      <Alert variant="danger" className="mb-1 py-1">
                        <strong>Warning:</strong> usage exceeds MTBF ({toFixedMaybe(opHrs - mtbf, 0)} h over). Fail
                        likely soon.
                      </Alert>
                    ) : (
                      <Alert variant="success" className="mb-1 py-1">
                        <strong>Status:</strong> {toFixedMaybe(diffHrs, 0)} h remaining until MTBF — within expected
                        range.
                      </Alert>
                    )}
                  </ListGroup.Item>
                )}
              </ListGroup>

              <div className="h6 mt-3 d-flex align-items-center justify-content-between">
                <span>Documents</span>
                <InfoTip placement="left" text={FIELD_HELP["documents.title"]} />
              </div>
              <ListGroup variant="flush">
                <ListGroup.Item className="px-0">
                  Disassembly:{" "}
                  <span className="ms-1">
                    {docLink(data?.documents?.disassembly)}{" "}
                    <InfoTip placement="right" text={FIELD_HELP["doc.disassembly"]} />
                  </span>
                </ListGroup.Item>
                <ListGroup.Item className="px-0">
                  Recycling/EoL:{" "}
                  <span className="ms-1">
                    {docLink(data?.documents?.recycling)}{" "}
                    <InfoTip placement="right" text={FIELD_HELP["doc.recycling"]} />
                  </span>
                </ListGroup.Item>
              </ListGroup>
            </Card.Body>
          </Card>

          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Usage counters</span>
              <InfoTip placement="left" text={FIELD_HELP["counters.title"]} />
            </Card.Header>
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

          {/* Lifetime service summary */}
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Service summary (device + subparts)</span>
              <InfoTip placement="left" text={FIELD_HELP["service.summary.subtree"]} />
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <KV label="Total cost" tipKey="service.cost.total">
                  <strong>{eur(svcTotals.costEUR)}</strong>
                </KV>
                <KV label="# Repair" tipKey="service.counts.repair">
                  {svcTotals.Repair}
                </KV>
                <KV label="# Replace" tipKey="service.counts.replace">
                  {svcTotals.Replace}
                </KV>
                <KV label="# Cleaning" tipKey="service.counts.cleaning">
                  {svcTotals.Cleaning}
                </KV>
                <KV label="# Remanufacturing" tipKey="service.counts.remanufacturing">
                  {svcTotals.Remanufacturing}
                </KV>
                <KV label="# Refurbishment" tipKey="service.counts.refurbishment">
                  {svcTotals.Refurbishment}
                </KV>
              </ListGroup>
            </Card.Body>
          </Card>
        </Col>

        {/* Right column */}
        <Col xs={12} lg={8}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Material composition</span>
              <InfoTip text={FIELD_HELP["materials.title"]} placement="left" />
            </Card.Header>
            <Card.Body>
              <Row className="gy-3">
                <Col xs={12} md="auto">
                  <div style={{ minWidth: 320 }}>
                    <div className="fw-semibold mb-2 d-flex align-items-center justify-content-between">
                      <span>Distribution by name</span>
                      <InfoTip text={FIELD_HELP["materials.distribution"]} placement="left" />
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
                  <div className="fw-semibold d-flex align-items-center justify-content-between">
                    <span>Summary</span>
                    <InfoTip text={FIELD_HELP["materials.title"]} placement="left" />
                  </div>
                  <div>
                    <b>Overall recycled</b> : {overallRecycledPct.toFixed(1)}%
                    <InfoTip className="ms-1" text={FIELD_HELP["materials.recycled"]} />
                  </div>
                  <div>
                    <b>Rare earth content</b> : {rareEarthPct.toFixed(2)}%
                    <InfoTip className="ms-1" text={FIELD_HELP["materials.rare"]} />
                  </div>

                  <div className="fw-semibold mt-3 mb-1 d-flex align-items-center justify-content-between">
                    <span>Per material</span>
                    <InfoTip text={FIELD_HELP["materials.perMaterial"]} placement="left" />
                  </div>
                  {matByNameRecycled.length ? (
                    <Table size="sm" bordered responsive>
                      <thead>
                        <tr>
                          <th>Material</th>
                          <th className="text-end">Mass (g)</th>
                          <th className="text-end">Share %</th>
                          <th className="text-end">
                            <div className="d-flex align-items-center justify-content-end gap-2">
                              <span>Recycled %</span>
                              <InfoTip text={FIELD_HELP["materials.recycled"]} placement="left" />
                            </div>
                          </th>
                          <th className="text-end">
                            <div className="d-flex align-items-center justify-content-end gap-2">
                              <span>Avg. Purity %</span>
                              <InfoTip text={FIELD_HELP["purity.avg"]} placement="left" />
                            </div>
                          </th>
                          <th className="text-end">
                            <div className="d-flex align_items-center justify-content-end gap-2">
                              <span>New material %</span>
                              <InfoTip placement="left" text={FIELD_HELP["materials.virgin"]} />
                            </div>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {matByNameRecycled.map((m) => {
                          const base = matByName.find((x) => x.name === m.name) || {};
                          const isRare = rareNameSet.has(m.name);

                          const purityPct = asPercent(m.purityPercent);
                          const recPct = asPercent(m.recycledPercent ?? 0);
                          const virginPct = Number.isFinite(Number(m.virginPercent))
                            ? asPercent(m.virginPercent)
                            : Math.max(0, 100 - recPct);
                          const purityBg = purityVariant(purityPct);
                          const recBg = recycledVariant(recPct);

                          return (
                            <tr key={m.name}>
                              <td className={`d-flex align-items-center gap-2 ${isRare ? "rare-cell" : ""}`}>
                                {isRare && (
                                  <Badge bg="warning" text="dark">
                                    rare-earth
                                  </Badge>
                                )}
                                <span style={{ fontWeight: isRare ? 600 : 400 }}>{m.name}</span>
                              </td>
                              <td className="text-end">{Number(base.mass ?? 0).toLocaleString()}</td>
                              <td className="text-end">{Number(base.percent ?? 0).toFixed(1)}</td>
                              <td className="text-end">
                                {Number.isFinite(recPct) ? <Badge bg={recBg}>{recPct.toFixed(1)}%</Badge> : "—"}
                              </td>
                              <td className="text-end">
                                {Number.isFinite(purityPct) ? (
                                  <Badge bg={purityBg}>{purityPct.toFixed(1)}%</Badge>
                                ) : (
                                  "—"
                                )}
                              </td>
                              <td className="text-end">
                                {Number.isFinite(virginPct) ? `${virginPct.toFixed(1)}%` : "—"}
                              </td>
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

          {/* Rare-earth & Hazardous listings */}
          <Row className="gy-3">
            <Col xs={12} md={6}>
              <Card className="mb-3">
                <Card.Header className="h6 d-flex align-items-center justify-content-between">
                  <span>Rare-earth materials in parts</span>
                  <InfoTip placement="left" text={FIELD_HELP["materials.rareParts"]} />
                </Card.Header>
                <Card.Body>
                  {Array.isArray(data?.rareEarthParts) && data.rareEarthParts.length ? (
                    <ListGroup variant="flush">
                      {data.rareEarthParts.map((g, i) => (
                        <ListGroup.Item key={`${g.material}-${i}`} className="px-0">
                          <div className="d-flex align-items-center gap-2">
                            <Badge bg="warning" text="dark">
                              rare-earth
                            </Badge>
                            <div className="fw-semibold">{g.material}</div>
                            {Number(g.gramsTotal) > 0 && (
                              <span className="ms-auto text-muted small">
                                {Number(g.gramsTotal).toLocaleString()} g
                              </span>
                            )}
                          </div>
                          <div className="mt-2 d-flex flex-column gap-2">
                            {(g.parts || []).map((p, j) => (
                              <div key={`${g.material}-${p.id || j}`} className="partline">
                                <div className="partline-name">
                                  <strong>{p.name}</strong>
                                  {Number(p.grams) > 0 && (
                                    <span className="badge bg-light text-dark ms-2">
                                      {Number(p.grams).toLocaleString()} g
                                    </span>
                                  )}
                                </div>
                                <div className="partline-path">{renderPath(p.path)}</div>
                              </div>
                            ))}
                            {(!g.parts || g.parts.length === 0) && <div className="text-muted small">—</div>}
                          </div>
                        </ListGroup.Item>
                      ))}
                    </ListGroup>
                  ) : (
                    <div className="text-muted">No rare-earth detected.</div>
                  )}
                </Card.Body>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card className="mb-3">
                <Card.Header className="h6 d-flex align-items-center justify-content-between">
                  <span>Hazardous materials & warnings</span>
                  <InfoTip placement="left" text={FIELD_HELP["materials.hazardous"]} />
                </Card.Header>
                <Card.Body>
                  {Array.isArray(data?.hazardous) && data.hazardous.length ? (
                    <ListGroup variant="flush">
                      {data.hazardous.map((h, i) => (
                        <ListGroup.Item key={`${h.material}-${i}`} className="px-0">
                          <div className="fw-semibold">{h.material}</div>

                          {(h.parts || []).length > 0 && (
                            <div className="mt-2 d-flex flex-column gap-2">
                              {h.parts.map((p, j) => (
                                <div key={`${h.material}-${p.id || j}`} className="partline">
                                  <div className="partline-name">
                                    <strong>{p.name}</strong>
                                    {Number(p.grams) > 0 && (
                                      <span className="badge bg-light text-dark ms-2">
                                        {Number(p.grams).toLocaleString()} g
                                      </span>
                                    )}
                                  </div>
                                  <div className="partline-path">{renderPath(p.path)}</div>
                                </div>
                              ))}
                            </div>
                          )}

                          {h.warnings?.length ? (
                            <ul className="mb-0 mt-2">
                              {h.warnings.map((w, j) => (
                                <li key={`${h.material}-warn-${j}`} className="small text-danger">
                                  {w}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <div className="text-muted small mt-2">No warnings provided.</div>
                          )}
                        </ListGroup.Item>
                      ))}
                    </ListGroup>
                  ) : (
                    <div className="text-muted">No hazardous materials flagged.</div>
                  )}
                </Card.Body>
              </Card>
            </Col>
          </Row>

          {/* Part tree */}
          <Card className="mb-4">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Parts</span>
              <InfoTip text={FIELD_HELP["parts.title"]} placement="left" />
            </Card.Header>
            <Card.Body>
              <div className="mb-2 d-flex align-items-center gap-3 flex-wrap">
                <div className="d-flex align-items-center">
                  <strong>Total parts in device</strong>{" "}
                  <InfoTip className="ms-1" text={FIELD_HELP["parts.totalInTree"]} />: {data?.parts?.totalCount ?? "—"}
                </div>
                <div className="d-flex align-items-center">
                  <span className={`me-2 ${productHasFail ? "text-danger" : "text-success"}`} style={{ fontSize: 16 }}>
                    {productHasFail ? "⚠️" : "✅"}
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
              <PartTree
                rootParts={firstLevelParts}
                showModular={true}
                showAvvDispose={true}
                showPurity={true}
                linkedDppMap={linkedDppMap}
                hideDppBadgeForId={topPart?.id}
              />
            </Card.Body>
          </Card>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Linked DPPs (sub-parts)</span>
              <InfoTip text={FIELD_HELP["dpplinks.header"]} placement="left" />
            </Card.Header>
            <Card.Body>
              {Array.isArray(data?.linkedDpps) && data.linkedDpps.length ? (
                <ListGroup variant="flush">
                  {data.linkedDpps.map((it) => (
                    <ListGroup.Item key={`${it.partId}-${it.dppId}`} className="px-0 wrap">
                      <Link to={`/dpp/${it.dppId}/user`} className="wrap">
                        {it.partName || it.partId}
                        {it.productName ? ` — ${it.productName}` : ""}
                      </Link>
                    </ListGroup.Item>
                  ))}
                </ListGroup>
              ) : (
                <div className="text-muted">No linked DPPs found.</div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Modal show={showModal} onHide={() => setShowModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Register recycling / discontinue</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {postErr && (
            <Alert variant="danger" className="mb-3">
              {postErr}
            </Alert>
          )}
          <Form>
            <Row className="g-3">
              <Col md={6}>
                <Form.Group>
                  <Form.Label className="d-flex align-items-center gap-2">
                    <span>Begin date/time</span>
                    <InfoTip placement="right" text={FIELD_HELP["recycling.beginDate"]} />
                  </Form.Label>
                  <Form.Control
                    type="datetime-local"
                    value={beginDate}
                    onChange={(e) => setBeginDate(e.target.value)}
                  />
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group>
                  <Form.Label className="d-flex align-items-center gap-2">
                    <span>Place</span>
                    <InfoTip placement="right" text={FIELD_HELP["modal.processedAt"]} />
                  </Form.Label>
                  <Form.Select value={placeId} onChange={(e) => setPlaceId(e.target.value)}>
                    <option value="">— choose place —</option>
                    {places.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} {p.city ? `(${p.city}, ${p.country})` : ""}
                      </option>
                    ))}
                  </Form.Select>
                </Form.Group>
              </Col>

              <Col md={12}>
                <Form.Group>
                  <Form.Label className="d-flex align-items-center gap-2">
                    <span>Reason</span>
                    <InfoTip placement="right" text={FIELD_HELP["recycling.reason"]} />
                  </Form.Label>
                  <Form.Control
                    placeholder="e.g., Device reached end-of-life and is recycled"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </Form.Group>
              </Col>

              <Col md={4}>
                <Form.Group>
                  <Form.Label className="d-flex align-items-center gap-2">
                    <span>Cost (EUR)</span>
                    <InfoTip placement="right" text={FIELD_HELP["modal.cost"]} />
                  </Form.Label>
                  <Form.Control
                    type="number"
                    step="0.01"
                    min="0"
                    value={costEur}
                    onChange={(e) => setCostEur(e.target.value)}
                  />
                </Form.Group>
              </Col>

              <Col md={8}>
                <Form.Group>
                  <Form.Label className="d-flex align-items-center gap-2">
                    <span>Diagnose (optional)</span>
                    <InfoTip placement="right" text={FIELD_HELP["recycling.diagnose"]} />
                  </Form.Label>
                  <Form.Control
                    placeholder="optional note"
                    value={diagnose}
                    onChange={(e) => setDiagnose(e.target.value)}
                  />
                </Form.Group>
              </Col>

              <Col md={12}>
                <Form.Group>
                  <Form.Label className="d-flex align-items-center gap-2">
                    <span>Observed symptoms (comma/semicolon separated, optional)</span>
                    <InfoTip placement="right" text={FIELD_HELP["modal.symptoms"]} />
                  </Form.Label>
                  <Form.Control
                    placeholder="e.g., no power; damaged housing"
                    value={symptoms}
                    onChange={(e) => setSymptoms(e.target.value)}
                  />
                </Form.Group>
              </Col>
            </Row>
          </Form>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowModal(false)}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onSubmitRecycle} disabled={posting}>
            {posting ? "Saving…" : "Mark as recycled"}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

function safeNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v : "—";
}

/**
 * Key/Value List item.
 */
function KV({ label, tipKey, tipText, children, tipPlacement = "left" }) {
  const text = tipText ?? FIELD_HELP[tipKey];
  return (
    <ListGroup.Item className="px-0 d-flex justify-content-between align-items-start gap-2">
      <div className="wrap">
        <span className="text-muted">{label}</span>: <span className="ms-1">{children ?? "—"}</span>
      </div>
      {text ? <InfoTip text={text} placement={tipPlacement} className="ms-2 text-muted flex-shrink-0" /> : null}
    </ListGroup.Item>
  );
}
