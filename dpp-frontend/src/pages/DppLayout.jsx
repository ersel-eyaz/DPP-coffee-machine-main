// src/layouts/DppLayout.jsx
import React from "react";
import { Container, Nav, Navbar } from "react-bootstrap";
import { NavLink, Outlet, useParams } from "react-router-dom";

export default function DppLayout() {
  const { instanceId } = useParams();

  return (
    <>
      {" "}
      <Container className="py-3 pb-5">
        <Outlet />
      </Container>
      <Navbar fixed="bottom" bg="body" className="dpp-bottom-nav shadow-sm">
        <Nav className="mx-auto" variant="pills" justify>
          <Nav.Link as={NavLink} to={`/dpp/${instanceId}/overview`} end>
            User and Compliance
          </Nav.Link>
          <Nav.Link as={NavLink} to={`/dpp/${instanceId}/service`} end>
            Service and Repair
          </Nav.Link>
          <Nav.Link as={NavLink} to={`/dpp/${instanceId}/eol`} end>
            End of Life (EoL)
          </Nav.Link>
          <Nav.Link as={NavLink} to={`/dpp/${instanceId}/utility`} end>
            Utility and Statistics
          </Nav.Link>
          <Nav.Link as={NavLink} to={`/`} end>
            Select DPP
          </Nav.Link>
        </Nav>
      </Navbar>
    </>
  );
}
