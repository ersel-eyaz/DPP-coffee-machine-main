import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  ButtonGroup,
  Card,
  Col,
  Container,
  Form,
  Modal,
  Row,
  Spinner,
  Tab,
  Table,
  Tabs,
} from "react-bootstrap";
import { Download, FileEarmarkCode, PlayFill, Upload } from "react-bootstrap-icons";

import { api } from "../api";

const EMPTY_INPUT = `{
  "@context": {},
  "@graph": []
}`;

function prettyJson(value) {
  return JSON.stringify(value, null, 2);
}

function JsonPanel({ title, value }) {
  return (
    <Card className="h-100">
      <Card.Header className="d-flex align-items-center justify-content-between">
        <span className="fw-semibold">{title}</span>
        <Badge bg="secondary">JSON</Badge>
      </Card.Header>
      <Card.Body className="p-0">
        <pre className="m-0 p-3 bg-light dq-json-scroll" style={{ minHeight: 320, maxHeight: 560, fontSize: "0.84rem" }}>
          {value ? prettyJson(value) : "No output yet."}
        </pre>
      </Card.Body>
    </Card>
  );
}

function severityVariant(severity) {
  if (severity === "error") return "danger";
  if (severity === "warning") return "warning";
  if (severity === "info") return "info";
  return "secondary";
}

function statusVariant(status) {
  if (status === "error") return "danger";
  if (status === "unmapped" || status === "ambiguous" || status === "unresolved") return "warning";
  if (status === "mapped" || status === "normalized") return "success";
  return "secondary";
}

function formatMethod(method, confidence) {
  if (!method) return "-";
  return typeof confidence === "number" ? `${method} (${confidence.toFixed(2)})` : method;
}

function formatScore(value) {
  return typeof value === "number" ? value.toFixed(2) : null;
}

function formatThresholds(thresholds) {
  if (!thresholds) return "-";

  const parts = [];
  const fuzzyAuto = formatScore(thresholds.automatic_fuzzy_threshold);
  const fuzzyCandidate = formatScore(
    thresholds.candidate_reporting_threshold ?? thresholds.candidate_fuzzy_reporting_threshold,
  );
  const semanticAuto = formatScore(thresholds.automatic_semantic_threshold);
  const semanticCandidate = formatScore(thresholds.candidate_semantic_reporting_threshold);
  const margin = formatScore(thresholds.minimum_margin ?? thresholds.minimum_fuzzy_margin);
  const semanticMargin = formatScore(thresholds.minimum_semantic_margin);

  if (fuzzyAuto) parts.push(`fuzzy auto >= ${fuzzyAuto}`);
  if (fuzzyCandidate) parts.push(`candidate >= ${fuzzyCandidate}`);
  if (semanticAuto) parts.push(`semantic auto >= ${semanticAuto}`);
  if (semanticCandidate) parts.push(`semantic candidate >= ${semanticCandidate}`);
  if (margin) parts.push(`margin >= ${margin}`);
  if (semanticMargin && semanticMargin !== margin) parts.push(`semantic margin >= ${semanticMargin}`);

  return parts.length ? parts.join(" · ") : "-";
}

function collectThresholdProfiles(items, key) {
  const profiles = [];
  for (const item of items) {
    const text = formatThresholds(item?.[key]);
    if (text !== "-" && !profiles.includes(text)) profiles.push(text);
  }
  return profiles;
}

function ThresholdSummary({ label, profiles }) {
  if (!profiles?.length) return null;
  return (
    <div className="small text-muted">
      <span className="fw-semibold">{label} thresholds:</span>{" "}
      {profiles.join(" | ")}
    </div>
  );
}

function GuidancePanel({ guidance }) {
  if (!guidance) return null;
  const targets = Array.isArray(guidance.targets) ? guidance.targets : [];
  const visibleTargets = targets.slice(0, 10);
  return (
    <div className="border rounded bg-light py-2 px-2 mt-2 mb-0">
      <div className="small fw-semibold">{guidance.message || "Expected targets"}</div>
      {visibleTargets.length > 0 && (
        <div className="small mt-1 d-flex flex-wrap gap-1">
          {visibleTargets.map((target, index) => (
            <Badge key={`${target.id || target.label || index}`} bg="light" text="dark" className="border">
              {target.id || target.label}
              {target.target_unit ? ` · ${target.target_unit}` : ""}
            </Badge>
          ))}
          {targets.length > visibleTargets.length && (
            <Badge bg="secondary">+{targets.length - visibleTargets.length} more</Badge>
          )}
        </div>
      )}
    </div>
  );
}

function sameThresholdProfiles(left, right) {
  return left.length > 0
    && right.length > 0
    && left.length === right.length
    && left.every((item, index) => item === right[index]);
}

function FieldValueThresholdSummary({ fieldProfiles, valueProfiles }) {
  if (sameThresholdProfiles(fieldProfiles, valueProfiles)) {
    return <ThresholdSummary label="Decision" profiles={fieldProfiles} />;
  }

  return (
    <>
      <ThresholdSummary label="Label" profiles={fieldProfiles} />
      <ThresholdSummary label="Value/unit" profiles={valueProfiles} />
    </>
  );
}

function flattenHarmonizationIssues(report) {
  const issues = [...(report?.global_issues || [])];
  for (const entity of Object.values(report?.entities || {})) {
    issues.push(...(entity.issues || []));
  }
  return issues;
}

function flattenTextConcepts(report) {
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

  for (const entity of Object.values(report?.entities || {})) {
    for (const [fieldName, value] of Object.entries(entity.text_harmonization || {})) {
      collect(value, entity, fieldName);
    }
  }
  return entries;
}

function issueMatchesTextEntry(issue, entry) {
  return issue.entity_id === entry.entity_id
    && issue.field_label === entry.field_name
    && String(issue.message || "").includes(String(entry.original_value));
}

function textEntryIssues(entry, issues) {
  return issues.filter((issue) => issueMatchesTextEntry(issue, entry));
}

function nonTextHarmonizationIssues(issues, textConcepts) {
  return issues.filter((issue) => !textConcepts.some((entry) => issueMatchesTextEntry(issue, entry)));
}

function controlledVocabularyFields(report) {
  const paths = new Set(["ActivityData.activity_type", "GHGEmissionRecord.scope", "GHGEmissionRecord.scope3_category"]);
  return flattenHarmonizationEntities(report).filter((field) => paths.has(field.canonical_path));
}

function SummaryBadges({ result, onBadgeClick }) {
  const harmonization = result?.harmonization_report?.summary;
  const anomaly = result?.anomaly_report?.summary;
  const fields = flattenHarmonizationEntities(result?.harmonization_report);
  const changedFields = fields.filter((field) => isChangedField(field));
  const harmonizationIssues = flattenHarmonizationIssues(result?.harmonization_report);
  const textConcepts = flattenTextConcepts(result?.harmonization_report);
  const normalizedTextConcepts = textConcepts.filter((entry) => entry.status === "normalized").length;
  const vocabularyFields = controlledVocabularyFields(result?.harmonization_report);
  const serviceScope = result?.scope === "service";
  const visibleHarmonizationIssues = serviceScope
    ? nonTextHarmonizationIssues(harmonizationIssues, textConcepts)
    : harmonizationIssues;
  const emissionScope = result?.scope === "emission";
  if (!harmonization && !anomaly) return null;

  return (
    <Row className="g-2 mb-3">
      {harmonization && (
        <>
          <Col xs="auto">
            <Badge
              as="button"
              type="button"
              className="dq-summary-badge"
              bg="secondary"
              title="Show parsed entities"
              onClick={() => onBadgeClick?.("entities")}
            >
              Entities {harmonization.entities_total ?? 0}
            </Badge>
          </Col>
          {!serviceScope && (
            <Col xs="auto">
              <Badge
                as="button"
                type="button"
                className="dq-summary-badge"
              bg="secondary"
              title="Show labels or values changed by harmonization"
              onClick={() => onBadgeClick?.("changed-fields")}
            >
              Changed labels/values {changedFields.length}
            </Badge>
            </Col>
          )}
          {(!serviceScope || harmonization.unmapped_fields_total > 0) && (
            <Col xs="auto">
              <Badge
                as="button"
                type="button"
                className="dq-summary-badge"
                bg={harmonization.unmapped_fields_total ? "warning" : "success"}
                title="Show input labels that could not be mapped to canonical fields"
                onClick={() => onBadgeClick?.("unmapped")}
              >
                Unmapped labels {harmonization.unmapped_fields_total ?? 0}
              </Badge>
            </Col>
          )}
          {serviceScope && (
            <Col xs="auto">
              <Badge
                as="button"
                type="button"
                className="dq-summary-badge"
                bg={normalizedTextConcepts === textConcepts.length && textConcepts.length ? "success" : "warning"}
                title="Show service-text harmonization results and notes"
                onClick={() => onBadgeClick?.("text-harmonization")}
              >
                Text harmonization {normalizedTextConcepts}/{textConcepts.length}
              </Badge>
            </Col>
          )}
          {emissionScope && vocabularyFields.length > 0 && (
            <Col xs="auto">
              <Badge
                as="button"
                type="button"
                className="dq-summary-badge"
                bg={vocabularyFields.some((field) => field.status === "error") ? "danger" : "info"}
                title="Show controlled-vocabulary normalization results"
                onClick={() => onBadgeClick?.("controlled-values")}
              >
                Controlled values {vocabularyFields.length}
              </Badge>
            </Col>
          )}
          {(!serviceScope || visibleHarmonizationIssues.length > 0) && (
            <Col xs="auto">
              <Badge
                as="button"
                type="button"
                className="dq-summary-badge"
                bg={visibleHarmonizationIssues.length ? "warning" : "success"}
                title="Show harmonization issues and candidate decisions"
                onClick={() => onBadgeClick?.("harmonization-issues")}
              >
                Harmonization notes {visibleHarmonizationIssues.length}
              </Badge>
            </Col>
          )}
        </>
      )}
      {anomaly && (
        <>
          <Col xs="auto">
            <Badge
              as="button"
              type="button"
              className="dq-summary-badge"
              bg={anomaly.findings_total ? "warning" : "success"}
              title="Show all anomaly/plausibility findings"
              onClick={() => onBadgeClick?.("findings")}
            >
              Anomaly findings {anomaly.findings_total ?? 0}
            </Badge>
          </Col>
        </>
      )}
    </Row>
  );
}

function flattenHarmonizationEntities(report) {
  const rows = [];
  for (const entity of Object.values(report?.entities || {})) {
    for (const field of Object.values(entity.fields || {})) {
      rows.push({
        entity_id: entity.entity_id,
        entity_type: entity.entity_type,
        ...field,
      });
    }
    for (const field of entity.unmapped_fields || []) {
      const originalLabel = field.original_label || field.label;
      const originalValue = field.original_value ?? field.value;
      rows.push({
        entity_id: entity.entity_id,
        entity_type: entity.entity_type,
        canonical_path: originalLabel || "(unmapped)",
        original_label: originalLabel,
        original_value: originalValue,
        normalized_value: null,
        status: "unmapped",
        confidence: null,
        guidance: field.guidance,
      });
    }
  }
  return rows;
}

function stableJson(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => stableJson(item)).join(",")}]`;
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
    .join(",")}}`;
}

function canonicalFieldLabel(field) {
  return field.jsonld_term?.split(":").pop()
    || field.canonical_path?.split(".").pop()
    || field.canonical_path
    || "-";
}

function isMeasurementObject(value) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && Object.prototype.hasOwnProperty.call(value, "value")
    && Object.prototype.hasOwnProperty.call(value, "unit");
}

function fieldChangeTypes(field) {
  if (field.status === "unmapped" || field.status === "error") return [];
  const changes = [];
  if (field.original_label && field.original_label !== canonicalFieldLabel(field)) changes.push("label");

  if (field.normalized_value !== undefined) {
    if (isMeasurementObject(field.original_value) && isMeasurementObject(field.normalized_value)) {
      if (stableJson(field.original_value.value) !== stableJson(field.normalized_value.value)) changes.push("value");
      if (stableJson(field.original_value.unit) !== stableJson(field.normalized_value.unit)) changes.push("unit");
    } else if (stableJson(field.original_value) !== stableJson(field.normalized_value)) {
      changes.push("value");
    }
  }
  return changes;
}

function isChangedField(field) {
  return fieldChangeTypes(field).length > 0;
}

function changeLabel(field) {
  const changes = fieldChangeTypes(field);
  return changes.length ? changes.join(" + ") : "none";
}

function HarmonizationTable({ report }) {
  const rows = flattenHarmonizationEntities(report);
  const fieldThresholdProfiles = collectThresholdProfiles(rows, "field_thresholds");
  const valueThresholdProfiles = collectThresholdProfiles(rows, "value_thresholds");
  if (!rows.length) {
    return <Alert variant="secondary">No harmonization field entries.</Alert>;
  }

  return (
    <Card>
      <Card.Header className="fw-semibold">Harmonization Fields</Card.Header>
      {(fieldThresholdProfiles.length > 0 || valueThresholdProfiles.length > 0) && (
        <Card.Body className="py-2 border-bottom">
          <FieldValueThresholdSummary
            fieldProfiles={fieldThresholdProfiles}
            valueProfiles={valueThresholdProfiles}
          />
        </Card.Body>
      )}
      <div className="table-responsive dq-table-scroll">
        <Table size="sm" hover className="mb-0 align-middle">
          <thead>
            <tr>
              <th>Entity</th>
              <th>Input label</th>
              <th>Output term</th>
              <th>Canonical field</th>
              <th>Changed part</th>
              <th>Status</th>
              <th>Input value</th>
              <th>Harmonized value</th>
              <th>Label check</th>
              <th>Value check</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 80).map((row, index) => (
              <tr key={`${row.entity_id}-${row.canonical_path}-${index}`}>
                <td>
                  <div className="fw-semibold">{row.entity_type}</div>
                  <div className="small text-truncate" style={{ maxWidth: 180 }}>
                    {row.entity_id}
                  </div>
                </td>
                <td>{row.original_label || "-"}</td>
                <td>{row.jsonld_term || "-"}</td>
                <td>{row.canonical_path}</td>
                <td>
                  <Badge bg={isChangedField(row) ? "primary" : "secondary"}>
                    {changeLabel(row)}
                  </Badge>
                </td>
                <td>
                  <Badge bg={statusVariant(row.status)}>{row.status}</Badge>
                </td>
                <td className="dq-json-cell">{prettyJson(row.original_value)}</td>
                <td className="dq-json-cell">{row.normalized_value == null ? "-" : prettyJson(row.normalized_value)}</td>
                <td>{formatMethod(row.field_method || row.method, row.field_confidence ?? row.confidence)}</td>
                <td>{formatMethod(row.value_method, row.value_confidence)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
      {rows.length > 80 && <Card.Footer className="small text-muted">Showing first 80 of {rows.length} entries.</Card.Footer>}
    </Card>
  );
}

function TextConceptTable({ report }) {
  const entries = flattenTextConcepts(report);
  const thresholdProfiles = collectThresholdProfiles(entries, "thresholds");
  if (!entries.length) {
    return null;
  }

  return (
    <Card>
      <Card.Header className="fw-semibold">Text Harmonization</Card.Header>
      {thresholdProfiles.length > 0 && (
        <Card.Body className="py-2 border-bottom">
          <ThresholdSummary label="Text" profiles={thresholdProfiles} />
        </Card.Body>
      )}
      <div className="table-responsive dq-table-scroll">
        <Table size="sm" hover className="mb-0 align-middle">
          <thead>
            <tr>
              <th>Entity</th>
              <th>Field</th>
              <th>Input text</th>
              <th>Status</th>
              <th>Concept</th>
              <th>Method</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => (
              <tr key={`${entry.entity_id}-${entry.field_name}-${index}`}>
                <td>
                  <div>{entry.entity_type}</div>
                  <div className="small text-muted">{entry.entity_id}</div>
                </td>
                <td>{entry.field_name}</td>
                <td>{entry.original_value}</td>
                <td>
                  <Badge bg={entry.status === "normalized" ? "success" : entry.status === "error" ? "danger" : "warning"}>
                    {entry.status}
                  </Badge>
                </td>
                <td>{entry.normalized_value || "-"}</td>
                <td>{formatMethod(entry.method, entry.confidence)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </Card>
  );
}

function AnomalyTable({ report }) {
  const findings = report?.findings || [];
  if (!findings.length) {
    return <Alert variant="success">No anomaly findings.</Alert>;
  }

  return (
    <Card>
      <Card.Header className="fw-semibold">Anomaly Findings</Card.Header>
      <div className="table-responsive dq-table-scroll">
        <Table size="sm" hover className="mb-0 align-middle">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Check</th>
              <th>Entity</th>
              <th>Message</th>
              <th>Observed</th>
              <th>Review</th>
            </tr>
          </thead>
          <tbody>
            {findings.map((finding, index) => (
              <tr key={`${finding.check_id}-${finding.entity_id}-${index}`}>
                <td>
                  <Badge bg={severityVariant(finding.severity)}>{finding.severity}</Badge>
                </td>
                <td>
                  <div className="fw-semibold">{finding.check_id}</div>
                  <div className="small">{finding.category}</div>
                </td>
                <td>
                  <div>{finding.entity_type || "-"}</div>
                  <div className="small text-truncate" style={{ maxWidth: 180 }}>
                    {finding.entity_id || "-"}
                  </div>
                </td>
                <td>{finding.message}</td>
                <td className="dq-json-cell">
                  {typeof finding.observed_value === "undefined" ? "-" : prettyJson(finding.observed_value)}
                </td>
                <td>{finding.review_action || "-"}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </Card>
  );
}

function SummaryModal({ type, result, onHide }) {
  const visible = Boolean(type);
  const findings = result?.anomaly_report?.findings || [];
  const fields = flattenHarmonizationEntities(result?.harmonization_report);
  const entities = Object.values(result?.harmonization_report?.entities || {});
  const harmonizationIssues = flattenHarmonizationIssues(result?.harmonization_report);
  const textConcepts = flattenTextConcepts(result?.harmonization_report);
  const visibleHarmonizationIssues = result?.scope === "service"
    ? nonTextHarmonizationIssues(harmonizationIssues, textConcepts)
    : harmonizationIssues;
  const vocabularyFields = controlledVocabularyFields(result?.harmonization_report);
  const severity = type?.startsWith("severity:") ? type.split(":")[1] : null;
  const filteredFindings = severity ? findings.filter((finding) => finding.severity === severity) : findings;
  const unmappedFields = fields.filter((field) => field.status === "unmapped");
  const changedFields = fields.filter((field) => isChangedField(field));
  const changedFieldThresholdProfiles = collectThresholdProfiles(changedFields, "field_thresholds");
  const changedValueThresholdProfiles = collectThresholdProfiles(changedFields, "value_thresholds");
  const textThresholdProfiles = collectThresholdProfiles(textConcepts, "thresholds");
  const vocabularyThresholdProfiles = collectThresholdProfiles(vocabularyFields, "value_thresholds");

  let title = "Summary";
  if (type === "entities") title = "Entities";
  if (type === "changed-fields") title = "Changed Labels / Values";
  if (type === "unmapped") title = "Unmapped Labels";
  if (type === "harmonization-issues") title = "Harmonization Notes";
  if (type === "text-harmonization") title = "Text Harmonization";
  if (type === "controlled-values") title = "Controlled Vocabulary Values";
  if (type === "findings") title = "Anomaly Findings";
  if (severity) title = `${severity} Findings`;

  return (
    <Modal show={visible} onHide={onHide} size="lg" centered>
      <Modal.Header closeButton>
        <Modal.Title>
          {severity && (
            <Badge bg={severityVariant(severity)} className="me-2">
              {severity}
            </Badge>
          )}
          {title}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {type === "entities" && entities.length > 0 && (
          <div className="d-flex flex-column gap-2">
            {entities.map((entity) => (
              <Card key={entity.entity_id} className="shadow-none">
                <Card.Body>
                  <div className="fw-semibold">{entity.entity_type}</div>
                  <div className="small text-muted">{entity.entity_id}</div>
                  <div className="small mt-1">
                    Fields: {Object.keys(entity.fields || {}).length} · Unmapped: {entity.unmapped_fields?.length || 0} ·
                    Issues: {entity.issues?.length || 0}
                  </div>
                </Card.Body>
              </Card>
            ))}
          </div>
        )}

        {type === "changed-fields" && changedFields.length > 0 && (
          <div className="d-flex flex-column gap-2">
            {(changedFieldThresholdProfiles.length > 0 || changedValueThresholdProfiles.length > 0) && (
              <Alert variant="secondary" className="py-2 mb-0">
                <FieldValueThresholdSummary
                  fieldProfiles={changedFieldThresholdProfiles}
                  valueProfiles={changedValueThresholdProfiles}
                />
              </Alert>
            )}
            {changedFields.map((field, index) => {
              const changes = fieldChangeTypes(field);
              return (
                <Card key={`${field.entity_id}-${field.canonical_path}-${index}`} className="shadow-none">
                  <Card.Body>
                    <div className="d-flex flex-column flex-sm-row justify-content-between align-items-start gap-2 mb-3">
                      <div>
                        <div className="fw-semibold">{field.jsonld_term || field.canonical_path}</div>
                        <div className="small text-muted">
                          {field.entity_type} · {field.entity_id}
                        </div>
                      </div>
                      <Badge bg="primary">{changeLabel(field)}</Badge>
                    </div>

                    {changes.includes("label") && (
                      <Row className="g-2 mb-3">
                        <Col xs={12} sm={6}>
                          <div className="small text-muted">Input label</div>
                          <div className="dq-diff-value">{field.original_label || "-"}</div>
                        </Col>
                        <Col xs={12} sm={6}>
                          <div className="small text-muted">Output term</div>
                          <div className="dq-diff-value">{field.jsonld_term || "-"}</div>
                        </Col>
                      </Row>
                    )}

                    {changes.includes("value") && (
                      <Row className="g-2 mb-3">
                        <Col xs={12} sm={6}>
                          <div className="small text-muted">Input value</div>
                          <div className="dq-json-cell dq-diff-value">
                            {isMeasurementObject(field.original_value)
                              ? prettyJson(field.original_value.value)
                              : prettyJson(field.original_value)}
                          </div>
                        </Col>
                        <Col xs={12} sm={6}>
                          <div className="small text-muted">Harmonized value</div>
                          <div className="dq-json-cell dq-diff-value">
                            {field.normalized_value == null
                              ? "-"
                              : prettyJson(isMeasurementObject(field.normalized_value)
                                ? field.normalized_value.value
                                : field.normalized_value)}
                          </div>
                        </Col>
                      </Row>
                    )}

                    {changes.includes("unit") && (
                      <Row className="g-2 mb-3">
                        <Col xs={12} sm={6}>
                          <div className="small text-muted">Input unit</div>
                          <div className="dq-diff-value">{field.original_value?.unit || "-"}</div>
                        </Col>
                        <Col xs={12} sm={6}>
                          <div className="small text-muted">Harmonized unit</div>
                          <div className="dq-diff-value">{field.normalized_value?.unit || "-"}</div>
                        </Col>
                      </Row>
                    )}

                    <div className="small text-muted">{field.canonical_path}</div>
                    <div className="small mt-1">
                      Label check: <span className="fw-semibold">{formatMethod(field.field_method || field.method, field.field_confidence ?? field.confidence)}</span>
                      {" · "}
                      Value check: <span className="fw-semibold">{formatMethod(field.value_method, field.value_confidence)}</span>
                    </div>
                  </Card.Body>
                </Card>
              );
            })}
          </div>
        )}

        {type === "unmapped" && (
          unmappedFields.length ? (
            <div className="d-flex flex-column gap-2">
              {unmappedFields.map((field, index) => {
                const matchingIssues = harmonizationIssues.filter(
                  (issue) => issue.entity_id === field.entity_id && issue.field_label === field.original_label,
                );
                return (
                  <Card key={`${field.entity_id}-${field.original_label}-${index}`} className="shadow-none">
                    <Card.Body>
                      <div className="fw-semibold">{field.original_label || field.canonical_path}</div>
                      <div className="small text-muted">
                        {field.entity_type} · {field.entity_id}
                      </div>
                      <div className="dq-json-cell mt-2">{prettyJson(field.original_value)}</div>
                      {matchingIssues.length ? (
                        matchingIssues.map((issue, issueIndex) => (
                          <Alert key={issueIndex} variant={severityVariant(issue.severity)} className="py-2 mt-2 mb-0">
                            {issue.message}
                            <GuidancePanel guidance={issue.guidance} />
                          </Alert>
                        ))
                      ) : (
                        <Alert variant="secondary" className="py-2 mt-2 mb-0">
                          No mapping candidate above the review threshold.
                          <GuidancePanel guidance={field.guidance} />
                        </Alert>
                      )}
                    </Card.Body>
                  </Card>
                );
              })}
            </div>
          ) : (
            <Alert variant="success" className="mb-0">
              No unmapped input labels.
            </Alert>
          )
        )}

        {type === "harmonization-issues" && (
          visibleHarmonizationIssues.length ? (
            <div className="d-flex flex-column gap-2">
              {visibleHarmonizationIssues.map((issue, index) => (
                <Card key={`${issue.entity_id}-${issue.field_label}-${index}`} className="shadow-none">
                  <Card.Body>
                    <div className="d-flex justify-content-between gap-3 mb-1">
                      <div className="fw-semibold">{issue.field_label || "Global issue"}</div>
                      <Badge bg={severityVariant(issue.severity)}>{issue.severity}</Badge>
                    </div>
                    <div>{issue.message}</div>
                    <div className="small text-muted mt-1">
                      {issue.entity_type || "-"} · {issue.entity_id || "-"}
                    </div>
                    <GuidancePanel guidance={issue.guidance} />
                  </Card.Body>
                </Card>
              ))}
            </div>
          ) : (
            <Alert variant="success" className="mb-0">
              No harmonization issues.
            </Alert>
          )
        )}

        {type === "text-harmonization" && (
          textConcepts.length ? (
            <div className="d-flex flex-column gap-2">
              {textThresholdProfiles.length > 0 && (
                <Alert variant="secondary" className="py-2 mb-0">
                  <ThresholdSummary label="Text" profiles={textThresholdProfiles} />
                </Alert>
              )}
              {textConcepts.map((entry, index) => {
                const notes = textEntryIssues(entry, harmonizationIssues);
                return (
                  <Card key={`${entry.entity_id}-${entry.field_name}-${index}`} className="shadow-none">
                    <Card.Body>
                      <div className="d-flex justify-content-between gap-3 mb-1">
                        <div className="fw-semibold">{entry.field_name}</div>
                        <Badge
                          bg={entry.status === "normalized" ? "success" : entry.status === "error" ? "danger" : "warning"}
                        >
                          {entry.status}
                        </Badge>
                      </div>
                      <div className="mb-2">{entry.original_value}</div>
                      <div className="small text-muted">
                        {entry.entity_type} · {entry.entity_id}
                      </div>
                      {entry.normalized_value && (
                        <div className="small mt-1">
                          Concept: <span className="fw-semibold">{entry.normalized_value}</span> · Method:{" "}
                          {formatMethod(entry.method, entry.confidence)}
                        </div>
                      )}
                      {entry.candidates?.length > 0 && (
                        <div className="small mt-1">
                          Candidates:{" "}
                          {entry.candidates
                            .map((candidate) => formatMethod(candidate.concept_id, candidate.confidence))
                            .join(", ")}
                        </div>
                      )}
                      {notes.map((issue, issueIndex) => (
                        <Alert
                          key={`${entry.entity_id}-${entry.field_name}-note-${issueIndex}`}
                          variant={severityVariant(issue.severity)}
                          className="py-2 mt-2 mb-0"
                        >
                          {issue.message}
                        </Alert>
                      ))}
                    </Card.Body>
                  </Card>
                );
              })}
            </div>
          ) : (
            <Alert variant="secondary" className="mb-0">
              No service-text concept entries.
            </Alert>
          )
        )}

        {type === "controlled-values" && (
          vocabularyFields.length ? (
            <div className="d-flex flex-column gap-2">
              {vocabularyThresholdProfiles.length > 0 && (
                <Alert variant="secondary" className="py-2 mb-0">
                  <ThresholdSummary label="Value" profiles={vocabularyThresholdProfiles} />
                </Alert>
              )}
              {vocabularyFields.map((field, index) => (
                <Card key={`${field.entity_id}-${field.canonical_path}-${index}`} className="shadow-none">
                  <Card.Body>
                    <div className="d-flex flex-column flex-sm-row justify-content-between align-items-start gap-2 mb-2">
                      <div>
                        <div className="fw-semibold text-break">{field.canonical_path}</div>
                        <div className="small text-muted">Input label: {field.original_label || "-"}</div>
                      </div>
                      <Badge className="flex-shrink-0" bg={statusVariant(field.status)}>{field.status}</Badge>
                    </div>
                    <div className="small text-muted">Input value</div>
                    <div className="dq-json-cell mb-2">{prettyJson(field.original_value)}</div>
                    <div className="small text-muted">Harmonized value</div>
                    <div className="dq-json-cell mb-2">
                      {field.normalized_value == null ? "-" : prettyJson(field.normalized_value)}
                    </div>
                    <div className="small">
                      Value check: <span className="fw-semibold">{formatMethod(field.value_method, field.value_confidence)}</span>
                    </div>
                    <GuidancePanel guidance={field.guidance} />
                  </Card.Body>
                </Card>
              ))}
            </div>
          ) : (
            <Alert variant="secondary" className="mb-0">
              No controlled-vocabulary values.
            </Alert>
          )
        )}

        {(type === "findings" || severity) && (
          filteredFindings.length ? (
            <>
              {type === "findings" && (
                <div className="d-flex flex-wrap gap-2 mb-3">
                  {Object.entries(result?.anomaly_report?.summary?.severity_counts || {}).map(([itemSeverity, count]) => (
                    <Badge key={itemSeverity} bg={severityVariant(itemSeverity)}>
                      {itemSeverity} {count}
                    </Badge>
                  ))}
                </div>
              )}
              <div className="d-flex flex-column gap-2">
                {filteredFindings.map((finding, index) => (
                  <Card key={`${finding.check_id}-${finding.entity_id}-${index}`} className="shadow-none">
                    <Card.Body>
                      <div className="d-flex justify-content-between gap-3 mb-1">
                        <div className="fw-semibold">{finding.check_id}</div>
                        <div className="d-flex gap-2">
                          <Badge bg={severityVariant(finding.severity)}>{finding.severity}</Badge>
                          <Badge bg="secondary">{finding.category}</Badge>
                        </div>
                      </div>
                      <div className="mb-2">{finding.message}</div>
                      <div className="small text-muted">
                        {finding.entity_type || "-"} · {finding.entity_id || "-"}
                      </div>
                      {finding.review_action && <div className="small mt-1">Review: {finding.review_action}</div>}
                    </Card.Body>
                  </Card>
                ))}
              </div>
            </>
          ) : (
            <Alert variant="secondary" className="mb-0">
              No findings.
            </Alert>
          )
        )}

        {type === "entities" && !entities.length && (
          <Alert variant="secondary" className="mb-0">
            No entities.
          </Alert>
        )}
        {type === "changed-fields" && !changedFields.length && <Alert variant="secondary">No changed fields.</Alert>}
      </Modal.Body>
    </Modal>
  );
}

export default function DataQualityView() {
  const [scope, setScope] = useState("auto");
  const [mode, setMode] = useState("both");
  const [text, setText] = useState(EMPTY_INPUT);
  const [fileName, setFileName] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [result, setResult] = useState(null);
  const [examples, setExamples] = useState([]);
  const [examplesErr, setExamplesErr] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exampleLoading, setExampleLoading] = useState("");
  const [selectedSummary, setSelectedSummary] = useState(null);
  const [showIsolationConfig, setShowIsolationConfig] = useState(false);
  const [isolationEstimators, setIsolationEstimators] = useState("100");
  const [isolationContamination, setIsolationContamination] = useState("0.15");
  const [isolationMaxSamples, setIsolationMaxSamples] = useState("");
  const [isolationRandomState, setIsolationRandomState] = useState("42");
  const [isolationReferenceCsvType, setIsolationReferenceCsvType] = useState("product");
  const [isolationReferenceRows, setIsolationReferenceRows] = useState([]);
  const [isolationReferenceFileName, setIsolationReferenceFileName] = useState("");
  const [isolationReferenceErr, setIsolationReferenceErr] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    let active = true;
    api
      .listDataQualityExamples()
      .then((data) => {
        if (active) setExamples(Array.isArray(data?.examples) ? data.examples : []);
      })
      .catch((error) => {
        if (active) setExamplesErr(error?.message || String(error));
      });
    return () => {
      active = false;
    };
  }, []);

  const parsedPreview = useMemo(() => {
    try {
      return { ok: true, value: JSON.parse(text) };
    } catch (error) {
      return { ok: false, message: error?.message || String(error) };
    }
  }, [text]);

  async function readFile(file) {
    if (!file) return;
    setFileName(file.name);
    setText(await file.text());
    setResult(null);
    setErr(null);
  }

  function parseDelimitedLine(line, delimiter) {
    const values = [];
    let current = "";
    let inQuotes = false;
    for (let index = 0; index < line.length; index += 1) {
      const char = line[index];
      const next = line[index + 1];
      if (char === '"' && inQuotes && next === '"') {
        current += '"';
        index += 1;
      } else if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === delimiter && !inQuotes) {
        values.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    values.push(current.trim());
    return values;
  }

  function detectDelimiter(headerLine) {
    const candidates = [",", ";", "\t"];
    return candidates
      .map((delimiter) => ({ delimiter, columns: parseDelimitedLine(headerLine, delimiter).length }))
      .sort((left, right) => right.columns - left.columns)[0].delimiter;
  }

  function safeRatio(numerator, denominator) {
    if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator <= 0) return null;
    return Number((numerator / denominator).toFixed(6));
  }

  function numericCell(row, column, rowNumber, { required = true } = {}) {
    const rawValue = row[column];
    if (rawValue == null || rawValue === "") {
      if (required) throw new Error(`CSV row ${rowNumber}, column "${column}" is required.`);
      return null;
    }
    const numericValue = Number(rawValue);
    if (!Number.isFinite(numericValue)) {
      throw new Error(`CSV row ${rowNumber}, column "${column}" is not numeric.`);
    }
    return numericValue;
  }

  function textCell(row, column, rowNumber) {
    const rawValue = row[column];
    if (rawValue == null || rawValue === "") {
      throw new Error(`CSV row ${rowNumber}, column "${column}" is required.`);
    }
    return rawValue;
  }

  function requireColumns(headers, columns, csvTypeLabel) {
    const missing = columns.filter((column) => !headers.includes(column));
    if (missing.length) {
      throw new Error(`${csvTypeLabel} CSV is missing required columns: ${missing.join(", ")}.`);
    }
  }

  function unitCompatibilityValue(activityUnit, factorUnit) {
    const expected = {
      kWh: "kgCO2e/kWh",
      kg: "kgCO2e/kg",
      km: "kgCO2e/km",
    }[activityUnit];
    if (!expected) return null;
    return factorUnit === expected ? 1.0 : 0.0;
  }

  function productReferenceRow(row, rowIndex) {
    const rowNumber = rowIndex + 2;
    const operating = numericCell(row, "operatingHRS", rowNumber);
    const brewing = numericCell(row, "brewingCount", rowNumber);
    const cleaning = numericCell(row, "cleaningCount", rowNumber);
    const chalk = numericCell(row, "chalkCount", rowNumber);
    const grinding = numericCell(row, "coffeeGrindingCount", rowNumber);
    const productWeight = numericCell(row, "product_weightGRM", rowNumber, { required: false });
    const activePartWeight = numericCell(row, "active_part_weightGRM", rowNumber, { required: false });
    const materialRatio = numericCell(row, "max_material_weight_to_part_weight", rowNumber, { required: false });
    const entityId = textCell(row, "entity_id", rowNumber);
    const features = {
      operatingHRS: operating,
      brewingCount: brewing,
      cleaningCount: cleaning,
      chalkCount: chalk,
      coffeeGrindingCount: grinding,
      cleaning_to_brewing_ratio: safeRatio(cleaning, brewing),
      chalk_to_brewing_ratio: safeRatio(chalk, brewing),
      grinding_to_brewing_ratio: safeRatio(grinding, brewing),
      brews_per_operating_hour: safeRatio(brewing, operating),
      max_material_weight_to_part_weight: materialRatio,
      product_weightGRM: productWeight,
      active_part_weightGRM: activePartWeight,
      active_part_weight_to_product_weight: safeRatio(activePartWeight, productWeight),
    };

    return {
      scope_name: "product",
      feature_set: "product_usage_graph",
      entity_id: entityId,
      entity_type: "UploadedReferenceRow",
      features: Object.fromEntries(Object.entries(features).filter(([, value]) => value != null)),
      source_entity_ids: [],
      missing_features: [],
      evidence: { upload_format: "product_raw_csv" },
    };
  }

  function emissionReferenceRow(row, rowIndex) {
    const rowNumber = rowIndex + 2;
    const quantity = numericCell(row, "quantity", rowNumber);
    const entityId = textCell(row, "entity_id", rowNumber);
    const activityUnit = textCell(row, "activity_unit", rowNumber);
    const factorUnit = textCell(row, "factor_unit", rowNumber);
    const factorValue = numericCell(row, "factor_value", rowNumber);
    const reported = numericCell(row, "reported_emissions", rowNumber);
    const expected = quantity * factorValue;
    const absoluteDeviation = Math.abs(reported - expected);
    const relativeDeviation = safeRatio(absoluteDeviation, Math.abs(expected));
    const features = {
      quantity,
      factor_value: factorValue,
      reported_emissions: reported,
      expected_emissions: Number(expected.toFixed(6)),
      absolute_calculation_deviation: Number(absoluteDeviation.toFixed(6)),
      relative_calculation_deviation: relativeDeviation,
      reported_emissions_per_quantity: safeRatio(reported, quantity),
      unit_compatible: unitCompatibilityValue(activityUnit, factorUnit),
    };

    return {
      scope_name: "emission",
      feature_set: "emission_calculation_intensity",
      entity_id: entityId,
      entity_type: "UploadedReferenceRow",
      features: Object.fromEntries(Object.entries(features).filter(([, value]) => value != null)),
      source_entity_ids: [],
      missing_features: [],
      evidence: {
        upload_format: "emission_raw_csv",
        activity_unit: activityUnit,
        factor_unit: factorUnit,
      },
    };
  }

  function parseReferenceCsv(content, csvType) {
    const lines = content
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"));
    if (lines.length < 2) {
      throw new Error("CSV reference data needs a header and at least one data row.");
    }

    const delimiter = detectDelimiter(lines[0]);
    const headers = parseDelimitedLine(lines[0], delimiter);
    if (csvType === "product") {
      requireColumns(
        headers,
        ["entity_id", "operatingHRS", "brewingCount", "cleaningCount", "chalkCount", "coffeeGrindingCount"],
        "Product raw usage",
      );
    } else {
      requireColumns(
        headers,
        ["entity_id", "quantity", "activity_unit", "factor_value", "factor_unit", "reported_emissions"],
        "Emission raw calculation",
      );
    }

    return lines.slice(1).map((line, rowIndex) => {
      const values = parseDelimitedLine(line, delimiter);
      const row = Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
      return csvType === "product"
        ? productReferenceRow(row, rowIndex)
        : emissionReferenceRow(row, rowIndex);
    });
  }

  async function readIsolationReferenceFile(file) {
    if (!file) return;
    setIsolationReferenceErr(null);
    setIsolationReferenceFileName(file.name);
    try {
      if (!file.name.toLowerCase().endsWith(".csv")) {
        throw new Error("Reference data upload accepts CSV files only.");
      }
      const normalizedRows = parseReferenceCsv(await file.text(), isolationReferenceCsvType);
      setIsolationReferenceRows(normalizedRows);
      setResult(null);
    } catch (error) {
      setIsolationReferenceRows([]);
      setIsolationReferenceErr(error?.message || String(error));
    }
  }

  function isolationOptionsPayload() {
    const nEstimators = Number(isolationEstimators);
    const contamination = Number(isolationContamination);
    const maxSamples = isolationMaxSamples.trim() ? Number(isolationMaxSamples) : null;
    const randomState = Number(isolationRandomState);

    if (!Number.isInteger(nEstimators) || nEstimators < 10 || nEstimators > 1000) {
      throw new Error("Isolation Forest n_estimators must be an integer between 10 and 1000.");
    }
    if (!Number.isFinite(contamination) || contamination <= 0 || contamination > 0.5) {
      throw new Error("Isolation Forest contamination must be greater than 0 and at most 0.5.");
    }
    if (maxSamples !== null && (!Number.isFinite(maxSamples) || maxSamples <= 0)) {
      throw new Error("Isolation Forest max_samples must be empty or greater than 0.");
    }
    if (!Number.isInteger(randomState)) {
      throw new Error("Isolation Forest random_state must be an integer.");
    }

    return {
      isolation_forest: {
        enabled: true,
        n_estimators: nEstimators,
        contamination,
        max_samples: maxSamples,
        random_state: randomState,
        reference_rows: isolationReferenceRows,
        reference_description: isolationReferenceRows.length
          ? `Uploaded reference feature rows from ${isolationReferenceFileName || "local file"}.`
          : null,
      },
    };
  }

  function handleDrop(event) {
    event.preventDefault();
    setIsDragging(false);
    readFile(event.dataTransfer.files?.[0]);
  }

  async function runCheck() {
    setErr(null);
    setResult(null);

    let document;
    try {
      document = JSON.parse(text);
    } catch (error) {
      setErr(`Invalid JSON: ${error?.message || String(error)}`);
      return;
    }

    setLoading(true);
    try {
      const response = await api.runDataQuality({
        scope,
        mode,
        document,
        anomaly_options: isolationOptionsPayload(),
      });
      setResult(response);
    } catch (error) {
      setErr(error?.message || String(error));
    } finally {
      setLoading(false);
    }
  }

  async function loadExample(name) {
    setExampleLoading(name);
    setErr(null);
    setResult(null);
    try {
      const example = await api.getDataQualityExample(name);
      setScope(example.scope);
      setMode("both");
      setFileName(`${example.name}.json`);
      setText(prettyJson(example.document));
    } catch (error) {
      setErr(error?.message || String(error));
    } finally {
      setExampleLoading("");
    }
  }

  function downloadCleanJson() {
    if (!result?.data) return;
    const blob = new Blob([prettyJson(result.data)], { type: "application/ld+json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "clean-jsonld.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Container className="py-4">
      <Row className="align-items-center mb-3">
        <Col>
          <h2 className="mb-0">Data Quality</h2>
          <div className="text-muted">Run harmonization and anomaly checks on an external JSON-LD document.</div>
        </Col>
        <Col xs="auto">
          <Badge bg={result?.has_errors ? "danger" : result ? "success" : "secondary"}>
            {result ? (result.has_errors ? "Review required" : "Checked") : "Stateless"}
          </Badge>
        </Col>
      </Row>

      <Row className="g-3">
        <Col xs={12} lg={5}>
          <Card>
            <Card.Header className="fw-semibold">Input</Card.Header>
            <Card.Body>
              <Row className="g-3 mb-3">
                <Col xs={12} md={6}>
                  <Form.Label>Scope</Form.Label>
                  <Form.Select value={scope} onChange={(event) => setScope(event.target.value)}>
                    <option value="auto">Auto-detect</option>
                    <option value="product">Product</option>
                    <option value="emission">Emission</option>
                    <option value="service">Service</option>
                  </Form.Select>
                </Col>
                <Col xs={12} md={6}>
                  <Form.Label>Mode</Form.Label>
                  <Form.Select value={mode} onChange={(event) => setMode(event.target.value)}>
                    <option value="both">Harmonization + Anomaly</option>
                    <option value="harmonization">Harmonization</option>
                    <option value="anomaly">Anomaly</option>
                  </Form.Select>
                </Col>
              </Row>

              <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
                <Button
                  variant="outline-secondary"
                  size="sm"
                  onClick={() => setShowIsolationConfig(true)}
                >
                  Isolation Forest configuration
                </Button>
              </div>

              <div className="mb-3">
                <Form.Label>Examples</Form.Label>
                <div className="d-flex flex-wrap gap-2">
                  {examples.map((example) => (
                    <Button
                      key={example.name}
                      size="sm"
                      variant="outline-secondary"
                      disabled={!!exampleLoading}
                      onClick={() => loadExample(example.name)}
                    >
                      {exampleLoading === example.name && <Spinner animation="border" size="sm" className="me-1" />}
                      {example.label}
                    </Button>
                  ))}
                </div>
                {examplesErr && <div className="small text-danger mt-1">Could not load examples: {examplesErr}</div>}
              </div>

              <div
                className={`border rounded p-4 mb-3 text-center ${isDragging ? "border-primary bg-light" : "border-secondary-subtle"}`}
                onDragOver={(event) => {
                  event.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                role="button"
                tabIndex={0}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload size={24} className="mb-2" aria-hidden="true" />
                <div className="fw-semibold">Drop JSON-LD here</div>
                <div className="text-muted small">{fileName || "or choose a local .json/.jsonld file"}</div>
                <Form.Control
                  ref={fileInputRef}
                  type="file"
                  accept=".json,.jsonld,application/json,application/ld+json"
                  className="d-none"
                  onChange={(event) => readFile(event.target.files?.[0])}
                />
              </div>

              <Form.Group className="mb-3">
                <Form.Label className="d-flex align-items-center gap-2">
                  <FileEarmarkCode aria-hidden="true" />
                  JSON-LD
                </Form.Label>
                <Form.Control
                  as="textarea"
                  value={text}
                  rows={16}
                  spellCheck={false}
                  onChange={(event) => {
                    setText(event.target.value);
                    setResult(null);
                    setErr(null);
                  }}
                  style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}
                />
              </Form.Group>

              {!parsedPreview.ok && (
                <Alert variant="warning" className="py-2">
                  Invalid JSON: {parsedPreview.message}
                </Alert>
              )}

              {err && <Alert variant="danger">{err}</Alert>}

              <ButtonGroup>
                <Button onClick={runCheck} disabled={loading || !parsedPreview.ok}>
                  {loading ? <Spinner animation="border" size="sm" className="me-2" /> : <PlayFill className="me-1" />}
                  Run
                </Button>
                <Button variant="outline-primary" disabled={!result?.data} onClick={downloadCleanJson}>
                  <Download className="me-1" aria-hidden="true" />
                  Download clean JSON
                </Button>
                <Button
                  variant="outline-secondary"
                  onClick={() => {
                    setText(EMPTY_INPUT);
                    setFileName("");
                    setResult(null);
                    setErr(null);
                  }}
                >
                  Reset
                </Button>
              </ButtonGroup>
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={7}>
          <SummaryBadges result={result} onBadgeClick={setSelectedSummary} />
          <Tabs defaultActiveKey="clean" className="mb-3">
            <Tab eventKey="overview" title="Overview">
              <Row className="g-3">
                {result?.scope === "service" && (
                  <Col xs={12}>
                    <TextConceptTable report={result?.harmonization_report} />
                  </Col>
                )}
                {result?.scope !== "service" && (
                  <Col xs={12}>
                    <HarmonizationTable report={result?.harmonization_report} />
                  </Col>
                )}
                <Col xs={12}>
                  <AnomalyTable report={result?.anomaly_report} />
                </Col>
              </Row>
            </Tab>
            <Tab eventKey="clean" title="Clean JSON">
              <JsonPanel title="Clean JSON-LD" value={result?.data} />
            </Tab>
            <Tab eventKey="harmonization" title="Harmonization Report">
              <JsonPanel title="Harmonization Report" value={result?.harmonization_report} />
            </Tab>
            <Tab eventKey="anomaly" title="Anomaly Report">
              <JsonPanel title="Anomaly Report" value={result?.anomaly_report} />
            </Tab>
            <Tab eventKey="full" title="Full Response">
              <JsonPanel title="Full Response" value={result} />
            </Tab>
          </Tabs>
        </Col>
      </Row>

      <Modal show={showIsolationConfig} onHide={() => setShowIsolationConfig(false)} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title>Isolation Forest Configuration</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <div className="mb-3">
            <div>
              <div className="fw-semibold">ML anomaly layer</div>
              <div className="small text-muted">
                Configure the local Isolation Forest check for product/emission feature rows.
              </div>
            </div>
          </div>

          <Row className="g-3">
            <Col xs={12} md={6} lg={3}>
              <Form.Label className="small mb-1">n_estimators</Form.Label>
              <Form.Control
                size="sm"
                type="number"
                min="10"
                max="1000"
                value={isolationEstimators}
                onChange={(event) => {
                  setIsolationEstimators(event.target.value);
                  setResult(null);
                }}
              />
              <div className="small text-muted">Number of trees in the forest.</div>
            </Col>
            <Col xs={12} md={6} lg={3}>
              <Form.Label className="small mb-1">contamination</Form.Label>
              <Form.Control
                size="sm"
                type="number"
                min="0.001"
                max="0.5"
                step="0.01"
                value={isolationContamination}
                onChange={(event) => {
                  setIsolationContamination(event.target.value);
                  setResult(null);
                }}
              />
              <div className="small text-muted">Expected outlier share in the reference data.</div>
            </Col>
            <Col xs={12} md={6} lg={3}>
              <Form.Label className="small mb-1">max_samples</Form.Label>
              <Form.Control
                size="sm"
                type="number"
                min="0.001"
                step="1"
                placeholder="default"
                value={isolationMaxSamples}
                onChange={(event) => {
                  setIsolationMaxSamples(event.target.value);
                  setResult(null);
                }}
              />
              <div className="small text-muted">Empty keeps the built-in default.</div>
            </Col>
            <Col xs={12} md={6} lg={3}>
              <Form.Label className="small mb-1">random_state</Form.Label>
              <Form.Control
                size="sm"
                type="number"
                step="1"
                value={isolationRandomState}
                onChange={(event) => {
                  setIsolationRandomState(event.target.value);
                  setResult(null);
                }}
              />
              <div className="small text-muted">Reproducibility seed for repeated runs.</div>
            </Col>
          </Row>

          <div className="border-top pt-3 mt-3">
            <Form.Group className="mb-3">
              <Form.Label className="small mb-1">Reference CSV type</Form.Label>
              <Form.Select
                size="sm"
                value={isolationReferenceCsvType}
                onChange={(event) => {
                  setIsolationReferenceCsvType(event.target.value);
                  setIsolationReferenceRows([]);
                  setIsolationReferenceFileName("");
                  setIsolationReferenceErr(null);
                  setResult(null);
                }}
                style={{ maxWidth: 320 }}
              >
                <option value="product">Product raw usage CSV</option>
                <option value="emission">Emission raw calculation CSV</option>
              </Form.Select>
            </Form.Group>

            <Alert variant="secondary" className="py-2">
              <div className="fw-semibold small">Expected clean CSV format</div>
              {isolationReferenceCsvType === "product" ? (
                <div className="small">
                  Required columns: <code>entity_id</code>, <code>operatingHRS</code>, <code>brewingCount</code>,{" "}
                  <code>cleaningCount</code>, <code>chalkCount</code>, <code>coffeeGrindingCount</code>.
                  Optional columns: <code>product_weightGRM</code>, <code>active_part_weightGRM</code>,{" "}
                  <code>max_material_weight_to_part_weight</code>. The system derives product usage ratios and
                  product/part weight ratios for the Isolation Forest feature row.
                </div>
              ) : (
                <div className="small">
                  Required columns: <code>entity_id</code>, <code>quantity</code>, <code>activity_unit</code>,{" "}
                  <code>factor_value</code>, <code>factor_unit</code>, <code>reported_emissions</code>.
                  The system derives expected emissions, calculation deviation, emission intensity, and deterministic
                  unit compatibility for the Isolation Forest feature row.
                </div>
              )}
              <div className="small text-muted mt-1">
                Column names and units must already be model-conform. This upload does not perform label, enum, or unit
                harmonization.
              </div>
            </Alert>

            <Form.Label className="small mb-1">Reference data CSV</Form.Label>
            <div className="d-flex flex-wrap align-items-center gap-2">
              <Form.Control
                size="sm"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => readIsolationReferenceFile(event.target.files?.[0])}
                style={{ maxWidth: 320 }}
              />
              <Badge bg={isolationReferenceRows.length ? "info" : "secondary"}>
                {isolationReferenceRows.length
                  ? `${isolationReferenceRows.length} uploaded rows`
                  : "No CSV uploaded"}
              </Badge>
              {isolationReferenceRows.length > 0 && (
                <Button
                  size="sm"
                  variant="outline-secondary"
                  onClick={() => {
                    setIsolationReferenceRows([]);
                    setIsolationReferenceFileName("");
                    setIsolationReferenceErr(null);
                    setResult(null);
                  }}
                >
                  Clear
                </Button>
              )}
            </div>
            <div className="small text-muted mt-1">
              Uploaded data is converted into internal feature rows and used only for the current stateless run.
            </div>
            {isolationReferenceErr && (
              <div className="small text-danger mt-1">Reference data error: {isolationReferenceErr}</div>
            )}
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowIsolationConfig(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>

      <SummaryModal type={selectedSummary} result={result} onHide={() => setSelectedSummary(null)} />
    </Container>
  );
}
