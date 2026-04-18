// src/pages/UtilityView.jsx
import React, { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Col, Container, ListGroup, ProgressBar, Row, Spinner } from "react-bootstrap";
import { useParams } from "react-router-dom";

import { api } from "../api";
import { toApiURL } from "../shared/toApiURL";
import InfoTip from "../shared/InfoTip";

export default function UtilityView() {
  const { instanceId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [downA, setDownA] = useState(false);
  const [downB, setDownB] = useState(false);

  useEffect(() => {
    let on = true;
    setLoading(true);
    setErr(null);
    setData(null);
    (async () => {
      try {
        const json = await api.getUtilitySummary(instanceId);
        if (!on) return;
        setData(json);
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

  const title = data?.productName || "Product";

  async function triggerDownload(getBlobFn, filename) {
    const blob = await getBlobFn();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const onDownloadInstance = async () => {
    try {
      setDownA(true);
      const fname = `dpp-instance-${instanceId}.jsonld`;
      await triggerDownload(() => api.downloadJsonLdInstance(instanceId), fname);
    } catch (e) {
      alert(e?.message || String(e));
    } finally {
      setDownA(false);
    }
  };

  const onDownloadBundle = async () => {
    if (!data?.staticId) return;
    try {
      setDownB(true);
      const fname = `dpp-bundle-${data.staticId}.jsonld`;
      await triggerDownload(() => api.downloadJsonLdBundle(data.staticId), fname);
    } catch (e) {
      alert(e?.message || String(e));
    } finally {
      setDownB(false);
    }
  };
  const fmtNum = (n, d = 2) => {
    const v = Number(n);
    return Number.isFinite(v) ? v.toFixed(d) : "—";
  };
  const eur = (n) => {
    const v = Number(n);
    return Number.isFinite(v)
      ? v.toLocaleString(undefined, { style: "currency", currency: "EUR", maximumFractionDigits: 0 })
      : "—";
  };
  const humanizeAvgDays = (d) => {
    const val = Number(d);
    if (!Number.isFinite(val)) return "—";
    if (val < 60) return `${Math.round(val)} day${Math.round(val) === 1 ? "" : "s"}`;
    if (val < 365) return `${Math.round(val / 30)} month${Math.round(val / 30) === 1 ? "" : "s"}`;
    return `${Math.round(val / 365)} year${Math.round(val / 365) === 1 ? "" : "s"}`;
  };
  const STEP_LABEL = {
    SecondaryValueStep: "All secondary ops",
    RepairServiceStep: "Repair",
    ReplaceServiceStep: "Replace",
    CleaningServiceStep: "Cleaning",
    RemanufacturingServiceStep: "Remanufacturing",
    RefurbishmentServiceStep: "Refurbishment",
    RecyclingStep: "Recycling",
  };

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

  return (
    <Container className="py-3">
      <style>{`
        .wrap { white-space: normal !important; word-break: break-word !important; overflow-wrap: anywhere !important; }
      `}</style>

      <Row className="align-items-center mb-2">
        <Col>
          <h2 className="mb-0">
            {title} — Utility{" "}
            <InfoTip className="ms-1" placement="right" text="Backup links and JSON-LD export tools" />
          </h2>
          <div className="text-muted">Instance: {instanceId}</div>
        </Col>
        <Col xs="auto" className="d-flex align-items-center gap-2">
          <Badge bg="secondary">Static: {data?.staticId || "—"}</Badge>
          {Number.isFinite(Number(data?.instancesCount)) && (
            <Badge bg="info" text="dark" title="Number of instances in this product family">
              Instances: {data.instancesCount}
            </Badge>
          )}
        </Col>
      </Row>

      {/* Backup + JSON-LD */}
      <Row className="gy-3">
        <Col xs={12} lg={6}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Backup links</span>
              <InfoTip placement="left" text="Links to external backups (instance vs. product static)" />
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <ListGroup.Item className="px-0 d-flex justify-content-between align-items-start gap-2">
                  <div className="wrap">
                    <span className="text-muted">Instance backup (this unit)</span>:{" "}
                    {data?.backup?.instance ? (
                      <a href={toApiURL(data.backup.instance)} target="_blank" rel="noreferrer" className="ms-1">
                        {data.backup.instance}
                      </a>
                    ) : (
                      <span className="ms-1">—</span>
                    )}
                  </div>
                </ListGroup.Item>
                <ListGroup.Item className="px-0 d-flex justify-content-between align-items-start gap-2">
                  <div className="wrap">
                    <span className="text-muted">Static backup (product)</span>:{" "}
                    {data?.backup?.static ? (
                      <a href={toApiURL(data.backup.static)} target="_blank" rel="noreferrer" className="ms-1">
                        {data.backup.static}
                      </a>
                    ) : (
                      <span className="ms-1">—</span>
                    )}
                  </div>
                </ListGroup.Item>
              </ListGroup>
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={6}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>JSON-LD export</span>
              <InfoTip placement="left" text="Download JSON-LD for the instance or for the whole product family." />
            </Card.Header>
            <Card.Body className="d-flex flex-column gap-2">
              <Button variant="primary" onClick={onDownloadInstance} disabled={downA}>
                {downA ? (
                  <>
                    <Spinner animation="border" size="sm" className="me-2" /> Preparing…
                  </>
                ) : (
                  "Download instance (JSON-LD)"
                )}
              </Button>

              <Button
                variant="secondary"
                onClick={onDownloadBundle}
                disabled={downB || !data?.staticId}
                title={data?.staticId ? "" : "Static ID missing"}
              >
                {downB ? (
                  <>
                    <Spinner animation="border" size="sm" className="me-2" /> Preparing…
                  </>
                ) : (
                  "Download bundle: static + all instances (JSON-LD)"
                )}
              </Button>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="gy-3">
        <Col xs={12} lg={6}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Symptoms → likely diagnoses (family)</span>
              <InfoTip placement="left" text="Aggregated across all instances of this product." />
            </Card.Header>
            <Card.Body className="pt-3">
              {Array.isArray(data?.symptomDiagnosisSummary) && data.symptomDiagnosisSummary.length ? (
                <ListGroup variant="flush">
                  {data.symptomDiagnosisSummary.map((entry, idx) => (
                    <ListGroup.Item key={idx} className="px-0">
                      <div className="d-flex flex-wrap align-items-center justify-content-between mb-1">
                        <div className="mb-1">
                          <strong className="me-2">{entry.symptom}</strong>
                          <Badge bg="light" text="dark">
                            instances: {entry.instanceCount ?? 0}
                          </Badge>
                        </div>
                      </div>
                      {(entry.diagnoses || []).map((d, j) => {
                        const probPct = Math.max(0, Math.min(100, Math.round((Number(d.probability) || 0) * 100)));
                        return (
                          <div key={j} className="d-flex align-items-center flex-wrap gap-2 mb-2">
                            <span
                              className="d-inline-flex align-items-center gap-2 px-2 py-1 rounded wrap"
                              style={{ background: "#f8f9fa" }}
                            >
                              <span className="fw-semibold">{d.diagnosis || "—"}</span>
                              <span>({probPct}%)</span>
                            </span>
                            <div style={{ minWidth: 160, maxWidth: 200, flex: "0 0 160px" }}>
                              <ProgressBar now={probPct} />
                            </div>
                            <span className="text-muted small">
                              avg cost: <strong>{eur(d.avgCostEUR)}</strong>
                            </span>
                            <span className="text-muted small ms-2">
                              avg occur: <strong>{humanizeAvgDays(d.avgDaysSinceDeclaration)}</strong>
                            </span>
                          </div>
                        );
                      })}
                    </ListGroup.Item>
                  ))}
                </ListGroup>
              ) : (
                <div className="text-muted">No symptom/diagnosis data yet.</div>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={6}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Service operations across product family</span>
              <InfoTip placement="left" text="Totals, averages, and most-affected parts across all instances." />
            </Card.Header>
            <Card.Body>
              <div className="mb-3">
                <div className="fw-semibold mb-1">Totals (all instances)</div>
                {data?.operations?.totals ? (
                  <ul className="mb-2">
                    {Object.entries(data.operations.totals)
                      .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
                      .map(([k, v]) => (
                        <li key={k} className="wrap">
                          {STEP_LABEL[k] || k}: <strong>{v}</strong>
                        </li>
                      ))}
                  </ul>
                ) : (
                  <div className="text-muted">—</div>
                )}

                <div className="fw-semibold mb-1">
                  Average per instance <span className="text-muted">(n={data?.instancesCount ?? "—"})</span>
                </div>
                {data?.operations?.averagePerInstance ? (
                  <ul className="mb-0">
                    {Object.entries(data.operations.averagePerInstance)
                      .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
                      .map(([k, v]) => (
                        <li key={k} className="wrap">
                          {STEP_LABEL[k] || k}: <strong>{fmtNum(v, 2)}</strong>
                        </li>
                      ))}
                  </ul>
                ) : (
                  <div className="text-muted">—</div>
                )}
              </div>

              <div className="mb-3">
                <div className="fw-semibold">Most affected parts (overall)</div>
                {Array.isArray(data?.operations?.topPartsOverall) && data.operations.topPartsOverall.length ? (
                  <ol className="mb-0">
                    {data.operations.topPartsOverall.slice(0, 5).map((p, i) => (
                      <li key={i} className="wrap">
                        {p.name} — <strong>{p.count}</strong>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <div className="text-muted">—</div>
                )}
              </div>

              <div>
                <div className="fw-semibold">Top parts by operation</div>
                {data?.operations?.topPartsByOperation ? (
                  Object.entries(data.operations.topPartsByOperation)
                    .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
                    .map(([k, arr]) => (
                      <div key={k} className="mb-2">
                        <div className="text-muted">{STEP_LABEL[k] || k}</div>
                        {Array.isArray(arr) && arr.length ? (
                          <ol className="mb-0">
                            {arr.slice(0, 5).map((p, i) => (
                              <li key={i} className="wrap">
                                {p.name} — <strong>{p.count}</strong>
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <div className="text-muted">—</div>
                        )}
                      </div>
                    ))
                ) : (
                  <div className="text-muted">—</div>
                )}
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}
