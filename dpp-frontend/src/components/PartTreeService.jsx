import React, { useEffect, useMemo, useState } from "react";
import { Button, Card, Spinner, Table } from "react-bootstrap";

import { api } from "../api";
import { FIELD_HELP } from "../content/fieldHelp";
import InfoTip from "../shared/InfoTip";

export default function PartTreeService({
  rootParts = [],
  topPartId,
  perPartStats = {},
  perPartMtbf = {},
  showModular = true,
  topHasFail = false,
  instanceId,
  onRefresh = () => {},
  refreshSeq = 0,
}) {
  if (!Array.isArray(rootParts) || rootParts.length === 0) {
    return <div className="text-muted">No subparts.</div>;
  }

  return (
    <div className="d-flex flex-column gap-3">
      {topPartId ? (
        <ServicePartNode
          node={{ id: topPartId, name: "Product", isModular: false, hasFailstate: topHasFail }}
          perPartStats={perPartStats}
          perPartMtbf={perPartMtbf}
          showModular={showModular}
          isTop
          instanceId={instanceId}
          onRefresh={onRefresh}
          refreshSeq={refreshSeq}
        >
          <div className="d-flex flex-column gap-3 mt-2">
            {rootParts.map((part) => (
              <ServicePartNode
                key={part.id}
                node={part}
                perPartStats={perPartStats}
                perPartMtbf={perPartMtbf}
                showModular={showModular}
                instanceId={instanceId}
                onRefresh={onRefresh}
                refreshSeq={refreshSeq}
              />
            ))}
          </div>
        </ServicePartNode>
      ) : (
        rootParts.map((part) => (
          <ServicePartNode
            key={part.id}
            node={part}
            perPartStats={perPartStats}
            perPartMtbf={perPartMtbf}
            showModular={showModular}
            instanceId={instanceId}
            onRefresh={onRefresh}
            refreshSeq={refreshSeq}
          />
        ))
      )}
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
    name: child?.name || getPartName(child),
    hasFailstate: !!child?.hasFailstate,
    isModular: !!child?.isModular,
  }));
}

function formatEUR(amount) {
  const val = Number(amount);
  if (!Number.isFinite(val)) return "—";
  return val.toLocaleString(undefined, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
}

function statsFor(partId, allStats) {
  return (
    allStats?.[partId] || {
      costEUR: 0,
      Repair: 0,
      Replace: 0,
      Cleaning: 0,
      Remanufacturing: 0,
      Refurbishment: 0,
    }
  );
}

function mtbfFor(partId, mtbfMap) {
  return mtbfMap?.[partId] || null;
}

function fmtHours(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function ServicePartNode({
  node,
  perPartStats,
  perPartMtbf,
  showModular,
  isTop = false,
  children: injectedChildren,
  instanceId,
  onRefresh = () => {},
  refreshSeq = 0,
}) {
  const nodeId = node?.id;
  const nodeName = getPartName(node);

  const [isExpanded, setIsExpanded] = useState(isTop);
  const [isLoading, setIsLoading] = useState(false);
  const [children, setChildren] = useState(null);

  const [localFail, setLocalFail] = useState(!!node?.hasFailstate);
  useEffect(() => {
    setLocalFail(!!node?.hasFailstate);
  }, [node?.hasFailstate, nodeId, refreshSeq]);

  const stats = useMemo(() => statsFor(nodeId, perPartStats), [nodeId, perPartStats]);
  const mtbf = useMemo(() => mtbfFor(nodeId, perPartMtbf), [nodeId, perPartMtbf]);

  useEffect(() => {
    let alive = true;
    if (!isExpanded || isTop || !nodeId) return;

    (async () => {
      setIsLoading(true);
      try {
        const kids = await api.getPartChildren(nodeId);
        if (!alive) return;
        setChildren(normalizeChildren(kids));
      } catch {
        if (!alive) return;
        setChildren([]);
      } finally {
        if (alive) setIsLoading(false);
      }
    })();

    return () => {
      alive = false;
    };
  }, [isExpanded, nodeId, isTop, refreshSeq]);

  const [isToggling, setIsToggling] = useState(false);
  const onToggleFail = async () => {
    if (!instanceId || !nodeId) return;
    try {
      setIsToggling(true);
      setLocalFail((v) => !v);
      await api.togglePartFailstate(instanceId, nodeId);
      await onRefresh();
    } catch (err) {
      setLocalFail(!!node?.hasFailstate);
      console.error("Toggle failstate failed:", err);
    } finally {
      setIsToggling(false);
    }
  };

  const failBadgeClass = localFail ? "badge bg-danger" : "badge bg-success";
  const failBadgeText = localFail ? "fail" : "no-fail";

  return (
    <Card>
      <Card.Header className="d-flex align-items-center justify-content-between">
        <div className="d-flex align-items-center gap-2" style={{ minWidth: 0 }}>
          <span className="fw-semibold text-truncate" title={nodeName}>
            {nodeName}
          </span>

          <span className={failBadgeClass}>{failBadgeText}</span>
          <InfoTip className="ms-1" placement="right" text={FIELD_HELP["part.failstate"]} />

          {showModular && (
            <>
              <span className={`badge ${node?.isModular ? "bg-primary" : "bg-secondary"}`}>
                {node?.isModular ? "modular" : "non-modular"}
              </span>
              <InfoTip className="ms-1" placement="right" text={FIELD_HELP["part.modular"]} />
            </>
          )}
        </div>

        <div className="d-flex align-items-center gap-2">
          {isExpanded && (
            <Button
              size="sm"
              variant={localFail ? "outline-success" : "outline-danger"}
              onClick={onToggleFail}
              disabled={isToggling}
            >
              {isToggling ? "…" : localFail ? "Mark OK" : "Mark fail"}
            </Button>
          )}
          <Button size="sm" variant="outline-secondary" onClick={() => setIsExpanded((v) => !v)}>
            {isExpanded ? "Collapse" : "Expand"}
          </Button>
        </div>
      </Card.Header>

      {isExpanded && (
        <Card.Body style={{ overflowX: "auto" }}>
          <div className="fw-semibold mb-2 d-flex align-items-center justify-content-between">
            <span>Service summary</span>
            <InfoTip placement="left" text={FIELD_HELP["service.summary.subtree"]} />
          </div>

          <div className="table-responsive">
            <Table bordered size="sm" className="mb-0 align-middle">
              <thead>
                <tr>
                  <th className="text-end">
                    <div className="d-flex align-items-center justify-content-end gap-2">
                      <span>Total cost</span>
                      <InfoTip placement="left" text={FIELD_HELP["service.cost.total"]} />
                    </div>
                  </th>
                  <th className="text-end">
                    <div className="d-flex align-items-center justify-content-end gap-2">
                      <span>Repair</span>
                      <InfoTip placement="left" text={FIELD_HELP["service.counts.repair"]} />
                    </div>
                  </th>
                  <th className="text-end">
                    <div className="d-flex align-items-center justify-content-end gap-2">
                      <span>Replace</span>
                      <InfoTip placement="left" text={FIELD_HELP["service.counts.replace"]} />
                    </div>
                  </th>
                  <th className="text-end">
                    <div className="d-flex align-items-center justify-content-end gap-2">
                      <span>Cleaning</span>
                      <InfoTip placement="left" text={FIELD_HELP["service.counts.cleaning"]} />
                    </div>
                  </th>
                  <th className="text-end">
                    <div className="d-flex align-items-center justify-content-end gap-2">
                      <span>Remanufacturing</span>
                      <InfoTip placement="left" text={FIELD_HELP["service.counts.remanufacturing"]} />
                    </div>
                  </th>
                  <th className="text-end">
                    <div className="d-flex align-items-center justify-content-end gap-2">
                      <span>Refurbishment</span>
                      <InfoTip placement="left" text={FIELD_HELP["service.counts.refurbishment"]} />
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="text-end">{formatEUR(stats.costEUR)}</td>
                  <td className="text-end">{stats.Repair}</td>
                  <td className="text-end">{stats.Replace}</td>
                  <td className="text-end">{stats.Cleaning}</td>
                  <td className="text-end">{stats.Remanufacturing}</td>
                  <td className="text-end">{stats.Refurbishment}</td>
                </tr>
              </tbody>
            </Table>
          </div>

          {/* Reliability (MTBF) */}
          <div className="fw-semibold mt-3 mb-2 d-flex align-items-center justify-content-between">
            <span>Reliability</span>
            <InfoTip placement="left" text={FIELD_HELP["mtbf.title"]} />
          </div>
          {mtbf ? (
            <div className="table-responsive">
              <Table bordered size="sm" className="mb-0 align-middle">
                <thead>
                  <tr>
                    <th className="text-end">
                      <div className="d-flex align-items-center justify-content-end gap-2">
                        <span>MTBF (h)</span>
                        <InfoTip placement="left" text={FIELD_HELP["mtbf.expected"]} />
                      </div>
                    </th>
                    <th className="text-end">
                      <div className="d-flex align-items-center justify-content-end gap-2">
                        <span>Expected remaining (h)</span>
                        <InfoTip placement="left" text={FIELD_HELP["mtbf.expected"]} />
                      </div>
                    </th>
                    <th className="text-end">
                      <div className="d-flex align-items-center justify-content-end gap-2">
                        <span>Status</span>
                        <InfoTip placement="left" text={FIELD_HELP["status.overall"]} />
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="text-end">{fmtHours(mtbf.mtbfHRS)}</td>
                    <td className="text-end">{fmtHours(mtbf.remainingHRS)}</td>
                    <td className="text-end">
                      {mtbf.exceeded ? (
                        <span className="badge bg-danger">Exceeded</span>
                      ) : (
                        <span className="badge bg-success">OK</span>
                      )}
                    </td>
                  </tr>
                </tbody>
              </Table>
            </div>
          ) : (
            <div className="text-muted">No MTBF data.</div>
          )}

          {/* Children */}
          {isTop ? (
            injectedChildren
          ) : (
            <>
              <div className="fw-semibold mt-3 mb-2 d-flex align-items-center justify-content-between">
                <span>Subparts</span>
                <InfoTip placement="left" text={FIELD_HELP["parts.subparts"]} />
              </div>
              {isLoading && (
                <div className="py-2 text-center">
                  <Spinner animation="border" size="sm" />
                </div>
              )}
              {!isLoading &&
                (children && children.length > 0 ? (
                  <div className="d-flex flex-column gap-3">
                    {children.map((child) => (
                      <ServicePartNode
                        key={child.id}
                        node={child}
                        perPartStats={perPartStats}
                        perPartMtbf={perPartMtbf}
                        showModular={showModular}
                        instanceId={instanceId}
                        onRefresh={onRefresh}
                        refreshSeq={refreshSeq}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="text-muted">No subparts.</div>
                ))}
            </>
          )}
        </Card.Body>
      )}
    </Card>
  );
}
