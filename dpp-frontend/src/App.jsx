// src/App.jsx
import React, { lazy, Suspense } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";

const DppLayout = lazy(() => import("./pages/DppLayout.jsx"));
const Home = lazy(() => import("./pages/Home.jsx"));
const OverView = lazy(() => import("./pages/OverView.jsx"));
const ServiceView = lazy(() => import("./pages/ServiceView.jsx"));
const EolView = lazy(() => import("./pages/EolView.jsx"));
const UtilityView = lazy(() => import("./pages/UtilityView.jsx"));
const DataQualityView = lazy(() => import("./pages/DataQualityView.jsx"));

function NotFoundView() {
  return <div style={CONTENT_PAD_STYLE}>Not found</div>;
}

function Loader() {
  return <div style={CONTENT_PAD_STYLE}>Loading…</div>;
}

/* --- Styles --- */
const APP_WRAPPER_STYLE = {
  fontFamily: "system-ui, sans-serif",
  color: "#111",
  minHeight: "100dvh",
  display: "grid",
  gridTemplateRows: "auto 1fr",
};
const HEADER_STYLE = {
  padding: "12px 16px",
  borderBottom: "1px solid #eee",
  display: "flex",
  gap: 12,
  alignItems: "center",
};
const BRAND_LINK_STYLE = { textDecoration: "none", fontWeight: 700 };
const CONTENT_PAD_STYLE = { padding: 16 };

export default function App() {
  return (
    <div style={APP_WRAPPER_STYLE}>
      <header style={HEADER_STYLE}>
        <Link to="/" style={BRAND_LINK_STYLE}>
          DPP
        </Link>
      </header>

      <Suspense fallback={<Loader />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/data-quality" element={<DataQualityView />} />

          <Route path="/dpp/:instanceId" element={<DppLayout />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<OverView />} />
            <Route path="service" element={<ServiceView />} />
            <Route path="eol" element={<EolView />} />
            <Route path="utility" element={<UtilityView />} />
          </Route>

          <Route path="*" element={<NotFoundView />} />
        </Routes>
      </Suspense>
    </div>
  );
}
