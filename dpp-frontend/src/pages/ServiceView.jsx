import React, { useEffect, useRef, useState } from "react";
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
  const [qualityChecking, setQualityChecking] = useState(false);
  const [qualityResult, setQualityResult] = useState(null);
  const [qualityErr, setQualityErr] = useState(null);
  const [serviceConcepts, setServiceConcepts] = useState(null);
  const [feedbackConceptByEntry, setFeedbackConceptByEntry] = useState({});
  const [appliedFeedbackByEntry, setAppliedFeedbackByEntry] = useState({});
  const appliedFeedbackRef = useRef({});

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

  useEffect(() => {
    setQualityResult(null);
    setQualityErr(null);
    setAppliedFeedbackByEntry({});
    appliedFeedbackRef.current = {};
  }, [stepType, selPartId, costEur, diagnose, symptomsStr, newStaticId, newSerial, newBatch]);

  useEffect(() => {
    if (!showReg || serviceConcepts) return;
    let on = true;
    (async () => {
      try {
        const payload = await api.listDataQualityServiceConcepts();
        if (on) setServiceConcepts(payload?.concepts_by_kind || {});
      } catch {
        if (on) setServiceConcepts({});
      }
    })();
    return () => {
      on = false;
    };
  }, [showReg, serviceConcepts]);

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
  const renderSymptoms = (sym, originalSymptoms = []) => {
    const arr = Array.isArray(sym) ? sym : typeof sym === "string" ? sym.split(/[;,]+/) : [];
    const clean = arr.map((s) => String(s).trim()).filter(Boolean);
    const originals = Array.isArray(originalSymptoms)
      ? originalSymptoms.map((s) => String(s).trim())
      : typeof originalSymptoms === "string"
        ? originalSymptoms.split(/[;,]+/).map((s) => s.trim())
        : [];
    if (!clean.length) return "—";
    return (
      <div className="sym-chip-list">
        {clean.map((s, i) => (
          <span key={i} className="sym-chip">
            <span className="sym-token">{s}</span>
            {originalInputTip(originals[i], s)}
          </span>
        ))}
      </div>
    );
  };
  const rawSymptomInputList = () =>
    symptomsStr
      .split(/[;,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  const originalInputTip = (original, current) => {
    const originalText = Array.isArray(original) ? original.filter(Boolean).join("; ") : String(original || "").trim();
    const currentText = Array.isArray(current) ? current.filter(Boolean).join("; ") : String(current || "").trim();
    if (!originalText || originalText === currentText) return null;
    return (
      <InfoTip
        className="btn p-0 ms-1 text-body-secondary bg-transparent border-0 history-original-tip"
        size={13}
        placement="top"
        label="Original input"
        text={`Original input: ${originalText}`}
      />
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

  const buildPendingServiceQualityDocument = () => {
    const node = {
      "@id": "pending-service-step",
      "@type": `dpp:${stepType}`,
      costEur: Number(costEur) || 0,
      diagnose: diagnose || "",
      observedSymptoms: symptomsStr
        .split(/[;,]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    };

    if (stepType === "RepairServiceStep") {
      node.repairedPartId = selPartId;
    } else if (stepType === "CleaningServiceStep") {
      node.cleanedPartId = selPartId;
    } else if (stepType === "ReplaceServiceStep") {
      node.replacedPartId = selPartId;
      node.newPart = { "@id": newStaticId || "pending-new-part", "@type": "dpp:PartInstance" };
    } else if (stepType === "RemanufacturingServiceStep" || stepType === "RefurbishmentServiceStep") {
      node.repairedPartIds = [];
      node.cleanedPartIds = [];
      node.replacedAndNewParts = [
        [selPartId, { "@id": newStaticId || "pending-new-part", "@type": "dpp:PartInstance" }],
      ];
    }

    return {
      "@context": {
        dpp: "https://example.com/dpp#",
        schema: "https://schema.org/",
      },
      "@graph": [node],
    };
  };

  const runServiceQualityCheck = async () => {
    setQualityChecking(true);
    setQualityErr(null);
    setQualityResult(null);
    try {
      const selectedPart = partOptions.find((part) => part.id === selPartId);
      const response = await api.runDataQuality({
        scope: "service",
        mode: "both",
        document: buildPendingServiceQualityDocument(),
        enable_llm_review: true,
        review_context: {
          selectedPartId: selPartId,
          selectedPartLabel: selectedPart?.label || selPartId,
          selectedServiceType: stepType,
        },
      });
      setQualityResult(response);
      return response;
    } catch (e) {
      const message = e?.message || String(e);
      setQualityErr(message);
      setToast({ show: true, msg: `Data quality check failed: ${message}`, variant: "danger" });
      return null;
    } finally {
      setQualityChecking(false);
    }
  };

  const cleanServiceTextFromQuality = (quality) => {
    const node = Array.isArray(quality?.data?.["@graph"]) ? quality.data["@graph"][0] : null;
    const cleanSymptoms = node?.["dpp:observedSymptoms"] ?? node?.observedSymptoms;
    const baseSymptomList = Array.isArray(cleanSymptoms)
      ? cleanSymptoms
      : typeof cleanSymptoms === "string"
        ? [cleanSymptoms]
        : symptomsStr
            .split(/[;,]+/)
            .map((s) => s.trim())
            .filter(Boolean);
    const appliedFeedback = Object.values(appliedFeedbackByEntry);
    const appliedDiagnose = appliedFeedback.find((item) => item?.field_name === "diagnose");
    const appliedSymptoms = appliedFeedback.filter((item) => item?.field_name === "observedSymptoms");
    const symptomList = baseSymptomList.map((symptom) => {
      const applied = appliedSymptoms.find((item) => item.original_value === symptom);
      return applied?.concept_id || symptom;
    });

    return {
      diagnose: appliedDiagnose?.concept_id || node?.["dpp:diagnose"] || node?.diagnose || diagnose || "",
      observedSymptoms: symptomList,
    };
  };

  const serviceConceptOptionsForEntry = (entry) => {
    const kind = entry?.field_name === "diagnose" ? "diagnosis" : "symptom";
    return Array.isArray(serviceConcepts?.[kind]) ? serviceConcepts[kind] : [];
  };

  const feedbackEntryKey = (entry, index) =>
    `${entry.entity_id || "entity"}:${entry.field_name || "field"}:${index}:${entry.original_value || ""}`;

  const closeServiceRegister = () => {
    setShowReg(false);
    setAppliedFeedbackByEntry({});
    appliedFeedbackRef.current = {};
    setFeedbackConceptByEntry({});
    setQualityResult(null);
    setQualityErr(null);
  };

  const stageLearnedFeedbackForRecord = (entry, index, conceptId, shouldStoreFeedback = true) => {
    const key = feedbackEntryKey(entry, index);
    const options = serviceConceptOptionsForEntry(entry);
    const selectedConcept = conceptId || feedbackConceptByEntry[key] || options[0]?.concept_id || "";
    if (!selectedConcept) {
      setToast({ show: true, msg: "No service concept available for this feedback entry.", variant: "warning" });
      return;
    }

    const preparedFeedback = {
      entity_type: entry.entity_type || stepType,
      field_name: entry.field_name,
      field_path: `${entry.entity_type || stepType}.${entry.field_name}`,
      original_value: entry.original_value,
      concept_id: selectedConcept,
      should_store_feedback: shouldStoreFeedback,
    };
    appliedFeedbackRef.current = {
      ...appliedFeedbackRef.current,
      [key]: preparedFeedback,
    };
    setAppliedFeedbackByEntry((current) => ({
      ...current,
      [key]: preparedFeedback,
    }));
    setToast({
      show: true,
      msg: shouldStoreFeedback
        ? "Feedback prepared. It will be stored when this service step is saved."
        : "Learned suggestion prepared for this record.",
      variant: "success",
    });
  };

  const storePreparedFeedbackAfterSave = async () => {
    const pendingFeedback = Object.keys(appliedFeedbackRef.current).length
      ? appliedFeedbackRef.current
      : appliedFeedbackByEntry;
    const entriesToStore = Object.values(pendingFeedback).filter((entry) => entry?.should_store_feedback);
    if (entriesToStore.length === 0) return null;

    try {
      await Promise.all(entriesToStore.map((entry) =>
        api.createDataQualityServiceTextFeedback({
          entity_type: entry.entity_type || stepType,
          field_path: entry.field_path || `${entry.entity_type || stepType}.${entry.field_name}`,
          original_value: entry.original_value,
          concept_id: entry.concept_id,
          proposed_surface_form: entry.original_value,
          rationale: "Added through the service quality feedback UI after saving the service record.",
        })
      ));
      return { ok: true, count: entriesToStore.length };
    } catch (e) {
      return { ok: false, error: e?.message || String(e) };
    }
  };

  const postStep = async () => {
    try {
      const quality = await runServiceQualityCheck();
      if (!quality) return;
      if (quality.has_errors) {
        setToast({
          show: true,
          msg: "Please review the data-quality errors before saving this service step.",
          variant: "danger",
        });
        return;
      }

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
      const cleanServiceText = cleanServiceTextFromQuality(quality);
      const payloadCommon = {
        type: stepType,
        ...baseDates,
        ...(processedAt ? { processedAt } : {}),
        ghgEmissionRecords: [],
        costEur: Number(costEur) || 0,
        diagnose: cleanServiceText.diagnose,
        observedSymptoms: cleanServiceText.observedSymptoms,
        originalDiagnose: diagnose || "",
        originalObservedSymptoms: rawSymptomInputList(),
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
      const feedbackStorage = await storePreparedFeedbackAfterSave();
      await refreshAll();
      setShowReg(false);
      setAppliedFeedbackByEntry({});
      appliedFeedbackRef.current = {};
      setFeedbackConceptByEntry({});
      if (feedbackStorage && !feedbackStorage.ok) {
        setToast({
          show: true,
          msg: `Service step registered, but learned feedback could not be stored: ${feedbackStorage.error}`,
          variant: "warning",
        });
      } else {
        setToast({ show: true, msg: "Service step registered.", variant: "success" });
      }
    } catch (e) {
      setToast({ show: true, msg: `Failed to register step: ${e?.message || e}`, variant: "danger" });
    } finally {
      setPosting(false);
    }
  };
  const discontinued = !!inst?.discontinued;
  const qualityTextEntries = flattenServiceTextEntries(qualityResult);
  const qualityFindings = Array.isArray(qualityResult?.anomaly_report?.findings)
    ? qualityResult.anomaly_report.findings
    : [];
  const qualityLlmFindings = qualityFindings.filter(
    (finding) => finding?.evidence?.check_method === "llm_service_review",
  );
  const qualityPlausibilityFindings = qualityFindings.filter(
    (finding) => finding?.evidence?.check_method !== "llm_service_review",
  );
  const qualitySummary = qualityResult?.harmonization_report?.summary;

  return (
    <Container className="py-3">
      <style>{`
        .wrap { white-space: normal !important; word-break: break-word !important; overflow-wrap: anywhere !important; }
        .history-table { table-layout: fixed; }
        .history-table th, .history-table td { vertical-align: top; }
        @media (max-width: 576px) { .col-diagnose, .col-symptoms { width: 100%; } }
        .sym-chip-list { display: flex; flex-wrap: nowrap; gap: .35rem .5rem; align-items: center; max-width: 100%; overflow-x: auto; overflow-y: hidden; padding-right: .4rem; padding-bottom: .1rem; scroll-padding-right: .4rem; }
        .sym-chip { display: inline-flex; align-items: center; gap: .25rem; max-width: 100%; line-height: 1.35; }
        .sym-token { white-space: nowrap; overflow-wrap: normal; word-break: normal; }
        .diag-chip { display:inline-flex; align-items:center; gap:.5rem; padding:.25rem .5rem; border-radius:.5rem; background:#f8f9fa; }
        .diag-row { gap:.75rem; }
        .diag-sep { width: 1px; height: 18px; background: #e0e0e0; display:inline-block; }
        .diag-meta { display:inline-flex; align-items:center; gap:.5rem; flex-wrap: wrap; }
        .diag-prog { min-width: 120px; }
        .quality-llm-review { border-left: 3px solid #6f42c1; background: #f7f3ff; padding: .5rem .65rem; }
        .quality-learned-feedback { border-left: 3px solid #0d6efd; background: #f4f8ff; padding: .45rem .6rem; margin-top: .35rem; }
        .quality-feedback-applied { border-left: 3px solid #198754; background: #f3fbf6; padding: .45rem .6rem; margin-top: .35rem; }
        .quality-feedback-action { border-left: 3px solid #adb5bd; background: #f8f9fa; padding: .45rem .6rem; margin-top: .35rem; }
        .quality-candidate-meta { color: #6c757d; }
        .quality-caution-note { display:flex; align-items:flex-start; gap:.35rem; font-size:.74rem; line-height:1.25; color:#6c757d; margin-top:.3rem; }
        .quality-caution-mark { display:inline-flex; align-items:center; justify-content:center; flex:0 0 auto; width:.95rem; height:.95rem; border-radius:50%; border:1px solid #adb5bd; font-size:.68rem; font-weight:700; color:#6c757d; margin-top:.02rem; }
        .history-original-tip { display: inline-flex; flex: 0 0 auto; vertical-align: -0.1em; line-height: 1; margin-left: .1rem !important; }
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
                            <td className="wrap">
                              {s.diagnose || s.diagnosis || "—"}
                              {originalInputTip(s.originalDiagnose, s.diagnose || s.diagnosis)}
                            </td>
                            <td className="wrap">
                              {renderSymptoms(s.observedSymptoms, s.originalObservedSymptoms)}
                            </td>
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

      <Modal show={showReg} onHide={closeServiceRegister} size="lg">
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

            <Col md={12}>
              <Card className="border-info">
                <Card.Header className="d-flex flex-column flex-md-row align-items-md-center justify-content-between gap-2">
                  <span className="fw-semibold">Data quality check</span>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={runServiceQualityCheck}
                    disabled={qualityChecking || !selPartId || !stepType}
                  >
                    {qualityChecking ? (
                      <>
                        <Spinner animation="border" size="sm" className="me-1" />
                        Checking…
                      </>
                    ) : (
                      "Check input"
                    )}
                  </Button>
                </Card.Header>
                <Card.Body>
                  {!qualityResult && !qualityErr && (
                    <div className="text-muted small">
                      Runs harmonization and plausibility checks for this service input before it is saved.
                    </div>
                  )}
                  {qualityErr && <Alert variant="danger" className="py-2 mb-0">{qualityErr}</Alert>}
                  {qualityResult && (
                    <div className="d-flex flex-column gap-2">
                      <div className="d-flex flex-wrap gap-2">
                        {qualityResult.has_errors && <Badge bg="danger">Review required</Badge>}
                        <Badge bg="secondary">
                          Text {qualitySummary?.text_harmonization_status_counts?.normalized ?? 0}/
                          {qualityTextEntries.length}
                        </Badge>
                        {qualityPlausibilityFindings.length > 0 && (
                          <Badge bg="warning">Plausibility {qualityPlausibilityFindings.length}</Badge>
                        )}
                      </div>

                      {qualityTextEntries.length > 0 && (
                        <div>
                          <div className="small fw-semibold mb-1">Text harmonization</div>
                          <ListGroup variant="flush">
                            {qualityTextEntries.slice(0, 4).map((entry, index) => (
                              <ListGroup.Item key={`${entry.field_name}-${index}`} className="px-0 py-1">
                                <div className="d-flex flex-wrap align-items-center gap-2">
                                  <Badge bg={entry.status === "normalized" ? "success" : "warning"}>
                                    {entry.status}
                                  </Badge>
                                  <span className="small">{entry.field_name}:</span>
                                  <span className="small text-muted wrap">{entry.original_value}</span>
                                  {entry.normalized_value && (
                                    <span className="small fw-semibold">→ {entry.normalized_value}</span>
                                  )}
                                </div>
                                {entry.status !== "normalized" && renderTextCandidateTrace(entry, {
                                  onUseLearnedCandidate: (candidate) =>
                                    stageLearnedFeedbackForRecord(entry, index, candidate.concept_id, true),
                                  showLearnedAction: !appliedFeedbackByEntry[feedbackEntryKey(entry, index)],
                                })}
                                {entry.status !== "normalized" && renderAppliedFeedbackForRecord(
                                  appliedFeedbackByEntry[feedbackEntryKey(entry, index)]
                                )}
                                {entry.status !== "normalized" && !appliedFeedbackByEntry[feedbackEntryKey(entry, index)] && renderLearnedFeedbackAction(entry, index, {
                                  concepts: serviceConceptOptionsForEntry(entry),
                                  selectedConcept: feedbackConceptByEntry[feedbackEntryKey(entry, index)],
                                  onSelect: (conceptId) =>
                                    setFeedbackConceptByEntry((current) => ({
                                      ...current,
                                      [feedbackEntryKey(entry, index)]: conceptId,
                                    })),
                                  onSubmit: () => stageLearnedFeedbackForRecord(entry, index),
                                })}
                              </ListGroup.Item>
                            ))}
                          </ListGroup>
                        </div>
                      )}

                      {qualityPlausibilityFindings.length > 0 && (
                        <div>
                          <div className="small fw-semibold mb-1">Plausibility notes</div>
                          <ListGroup variant="flush">
                            {qualityPlausibilityFindings.slice(0, 4).map((finding, index) => (
                              <ListGroup.Item key={`${finding.check_id}-${index}`} className="px-0 py-1">
                                <Badge bg={severityVariant(finding.severity)} className="me-2">
                                  {finding.severity}
                                </Badge>
                                <span className="small wrap">{finding.message}</span>
                              </ListGroup.Item>
                            ))}
                          </ListGroup>
                        </div>
                      )}

                      {qualityLlmFindings.length > 0 && (
                        <div className="quality-llm-review">
                          <div className="small fw-semibold mb-1">LLM service review</div>
                          <ListGroup variant="flush">
                            {qualityLlmFindings.slice(0, 2).map((finding, index) => (
                              <ListGroup.Item
                                key={`${finding.check_id}-${index}`}
                                className="px-0 py-1 border-0 bg-transparent"
                              >
                                <Badge bg={severityVariant(finding.severity)} className="me-2">
                                  {finding.severity}
                                </Badge>
                                <span className="small wrap">{finding.message}</span>
                              </ListGroup.Item>
                            ))}
                          </ListGroup>
                          <div className="quality-caution-note">
                            <span className="quality-caution-mark">!</span>
                            <span>Advisory only; verify with domain knowledge.</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={closeServiceRegister} disabled={posting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={postStep} disabled={posting || qualityChecking || !selPartId || !stepType}>
            {posting ? "Saving…" : qualityChecking ? "Checking…" : "Save"}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

function severityVariant(severity) {
  if (severity === "error") return "danger";
  if (severity === "warning") return "warning";
  if (severity === "info") return "info";
  return "secondary";
}

function flattenServiceTextEntries(result) {
  const entries = [];

  function collect(value, entity, fieldName) {
    if (Array.isArray(value)) {
      value.forEach((item) => collect(item, entity, fieldName));
      return;
    }
    if (value && typeof value === "object" && value.status && value.original_value !== undefined) {
      entries.push({
        entity_id: entity.entity_id,
        entity_type: entity.entity_type,
        field_name: fieldName,
        ...value,
      });
    }
  }

  for (const entity of Object.values(result?.harmonization_report?.entities || {})) {
    for (const [fieldName, value] of Object.entries(entity.text_harmonization || {})) {
      collect(value, entity, fieldName);
    }
  }

  return entries;
}

function safeNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v : "—";
}

function renderTextCandidateTrace(entry, { onUseLearnedCandidate, showLearnedAction = true } = {}) {
  const learnedCandidates = Array.isArray(entry.candidates)
    ? entry.candidates.filter((candidate) => candidate?.source === "learned_feedback")
    : [];
  const visibleLearnedCandidates = showLearnedAction ? learnedCandidates : [];
  const candidates = Array.isArray(entry.closest_candidates) && entry.closest_candidates.length
    ? entry.closest_candidates
    : Array.isArray(entry.candidates)
      ? entry.candidates
      : [];
  if (!candidates.length && !visibleLearnedCandidates.length) return null;

  const thresholds = entry.thresholds || {};
  const rows = candidates
    .filter((candidate) => candidate?.source !== "learned_feedback")
    .slice(0, 3)
    .map((candidate) => {
      const method = candidate.match_type || candidate.method || "candidate";
      const score = formatScore(candidate.confidence);
      const reportingThreshold = method === "semantic"
        ? thresholds.candidate_semantic_reporting_threshold
        : thresholds.candidate_fuzzy_reporting_threshold;
      const autoThreshold = method === "semantic"
        ? thresholds.automatic_semantic_threshold
        : thresholds.automatic_fuzzy_threshold;
      return {
        method,
        conceptId: candidate.concept_id,
        score,
        thresholdText: coreCandidateThresholdText(candidate, reportingThreshold, autoThreshold),
      };
    });

  return (
    <div className="small mt-1 wrap">
      {visibleLearnedCandidates.length > 0 && (
        <div className="quality-learned-feedback">
          <div className="fw-semibold">Learned feedback suggestion</div>
          <ul className="mb-0 ps-3">
            {visibleLearnedCandidates.slice(0, 2).map((candidate) => (
              <li key={`${candidate.feedback_id || candidate.concept_id}-${candidate.method || candidate.match_type}`}>
                <div>
                  <span className="fw-semibold">{candidate.concept_id}</span>
                  <span className="quality-candidate-meta"> ({learnedFeedbackMatchLabel(candidate)})</span>
                </div>
                <div className="quality-candidate-meta">
                  {learnedFeedbackThresholdText(candidate, thresholds)}
                </div>
                {showLearnedAction && typeof onUseLearnedCandidate === "function" && (
                  <Button
                    size="sm"
                    variant="outline-primary"
                    className="mt-1 py-0"
                    onClick={() => onUseLearnedCandidate(candidate)}
                  >
                    Use for this record
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {rows.length > 0 && (
        <div className="text-muted mt-1">
          <div>Core candidate trace:</div>
          <ul className="mb-0 ps-3">
            {rows.map((row) => (
              <li key={`${row.method}-${row.conceptId}`}>
                {row.method}: {row.conceptId} {row.score} {row.thresholdText}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function coreCandidateThresholdText(candidate, candidateThreshold, autoThreshold) {
  const score = Number(candidate?.confidence);
  const candidateScore = Number(candidateThreshold);
  const autoScore = Number(autoThreshold);
  const candidateText = formatScore(candidateThreshold);
  const autoText = formatScore(autoThreshold);

  if (!Number.isFinite(score)) {
    return `(candidate >= ${candidateText}, auto >= ${autoText})`;
  }
  if (Number.isFinite(autoScore) && score >= autoScore) {
    return `(would auto-match; auto >= ${autoText})`;
  }
  if (Number.isFinite(candidateScore) && score >= candidateScore) {
    return `(candidate only; auto >= ${autoText})`;
  }
  return `(below candidate; candidate >= ${candidateText}, auto >= ${autoText})`;
}

function learnedFeedbackMatchLabel(candidate) {
  const method = candidate?.method || candidate?.match_type || "";
  if (method.includes("exact")) return "exact learned feedback match";
  if (method.includes("fuzzy")) return "similar learned feedback match";
  if (method.includes("semantic")) return "semantic learned feedback match";
  return "learned feedback match";
}

function learnedFeedbackThresholdText(candidate, thresholds = {}) {
  const method = candidate?.method || candidate?.match_type || "";
  const score = formatScore(candidate?.confidence);
  if (method.includes("exact")) {
    return `score ${score}; approval required`;
  }

  const candidateThreshold = method.includes("semantic")
    ? thresholds.candidate_semantic_reporting_threshold
    : thresholds.candidate_fuzzy_reporting_threshold;
  return `score ${score} (candidate >= ${formatScore(candidateThreshold)}; approval required)`;
}

function renderLearnedFeedbackAction(entry, index, { concepts, selectedConcept, onSelect, onSubmit }) {
  if (!Array.isArray(concepts) || concepts.length === 0) return null;
  const alreadyHasLearnedCandidate = Array.isArray(entry.candidates)
    && entry.candidates.some((candidate) => candidate?.source === "learned_feedback");

  const value = selectedConcept || "";

  return (
    <div className="quality-feedback-action">
      <div className="small fw-semibold mb-1">
        {alreadyHasLearnedCandidate ? "Use another service concept for this record" : "Use as learned feedback for this record"}
      </div>
      <div className="d-flex flex-column flex-md-row gap-2">
        <Form.Select
          size="sm"
          value={value}
          onChange={(event) => onSelect(event.target.value)}
          aria-label={`Select service concept for ${entry.field_name || "service text"} feedback ${index + 1}`}
        >
          <option value="">Select concept…</option>
          {concepts.map((concept) => (
            <option key={concept.concept_id} value={concept.concept_id}>
              {concept.concept_id} · {concept.label}
            </option>
          ))}
        </Form.Select>
        <Button size="sm" variant="outline-primary" onClick={onSubmit} disabled={!value}>
          Use
        </Button>
      </div>
      <div className="small text-muted mt-1">
        Prepares this text for the current record. New feedback is stored only after the service record is saved.
      </div>
      <div className="quality-caution-note">
        <span className="quality-caution-mark">!</span>
        <span>Use only when the mapping is reliable, because saved feedback can influence future suggestions.</span>
      </div>
    </div>
  );
}

function renderAppliedFeedbackForRecord(appliedFeedback) {
  if (!appliedFeedback?.concept_id) return null;

  return (
    <div className="quality-feedback-applied">
      <div className="small fw-semibold">Learned feedback prepared for this record</div>
      <div className="small">
        This entry will be saved as <span className="fw-semibold">{appliedFeedback.concept_id}</span>.
      </div>
      <div className="small text-muted">
        Original input remains available in the service history details. New learned feedback is stored only after Save.
      </div>
    </div>
  );
}

function formatScore(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : "—";
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
