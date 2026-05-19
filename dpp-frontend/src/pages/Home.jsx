// src/pages/Home.jsx
import React, { useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Col, Container, Form, ListGroup, Row, Spinner } from "react-bootstrap";
import { ClipboardCheck } from "react-bootstrap-icons";
import { Link } from "react-router-dom";

import { api } from "../api";

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let on = true;
    setLoading(true);
    setErr(null);
    api
      .listInstances()
      .then((data) => {
        if (!on) return;
        setItems(Array.isArray(data) ? data : []);
      })
      .catch((e) => {
        if (!on) return;
        setErr(e?.message || String(e));
      })
      .finally(() => on && setLoading(false));
    return () => {
      on = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return items;
    return items.filter((inst) => {
      const name = inst?.dppStaticLink?.name || "";
      return (
        name.toLowerCase().includes(term) ||
        String(inst?.id || "")
          .toLowerCase()
          .includes(term)
      );
    });
  }, [items, q]);

  const active = useMemo(() => filtered.filter((i) => !i?.discontinued), [filtered]);
  const discontinued = useMemo(() => filtered.filter((i) => !!i?.discontinued), [filtered]);

  return (
    <Container className="py-4">
      <Row className="align-items-center mb-3">
        <Col>
          <h2 className="mb-0">Select a DPP instance</h2>
          <div className="text-muted">Pick a product to view its Digital Product Passport.</div>
        </Col>
        <Col xs="auto" className="d-flex align-items-center gap-2">
          <Button as={Link} to="/data-quality" variant="outline-primary" size="sm">
            <ClipboardCheck className="me-1" aria-hidden="true" />
            Data Quality
          </Button>
          <Badge bg="secondary">{items.length} total</Badge>
        </Col>
      </Row>

      <Row className="mb-3">
        <Col xs={12} md={6} lg={4}>
          <Form.Control placeholder="Search by product name or ID…" value={q} onChange={(e) => setQ(e.target.value)} />
        </Col>
      </Row>

      {loading && (
        <div className="py-4 text-center">
          <Spinner animation="border" />
        </div>
      )}

      {err && (
        <Alert variant="danger" className="mb-3">
          Error: {err}
        </Alert>
      )}

      {!loading && !err && (
        <>
          {/* Active instances */}
          <Card className="mb-4">
            <Card.Header className="h6 d-flex justify-content-between align-items-center">
              <span>Active instances</span>
              <Badge bg="success">{active.length}</Badge>
            </Card.Header>
            <ListGroup variant="flush">
              {active.length ? (
                active.map((inst) => {
                  const staticName = inst?.dppStaticLink?.name ?? "(no name)";
                  return (
                    <ListGroup.Item key={inst.id} className="d-flex justify-content-between align-items-center">
                      <div className="me-2">
                        <div className="fw-semibold">{staticName}</div>
                        <div className="text-muted" style={{ fontFamily: "monospace" }}>
                          {inst.id}
                        </div>
                      </div>
                      <div>
                        <Button as={Link} to={`/dpp/${inst.id}/overview`} variant="primary" size="sm">
                          Open
                        </Button>
                      </div>
                    </ListGroup.Item>
                  );
                })
              ) : (
                <ListGroup.Item className="text-muted">No active instances.</ListGroup.Item>
              )}
            </ListGroup>
          </Card>

          {/* Discontinued instances */}
          <Card>
            <Card.Header className="h6 d-flex justify-content-between align-items-center">
              <span>Discontinued (recycled)</span>
              <Badge bg="secondary">{discontinued.length}</Badge>
            </Card.Header>
            <ListGroup variant="flush">
              {discontinued.length ? (
                discontinued.map((inst) => {
                  const staticName = inst?.dppStaticLink?.name ?? "(no name)";
                  return (
                    <ListGroup.Item key={inst.id} className="d-flex justify-content-between align-items-center">
                      <div className="me-2">
                        <div className="fw-semibold">{staticName}</div>
                        <div className="text-muted" style={{ fontFamily: "monospace" }}>
                          {inst.id}
                        </div>
                      </div>
                      <div className="d-flex align-items-center gap-2">
                        <Badge bg="secondary">Discontinued</Badge>
                        <Button as={Link} to={`/dpp/${inst.id}/overview`} variant="outline-primary" size="sm">
                          Open
                        </Button>
                      </div>
                    </ListGroup.Item>
                  );
                })
              ) : (
                <ListGroup.Item className="text-muted">No discontinued instances.</ListGroup.Item>
              )}
            </ListGroup>
          </Card>
        </>
      )}
    </Container>
  );
}
