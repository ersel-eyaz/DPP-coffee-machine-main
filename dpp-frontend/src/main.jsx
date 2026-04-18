// src/main.jsx
import "bootstrap/dist/css/bootstrap.min.css";
import "./theme.css";
import "leaflet/dist/leaflet.css";

import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App.jsx";

// Fail fast if the root container is missing
const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error('Root container "#root" not found. Ensure index.html includes <div id="root"></div>.');
}

// Support sub-path deployments
const basename = import.meta?.env?.BASE_URL ?? "/";

createRoot(rootElement).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
