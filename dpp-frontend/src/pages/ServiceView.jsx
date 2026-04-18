import React, { useEffect, useState } from "react";
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
  ProgressBar,
  Row,
  Spinner,
  Table,
  Toast,
  ToastContainer,
} from "react-bootstrap";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import PartTreeService from "../components/PartTreeService";
import { FIELD_HELP } from "../content/fieldHelp";
import InfoTip from "../shared/InfoTip";

export default function ServiceView() {
  const { instanceId } = useParams();
  const [data, setData] = useState(null);
  const [inst, setInst] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [showReg, setShowReg] = useState(false);
  const [posting, setPosting] = useState(false);
  const [toast, setToast] = useState({ show: false, msg: "", variant: "success" });
  const [partOptions, setPartOptions] = useState([]);
  const [staticOptions, setStaticOptions] = useState([]);
  const [placeOptions, setPlaceOptions] = useState([]);
  const [stepType, setStepType] = useState("RepairServiceStep");
  const [selPartId, setSelPartId] = useState("");
  const [costEur, setCostEur] = useState("");
  const [diagnose, setDiagnose] = useState("");
  const [symptomsStr, setSymptomsStr] = useState("");
  const [beginDateISO, setBeginDateISO] = useState(() => new Date().toISOString().slice(0, 16));
  const [placeId, setPlaceId] = useState("");
  const [newStaticId, setNewStaticId] = useState("");
  const [newSerial, setNewSerial] = useState("");
  const [newBatch, setNewBatch] = useState("");
  const [treeRefreshSeq, setTreeRefreshSeq] = useState(0);

  useEffect(() => {
    let on = true;
    setLoading(true);
    setErr(null);
    setData(null);
    setInst(null);

    (async () => {
      try {
        const [s, i] = await Promise.allSettled([api.getServiceSummary(instanceId), api.getInstance(instanceId)]);
        if (!on) return;
        if (s.status === "fulfilled") setData(s.value);
        if (i.status === "fulfilled") setInst(i.value);
        if (s.status !== "fulfilled" && i.status !== "fulfilled") {
          throw new Error(i.reason?.message || s.reason?.message || "Load failed");
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

  const refreshAll = async () => {
    const [s, i] = await Promise.all([api.getServiceSummary(instanceId), api.getInstance(instanceId)]);
    setData(s);
    setInst(i);
    setTreeRefreshSeq((n) => n + 1);
  };
  useEffect(() => {
    let on = true;
    (async () => {
      try {
        const json = await api.getPlaces?.();
        if (!on || !json) return;
        const arr = Array.isArray(json) ? json : (json?.items ?? []);
        const opts = arr.map((p) => ({
          id: p?.id || p?._id || "",
          label: p?.name ? `${p.name} (${p.id})` : p?.id || "place",
        }));
        setPlaceOptions(opts);
        if (!placeId && opts.length) setPlaceId(opts[0].id);
      } catch {
        // ignore
      }
    })();
    return () => {
      on = false;
    };
  }, []); // run once

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

  const dateDecl = data?.dateOfDeclaration;
  const endG = data?.endOfGuarantee;
  const guaranteeDesc = data?.guaranteeDescription;

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
  const toFixedMaybe = (n, d = 1) => {
    const v = Number(n);
    return Number.isFinite(v) ? v.toFixed(d) : "—";
  };
  const eur = (n) => {
    const v = Number(n);
    if (!Number.isFinite(v)) return "—";
    return v.toLocaleString(undefined, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
  };
  const renderSymptoms = (sym) => {
    const arr = Array.isArray(sym) ? sym : typeof sym === "string" ? sym.split(/[;,]+/) : [];
    const clean = arr.map((s) => String(s).trim()).filter(Boolean);
    if (!clean.length) return "—";
    return (
      <ol className="mb-0 ps-3 sym-list">
        {clean.map((s, i) => (
          <li key={i} className="sym-item">
            {s}
          </li>
        ))}
      </ol>
    );
  };

  const humanizeAvgDays = (d) => {
    const val = Number(d);
    if (!Number.isFinite(val)) return "—";
    if (val < 60) {
      const days = Math.round(val);
      return `${days} day${days === 1 ? "" : "s"}`;
    }
    if (val < 365) {
      const months = Math.round(val / 30);
      return `${months} month${months === 1 ? "" : "s"}`;
    }
    const years = Math.round(val / 365);
    return `${years} year${years === 1 ? "" : "s"}`;
  };
  const failCount = Number(data?.failState?.count || 0);
  const totalPartsInTree = Number(data?.failState?.totalPartsInTree || data?.parts?.totalCount || 0);
  const hasFails = !!data?.failState?.hasAny;
  const healthyCount = Math.max(0, totalPartsInTree - failCount);

  const remainingHrs = data?.mtbf?.remainingHRS;
  const mtbfExceeded = !!data?.mtbf?.exceeded;
  const expectedMtbf = Number(data?.expectedMtbfHRS ?? NaN);
  const operatingHRS = Number(data?.counters?.operatingHRS ?? NaN);
  const hasBoth = Number.isFinite(expectedMtbf) && Number.isFinite(operatingHRS);
  const counters = data?.counters || {
    operatingHRS: inst?.operatingHRS,
    cleaning: inst?.cleaningCount,
    chalk: inst?.chalkCount,
    brewing: inst?.brewingCount,
    grinding: inst?.coffeeGrindingCount,
  };
  const firstLevelParts = data?.parts?.firstLevel || [];
  const topHasFail = !!data?.parts?.topHasFailstate;
  const topPartId = inst?.partInstanceLink?.id || data?.parts?.topPartId || undefined;
  const perPartStats = data?.service?.perPart || data?.perPartStats || {};
  const perPartMtbf = data?.service?.perPartMtbf || {};
  const secSteps = Array.isArray(data?.secondaryValueSteps) ? data.secondaryValueSteps : [];
  const totalHistoryCost = secSteps.reduce((acc, s) => acc + (Number(s?.costEUR ?? s?.cost) || 0), 0);
  const diagSummary = Array.isArray(data?.symptomDiagnosisSummary) ? data.symptomDiagnosisSummary : [];
  const failingParts = Array.isArray(data?.failingParts) ? data.failingParts : [];
  const detachedParts = Array.isArray(data?.detachedParts) ? data.detachedParts : [];
  async function buildPartOptionsBFS(rootId) {
    const seen = new Set([rootId]);
    const queue = [rootId];
    const items = [];
    const staticIdx = new Map();

    while (queue.length) {
      const batch = queue.splice(0, queue.length);
      const [pis, kidsLists] = await Promise.all([
        Promise.all(batch.map((id) => api.getPartInstance(id))),
        Promise.all(batch.map((id) => api.getPartChildren(id).catch(() => []))),
      ]);

      pis.forEach((pi, i) => {
        const id = batch[i];
        const nm = pi?.partStaticLink?.name || pi?.partStaticLink?.document?.name || pi?.name || id;
        items.push({ id, label: nm });
        const ps = pi?.partStaticLink || pi?.partStaticLink?.document;
        const staticId = ps?.id || ps?._id || (typeof ps === "string" ? ps : null);
        if (staticId && !staticIdx.has(staticId)) {
          staticIdx.set(staticId, { id: staticId, label: ps?.name || nm || staticId });
        }
      });

      kidsLists.flat().forEach((k) => {
        const kidId = k?.id || k?._id || k;
        if (kidId && !seen.has(kidId)) {
          seen.add(kidId);
          queue.push(kidId);
        }
      });
    }

    setPartOptions(items.sort((a, b) => String(a.label || "").localeCompare(String(b.label || ""))));
    setStaticOptions(
      [...staticIdx.values()].sort((a, b) => String(a.label || "").localeCompare(String(b.label || ""))),
    );
    if (!selPartId && items.length) setSelPartId(items[0].id);
    if (!newStaticId && staticIdx.size) setNewStaticId([...staticIdx.values()][0].id);
  }

  const prepareRegisterModal = async () => {
    try {
      if (!topPartId) throw new Error("Top part not found");
      await buildPartOptionsBFS(topPartId);
      const rnd = Math.random().toString(36).slice(2, 8).toUpperCase();
      setNewSerial(`SN-REPLACE-${rnd}`);
      setNewBatch(`BATCH-REPLACE-001`);
      setShowReg(true);
    } catch (e) {
      setToast({ show: true, msg: `Failed to prepare service modal: ${e?.message || e}`, variant: "danger" });
    }
  };

  const postStep = async () => {
    try {
      setPosting(true);
      const baseDates = (() => {
        try {
          const d = new Date(beginDateISO);
          const iso = d.toISOString();
          return { beginDate: iso, endDate: iso };
        } catch {
          const iso = new Date().toISOString();
          return { beginDate: iso, endDate: iso };
        }
      })();
      const processedAt = placeId ? { id: String(placeId), collection: "place" } : undefined;
      const payloadCommon = {
        type: stepType,
        ...baseDates,
        ...(processedAt ? { processedAt } : {}),
        ghgEmissionRecords: [],
        costEur: Number(costEur) || 0,
        diagnose: diagnose || "",
        observedSymptoms: symptomsStr
          .split(/[;,]+/)
          .map((s) => s.trim())
          .filter(Boolean),
      };

      let payload = payloadCommon;
      if (stepType === "RepairServiceStep") {
        payload = { ...payloadCommon, repairedPartId: selPartId };
        await api.serviceRepair(instanceId, payload);
      } else if (stepType === "CleaningServiceStep") {
        payload = { ...payloadCommon, cleanedPartId: selPartId, cleaningMethod: "manual" };
        await api.serviceCleaning(instanceId, payload);
      } else if (stepType === "ReplaceServiceStep") {
        payload = {
          ...payloadCommon,
          replacedPartId: selPartId,
          newPart: {
            id: `urn:uuid:${crypto.randomUUID?.() || Math.random().toString(36).slice(2)}`,
            type: "PartInstance",
            partStaticLink: { id: newStaticId, collection: "part_static" },
            serialNumber: newSerial || undefined,
            batchNumber: newBatch || "BATCH-REPLACE-001",
            isModular: false,
            hasFailstate: false,
            compositeParts: [],
            historyOfDetachedParts: [],
            compositeMaterials: [],
            partProcessTracking: [
              {
                type: "ProductionStep",
                ...baseDates,
                processedAt: processedAt || { id: placeOptions[0]?.id, collection: "place" },
                ghgEmissionRecords: [
                  {
                    scope: "Scope 2",
                    activity: { activity_type: "electricity_consumption", quantity: 10.0, unit: "kWh" },
                    emission_factor: {
                      description: "Average grid electricity for production",
                      value: 0.4,
                      unit: "kgCO2e/kWh",
                      technology: "electricity grid",
                    },
                    emissions_kg_co2e: 4.0,
                    calculation_method: "activity.quantity * factor.value",
                    provenance: "production",
                    excluded_from_aggregation: false,
                  },
                ],
                description: "Manufacture replacement part",
              },
            ],
          },
        };
        await api.serviceReplace(instanceId, payload);
      } else if (stepType === "RemanufacturingServiceStep" || stepType === "RefurbishmentServiceStep") {
        payload = {
          ...payloadCommon,
          repairedPartIds: [],
          cleanedPartIds: [],
          replacedAndNewParts: [
            [
              selPartId,
              {
                id: `urn:uuid:${crypto.randomUUID?.() || Math.random().toString(36).slice(2)}`,
                type: "PartInstance",
                partStaticLink: { id: newStaticId, collection: "part_static" },
                serialNumber: newSerial || undefined,
                batchNumber: newBatch || "BATCH-REPLACE-001",
                isModular: false,
                hasFailstate: false,
                compositeParts: [],
                historyOfDetachedParts: [],
                compositeMaterials: [],
                partProcessTracking: [
                  {
                    type: "ProductionStep",
                    ...baseDates,
                    processedAt: processedAt || { id: placeOptions[0]?.id, collection: "place" },
                    ghgEmissionRecords: [],
                    description: "Manufacture replacement part",
                  },
                ],
              },
            ],
          ],
        };
        if (stepType === "RemanufacturingServiceStep") {
          await api.serviceRemanufacturing(instanceId, payload);
        } else {
          await api.serviceRefurbishment(instanceId, payload);
        }
      } else {
        throw new Error("Unsupported step type");
      }
      await refreshAll();
      setShowReg(false);
      setToast({ show: true, msg: "Service step registered.", variant: "success" });
    } catch (e) {
      setToast({ show: true, msg: `Failed to register step: ${e?.message || e}`, variant: "danger" });
    } finally {
      setPosting(false);
    }
  };
  const discontinued = !!inst?.discontinued;

  return (
    <Container className="py-3">
      <style>{`
        .wrap { white-space: normal !important; word-break: break-word !important; overflow-wrap: anywhere !important; }
        .history-table { table-layout: fixed; }
        .history-table th, .history-table td { vertical-align: top; }
        @media (max-width: 576px) { .col-diagnose, .col-symptoms { width: 100%; } }
        .sym-list .sym-item { margin-bottom: 0; }
        .diag-chip { display:inline-flex; align-items:center; gap:.5rem; padding:.25rem .5rem; border-radius:.5rem; background:#f8f9fa; }
        .diag-row { gap:.75rem; }
        .diag-sep { width: 1px; height: 18px; background: #e0e0e0; display:inline-block; }
        .diag-meta { display:inline-flex; align-items:center; gap:.5rem; flex-wrap: wrap; }
        .diag-prog { min-width: 120px; }
      `}</style>
      <Row className="align-items-center mb-2">
        <Col>
          <h2 className="mb-0">
            {title} — Service <InfoTip className="ms-1" placement="right" text={FIELD_HELP["service.header"]} />
            {discontinued && (
              <Badge bg="secondary" className="ms-2">
                Discontinued
              </Badge>
            )}
          </h2>
          <div className="text-muted">{data?.productClass || "—"}</div>
        </Col>
        <Col xs="auto" className="d-flex align-items-center gap-2">
          <Button variant="primary" onClick={prepareRegisterModal} disabled={discontinued}>
            Register service
          </Button>
          <Button as={Link} to="/" variant="link">
            ← Back to selection
          </Button>
        </Col>
      </Row>
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
      <Row className="gy-3">
        <Col xs={12} lg={4}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Dates & guarantee</span>
              <InfoTip placement="left" text={FIELD_HELP["service.dates"]} />
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <KV label="Declaration date" tipKey="dates.declaration">
                  <span className="wrap">{fmtDate(dateDecl)}</span>
                </KV>
                <KV label="End of guarantee" tipKey="guarantee.validUntil">
                  <span className="wrap">{fmtDate(endG)}</span>
                </KV>
                <KV label="Product age" tipKey="dates.productAge">
                  <span className="wrap">
                    {Number.isFinite(Number(data?.productAgeDays)) ? `${data.productAgeDays} days` : "—"}
                  </span>
                </KV>
                <KV label="Qualification required" tipKey="qualification.required">
                  <Badge bg="secondary">{data?.qualificationForRepair || "—"}</Badge>
                </KV>
              </ListGroup>

              {guaranteeDesc ? (
                <>
                  <div className="h6 mt-3 d-flex align-items-center justify-content-between">
                    <span>Guarantee details</span>
                    <InfoTip placement="left" text={FIELD_HELP["guarantee.description"]} />
                  </div>
                  <div className="text-muted wrap">{guaranteeDesc}</div>
                </>
              ) : null}
            </Card.Body>
          </Card>

          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>MTBF status</span>
              <InfoTip placement="left" text={FIELD_HELP["mtbf.title"]} />
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <KV label="Expected MTBF" tipKey="mtbf.expected">
                  <span className="fw-semibold">{toFixedMaybe(expectedMtbf, 0)} h</span>
                </KV>
                <KV label="Operating hours" tipKey="counters.operatingHRS">
                  {toFixedMaybe(operatingHRS, 0)} h
                </KV>
              </ListGroup>

              {hasBoth && (
                <div className="mt-2">
                  {mtbfExceeded ? (
                    <Alert variant="danger" className="mb-1 py-1 wrap">
                      <strong>Warning:</strong> usage exceeds MTBF ({toFixedMaybe(operatingHRS - expectedMtbf, 0)} h
                      over). Fail likely soon.
                    </Alert>
                  ) : (
                    <Alert variant="success" className="mb-1 py-1 wrap">
                      <strong>Status:</strong> {toFixedMaybe(remainingHrs, 0)} h remaining until MTBF — within expected
                      range.
                    </Alert>
                  )}
                </div>
              )}
            </Card.Body>
          </Card>

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

        <Col xs={12} lg={8}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Service documentation</span>
              <InfoTip placement="left" text={FIELD_HELP["documents.title"]} />
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <KV label="Repair & Service Manual" tipKey="doc.repair">
                  {data?.documents?.repairManual?.url ? (
                    <a href={data.documents.repairManual.url} target="_blank" rel="noreferrer" className="wrap">
                      {data.documents.repairManual.name || "Document"}
                    </a>
                  ) : (
                    <span className="wrap">{data?.documents?.repairManual?.name || "—"}</span>
                  )}
                </KV>
                <KV label="Disassembly Instructions" tipKey="doc.disassembly">
                  {data?.documents?.disassembly?.url ? (
                    <a href={data.documents.disassembly.url} target="_blank" rel="noreferrer" className="wrap">
                      {data.documents.disassembly.name || "Document"}
                    </a>
                  ) : (
                    <span className="wrap">{data?.documents?.disassembly?.name || "—"}</span>
                  )}
                </KV>
              </ListGroup>

              <div className="h6 mt-3 d-flex align-items-center justify-content-between">
                <span>Tools for maintenance</span>
                <InfoTip placement="left" text={FIELD_HELP["tools.maintenance"]} />
              </div>
              {Array.isArray(data?.toolsForMaintenance) && data.toolsForMaintenance.length ? (
                <ul className="mb-0 wrap">
                  {data.toolsForMaintenance.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              ) : (
                <div className="text-muted">—</div>
              )}

              <div className="h6 mt-3 d-flex align-items-center justify-content-between">
                <span>Spare parts</span>
                <InfoTip placement="left" text={FIELD_HELP["spares.common"]} />
              </div>
              {Array.isArray(data?.spareParts) && data.spareParts.length ? (
                <ul className="mb-0 wrap">
                  {data.spareParts.map((s, i) => (
                    <li key={s.id || i}>{s.name || s.id}</li>
                  ))}
                </ul>
              ) : (
                <div className="text-muted">—</div>
              )}
            </Card.Body>
          </Card>

          <Card className="mb-3">
            <Card.Header className="h6 d-flex justify-content-between align-items-center">
              <span className="d-inline-flex align-items-center gap-2">
                Repair & refurbishment history
                <InfoTip placement="right" text={FIELD_HELP["history.service"]} />
              </span>
              <span className="text-muted small d-inline-flex align-items-center gap-2">
                Total cost:&nbsp;<strong>{eur(totalHistoryCost)}</strong>
                <InfoTip placement="left" text={FIELD_HELP["history.totalCost"]} />
              </span>
            </Card.Header>
            <Card.Body className="pb-0">
              {secSteps.length ? (
                <div className="table-responsive">
                  <Table bordered size="sm" className="mb-0 align-middle history-table">
                    <thead>
                      <tr>
                        <th style={{ width: "4ch" }} className="text-end">
                          #
                        </th>
                        <th style={{ width: "14%" }}>Step</th>
                        <th style={{ width: "20%" }}>Part(s)</th>
                        <th className="text-end" style={{ width: "12%" }}>
                          Cost (EUR)
                        </th>
                        <th style={{ width: "16%" }}>Begin date</th>
                        <th className="col-diagnose">Diagnose</th>
                        <th className="col-symptoms">Observed symptoms</th>
                      </tr>
                    </thead>
                    <tbody>
                      {secSteps.map((s, idx) => {
                        const parts = Array.isArray(s.partNames) ? s.partNames : [];
                        return (
                          <tr key={idx}>
                            <td className="text-end">{idx + 1}</td>
                            <td className="wrap">{s.type || "—"}</td>
                            <td className="wrap">{parts.length ? parts.join(", ") : "—"}</td>
                            <td className="text-end">{eur(s.costEUR ?? s.cost)}</td>
                            <td className="wrap">{fmtDate(s.beginDate)}</td>
                            <td className="wrap">{s.diagnose || s.diagnosis || "—"}</td>
                            <td className="wrap">{renderSymptoms(s.observedSymptoms)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </Table>
                </div>
              ) : (
                <div className="text-muted">No secondary-value steps recorded.</div>
              )}
            </Card.Body>
            {secSteps.length ? (
              <Card.Footer className="d-flex justify-content-end">
                <div className="text-muted small">
                  Total cost:&nbsp;<strong>{eur(totalHistoryCost)}</strong>
                </div>
              </Card.Footer>
            ) : null}
          </Card>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Symptoms → likely diagnoses</span>
              <InfoTip placement="left" text={FIELD_HELP["diag.probNote"]} />
            </Card.Header>
            <Card.Body className="pt-3">
              {diagSummary.length ? (
                <ListGroup variant="flush">
                  {diagSummary.map((entry, idx) => (
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
                          <div key={j} className="d-flex align-items-center flex-wrap diag-row mb-2">
                            <span className="diag-chip">
                              <span className="fw-semibold">{d.diagnosis || "—"}</span>
                              <span>({probPct}%)</span>
                            </span>
                            <div className="diag-prog" style={{ flex: "0 0 160px" }}>
                              <ProgressBar now={probPct} />
                            </div>
                            <span className="diag-sep" aria-hidden="true" />
                            <div className="diag-meta">
                              <span className="text-muted small d-inline-flex align-items-center gap-2">
                                avg cost:&nbsp;<strong>{eur(d.avgCostEUR)}</strong>
                                <InfoTip placement="right" text={FIELD_HELP["diag.avgCost"]} />
                              </span>
                              <span className="diag-sep" aria-hidden="true" />
                              <span className="text-muted small d-inline-flex align-items-center gap-2">
                                avg occur:&nbsp;<strong>{humanizeAvgDays(d.avgDaysSinceDeclaration)}</strong>
                                <InfoTip placement="right" text={FIELD_HELP["diag.avgOccur"]} />
                              </span>
                            </div>
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
          <Card className="mb-3 card-accent-warning">
            <Card.Header className="h6 d-flex align-items-center justify-content-between bg-warning bg-opacity-10">
              <span>Failing parts</span>
              <div className="d-inline-flex align-items-center gap-2">
                <Badge bg="warning" text="dark" className="rounded-pill">
                  {failingParts.length}
                </Badge>
                <InfoTip placement="left" text={FIELD_HELP["parts.failing"]} />
              </div>
            </Card.Header>
            <Card.Body>
              {failingParts.length ? (
                <>
                  <Alert variant="warning" className="py-2 mb-3">
                    Detected <strong>{failingParts.length}</strong> part{failingParts.length === 1 ? "" : "s"} currently
                    in failstate.
                  </Alert>
                  <ListGroup variant="flush">
                    {failingParts.map((fp) => (
                      <ListGroup.Item key={fp.id} className="fp-item">
                        <div className="wrap">
                          <div className="fw-semibold">{fp.name || fp.id}</div>
                          {fp.path && <div className="text-muted small item-path">{fp.path}</div>}
                        </div>
                      </ListGroup.Item>
                    ))}
                  </ListGroup>
                </>
              ) : (
                <Alert variant="success" className="mb-0">
                  No failing parts
                </Alert>
              )}
            </Card.Body>
          </Card>

          <Card className="mb-3 card-accent-info">
            <Card.Header className="h6 d-flex align-items-center justify-content-between bg-info bg-opacity-10">
              <span>Detached parts (history)</span>
              <div className="d-inline-flex align-items-center gap-2">
                <Badge bg="info" text="dark" className="rounded-pill">
                  {detachedParts.length}
                </Badge>
                <InfoTip placement="left" text={FIELD_HELP["parts.detached"]} />
              </div>
            </Card.Header>
            <Card.Body>
              {detachedParts.length ? (
                <>
                  <Alert variant="info" className="py-2 mb-3">
                    {detachedParts.length} detached part{detachedParts.length === 1 ? "" : "s"} recorded over the
                    product’s lifetime.
                  </Alert>
                  <ListGroup variant="flush">
                    {detachedParts.map((dp) => (
                      <ListGroup.Item key={dp.id} className="dp-item">
                        <div className="wrap">{dp.name || dp.id}</div>
                      </ListGroup.Item>
                    ))}
                  </ListGroup>
                </>
              ) : (
                <Alert variant="secondary" className="mb-0">
                  No detached parts recorded.
                </Alert>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="gy-3">
        <Col xs={12}>
          <Card className="mb-3">
            <Card.Header className="h6 d-flex align-items-center justify-content-between">
              <span>Parts</span>
              <InfoTip placement="left" text={FIELD_HELP["parts.title"]} />
            </Card.Header>
            <Card.Body>
              <div className="mb-2 d-flex align-items-center gap-3 flex-wrap">
                <div className="d-inline-flex align-items-center">
                  <strong>Total parts in device</strong>{" "}
                  <InfoTip className="ms-1" text={FIELD_HELP["parts.totalInTree"]} />: {data?.parts?.totalCount ?? "—"}
                </div>
                <div className="d-flex align-items-center">
                  <span className={`me-2 ${hasFails ? "text-danger" : "text-success"}`} style={{ fontSize: 16 }}>
                    {hasFails ? "⚠️" : "✅"}
                  </span>
                  <span className="d-inline-flex align-items-center">
                    <strong>Status of entire product</strong>{" "}
                    <InfoTip className="ms-1" text={FIELD_HELP["parts.statusOverall"]} />:{" "}
                    <>
                      <b>{healthyCount}</b>/<b>{totalPartsInTree}</b> OK
                    </>
                  </span>
                </div>
              </div>

              <PartTreeService
                rootParts={firstLevelParts}
                topPartId={topPartId}
                perPartStats={perPartStats}
                perPartMtbf={perPartMtbf}
                showModular={true}
                topHasFail={topHasFail}
                instanceId={instanceId}
                onRefresh={refreshAll}
                refreshSeq={treeRefreshSeq}
              />
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <ToastContainer position="bottom-end" className="p-3">
        <Toast
          bg={toast.variant === "danger" ? "danger" : "success"}
          onClose={() => setToast((t) => ({ ...t, show: false }))}
          show={toast.show}
          autohide
          delay={4000}
        >
          <Toast.Body className="text-white">{toast.msg}</Toast.Body>
        </Toast>
      </ToastContainer>

      <Modal show={showReg} onHide={() => setShowReg(false)} size="lg">
        <Modal.Header closeButton>
          <Modal.Title>Register service</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Row className="gy-3">
            <Col md={6}>
              <Form.Group>
                <Form.Label className="d-inline-flex align-items-center gap-2">
                  <span>Service type</span>
                  <InfoTip placement="right" text={FIELD_HELP["modal.stepType"]} />
                </Form.Label>
                <Form.Select value={stepType} onChange={(e) => setStepType(e.target.value)}>
                  <option value="RepairServiceStep">Repair</option>
                  <option value="ReplaceServiceStep">Replace</option>
                  <option value="CleaningServiceStep">Cleaning</option>
                  <option value="RemanufacturingServiceStep">Remanufacturing</option>
                  <option value="RefurbishmentServiceStep">Refurbishment</option>
                </Form.Select>
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group>
                <Form.Label className="d-inline-flex align-items-center gap-2">
                  <span>Processed at (place)</span>
                  <InfoTip placement="right" text={FIELD_HELP["modal.processedAt"]} />
                </Form.Label>
                <Form.Select value={placeId} onChange={(e) => setPlaceId(e.target.value)}>
                  {placeOptions.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>

            <Col md={6}>
              <Form.Group>
                <Form.Label className="d-inline-flex align-items-center gap-2">
                  <span>Part</span>
                  <InfoTip placement="right" text={FIELD_HELP["modal.part"]} />
                </Form.Label>
                <Form.Select value={selPartId} onChange={(e) => setSelPartId(e.target.value)}>
                  {partOptions.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </Form.Select>
                <Form.Text className="text-muted">List shows all parts (names from PartStatic)</Form.Text>
              </Form.Group>
            </Col>
            <Col md={3}>
              <Form.Group>
                <Form.Label className="d-inline-flex align-items-center gap-2">
                  <span>Cost (EUR)</span>
                  <InfoTip placement="right" text={FIELD_HELP["modal.cost"]} />
                </Form.Label>
                <Form.Control type="number" step="0.01" value={costEur} onChange={(e) => setCostEur(e.target.value)} />
              </Form.Group>
            </Col>
            <Col md={3}>
              <Form.Group>
                <Form.Label className="d-inline-flex align-items-center gap-2">
                  <span>Begin date</span>
                  <InfoTip placement="right" text={FIELD_HELP["modal.beginDate"]} />
                </Form.Label>
                <Form.Control
                  type="datetime-local"
                  value={beginDateISO}
                  onChange={(e) => setBeginDateISO(e.target.value)}
                />
              </Form.Group>
            </Col>

            {(stepType === "ReplaceServiceStep" ||
              stepType === "RemanufacturingServiceStep" ||
              stepType === "RefurbishmentServiceStep") && (
              <>
                <Col md={6}>
                  <Form.Group>
                    <Form.Label className="d-inline-flex align-items-center gap-2">
                      <span>New part (choose PartStatic)</span>
                      <InfoTip placement="right" text={FIELD_HELP["modal.newPartStatic"]} />
                    </Form.Label>
                    <Form.Select value={newStaticId} onChange={(e) => setNewStaticId(e.target.value)}>
                      {staticOptions.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label} — {s.id}
                        </option>
                      ))}
                    </Form.Select>
                  </Form.Group>
                </Col>
                <Col md={3}>
                  <Form.Group>
                    <Form.Label className="d-inline-flex align-items-center gap-2">
                      <span>Serial number</span>
                      <InfoTip placement="right" text={FIELD_HELP["modal.serial"]} />
                    </Form.Label>
                    <Form.Control value={newSerial} onChange={(e) => setNewSerial(e.target.value)} />
                  </Form.Group>
                </Col>
                <Col md={3}>
                  <Form.Group>
                    <Form.Label className="d-inline-flex align-items-center gap-2">
                      <span>Batch number</span>
                      <InfoTip placement="right" text={FIELD_HELP["modal.batch"]} />
                    </Form.Label>
                    <Form.Control value={newBatch} onChange={(e) => setNewBatch(e.target.value)} />
                  </Form.Group>
                </Col>
              </>
            )}

            <Col md={12}>
              <Form.Group>
                <Form.Label className="d-inline-flex align-items-center gap-2">
                  <span>Diagnose</span>
                  <InfoTip placement="right" text={FIELD_HELP["modal.diagnose"]} />
                </Form.Label>
                <Form.Control
                  placeholder="e.g., Seal wear in 3-way valve"
                  value={diagnose}
                  onChange={(e) => setDiagnose(e.target.value)}
                />
              </Form.Group>
            </Col>
            <Col md={12}>
              <Form.Group>
                <Form.Label className="d-inline-flex align-items-center gap-2">
                  <span>Observed symptoms</span>
                  <InfoTip placement="right" text={FIELD_HELP["modal.symptoms"]} />
                </Form.Label>
                <Form.Control
                  placeholder="Comma or semicolon separated, e.g., Water leakage; Low brew pressure"
                  value={symptomsStr}
                  onChange={(e) => setSymptomsStr(e.target.value)}
                />
              </Form.Group>
            </Col>
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowReg(false)} disabled={posting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={postStep} disabled={posting || !selPartId || !stepType}>
            {posting ? "Saving…" : "Save"}
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
 * Key/Value List item
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
