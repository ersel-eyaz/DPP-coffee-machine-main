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
        <pre className="m-0 p-3 bg-light overflow-auto" style={{ minHeight: 320, maxHeight: 560, fontSize: "0.84rem" }}>
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

function formatMethod(method, confidence) {
  if (!method) return "-";
  return typeof confidence === "number" ? `${method} (${confidence.toFixed(2)})` : method;
}

function flattenHarmonizationIssues(report) {
  const issues = [...(report?.global_issues || [])];
  for (const entity of Object.values(report?.entities || {})) {
    issues.push(...(entity.issues || []));
  }
  return issues;
}

function SummaryBadges({ result, onBadgeClick }) {
  const harmonization = result?.harmonization_report?.summary;
  const anomaly = result?.anomaly_report?.summary;
  const fields = flattenHarmonizationEntities(result?.harmonization_report);
  const changedFields = fields.filter((field) => isChangedField(field));
  const harmonizationIssues = flattenHarmonizationIssues(result?.harmonization_report);
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
          <Col xs="auto">
            <Badge
              as="button"
              type="button"
              className="dq-summary-badge"
              bg="secondary"
              title="Show fields changed by harmonization"
              onClick={() => onBadgeClick?.("changed-fields")}
            >
              Changed fields {changedFields.length}
            </Badge>
          </Col>
          <Col xs="auto">
            <Badge
              as="button"
              type="button"
              className="dq-summary-badge"
              bg={harmonization.unmapped_fields_total ? "warning" : "success"}
              title="Show unmapped fields"
              onClick={() => onBadgeClick?.("unmapped")}
            >
              Unmapped {harmonization.unmapped_fields_total ?? 0}
            </Badge>
          </Col>
          <Col xs="auto">
            <Badge
              as="button"
              type="button"
              className="dq-summary-badge"
              bg={harmonizationIssues.length ? "warning" : "success"}
              title="Show harmonization issues and candidate decisions"
              onClick={() => onBadgeClick?.("harmonization-issues")}
            >
              Harmonization notes {harmonizationIssues.length}
            </Badge>
          </Col>
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

function isChangedField(field) {
  if (field.status === "unmapped") return false;
  if (field.status && field.status !== "mapped") return true;
  if (field.value_method) return true;
  if (field.normalized_value === undefined) return false;
  return stableJson(field.original_value) !== stableJson(field.normalized_value);
}

function HarmonizationTable({ report }) {
  const rows = flattenHarmonizationEntities(report);
  if (!rows.length) {
    return <Alert variant="secondary">No harmonization field entries.</Alert>;
  }

  return (
    <Card>
      <Card.Header className="fw-semibold">Harmonization Fields</Card.Header>
      <div className="table-responsive">
        <Table size="sm" hover className="mb-0 align-middle">
          <thead>
            <tr>
              <th>Entity</th>
              <th>Field</th>
              <th>Changed</th>
              <th>Status</th>
              <th>Original</th>
              <th>Normalized</th>
              <th>Field method</th>
              <th>Value method</th>
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
                <td>{row.canonical_path}</td>
                <td>
                  <Badge bg={isChangedField(row) ? "primary" : "secondary"}>
                    {isChangedField(row) ? "yes" : "no"}
                  </Badge>
                </td>
                <td>
                  <Badge bg={row.status === "unmapped" ? "warning" : "success"}>{row.status}</Badge>
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

function AnomalyTable({ report }) {
  const findings = report?.findings || [];
  if (!findings.length) {
    return <Alert variant="success">No anomaly findings.</Alert>;
  }

  return (
    <Card>
      <Card.Header className="fw-semibold">Anomaly Findings</Card.Header>
      <div className="table-responsive">
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
  const severity = type?.startsWith("severity:") ? type.split(":")[1] : null;
  const filteredFindings = severity ? findings.filter((finding) => finding.severity === severity) : findings;
  const unmappedFields = fields.filter((field) => field.status === "unmapped");
  const changedFields = fields.filter((field) => isChangedField(field));

  let title = "Summary";
  if (type === "entities") title = "Entities";
  if (type === "changed-fields") title = "Changed Fields";
  if (type === "unmapped") title = "Unmapped Fields";
  if (type === "harmonization-issues") title = "Harmonization Notes";
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
          <div className="table-responsive">
            <Table size="sm" hover className="mb-0 align-middle">
              <thead>
                <tr>
                  <th>Entity</th>
                  <th>Field</th>
                  <th>Status</th>
                  <th>Field method</th>
                  <th>Value method</th>
                </tr>
              </thead>
              <tbody>
                {changedFields.map((field, index) => (
                  <tr key={`${field.entity_id}-${field.canonical_path}-${index}`}>
                    <td>
                      <div>{field.entity_type}</div>
                      <div className="small text-muted">{field.entity_id}</div>
                    </td>
                    <td>{field.canonical_path}</td>
                    <td>
                      <Badge bg={field.status === "unmapped" ? "warning" : "success"}>{field.status}</Badge>
                    </td>
                    <td>{formatMethod(field.field_method || field.method, field.field_confidence ?? field.confidence)}</td>
                    <td>{formatMethod(field.value_method, field.value_confidence)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        )}

        {type === "unmapped" && (
          unmappedFields.length ? (
            <div className="d-flex flex-column gap-2">
              {unmappedFields.map((field, index) => (
                <Card key={`${field.entity_id}-${field.original_label}-${index}`} className="shadow-none">
                  <Card.Body>
                    <div className="fw-semibold">{field.original_label || field.canonical_path}</div>
                    <div className="small text-muted">
                      {field.entity_type} · {field.entity_id}
                    </div>
                    <div className="dq-json-cell mt-2">{prettyJson(field.original_value)}</div>
                    {harmonizationIssues.filter(
                      (issue) => issue.entity_id === field.entity_id && issue.field_label === field.original_label,
                    ).length ? (
                      harmonizationIssues
                        .filter((issue) => issue.entity_id === field.entity_id && issue.field_label === field.original_label)
                        .map((issue, issueIndex) => (
                          <Alert key={issueIndex} variant={severityVariant(issue.severity)} className="py-2 mt-2 mb-0">
                            {issue.message}
                          </Alert>
                        ))
                    ) : (
                      <Alert variant="secondary" className="py-2 mt-2 mb-0">
                        No mapping candidate above the review threshold.
                      </Alert>
                    )}
                  </Card.Body>
                </Card>
              ))}
            </div>
          ) : (
            <Alert variant="success" className="mb-0">
              No unmapped fields.
            </Alert>
          )
        )}

        {type === "harmonization-issues" && (
          harmonizationIssues.length ? (
            <div className="d-flex flex-column gap-2">
              {harmonizationIssues.map((issue, index) => (
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
  const [scope, setScope] = useState("product");
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
      const response = await api.runDataQuality({ scope, mode, document });
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
                <Col xs={12}>
                  <HarmonizationTable report={result?.harmonization_report} />
                </Col>
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

      <SummaryModal type={selectedSummary} result={result} onHide={() => setSelectedSummary(null)} />
    </Container>
  );
}
