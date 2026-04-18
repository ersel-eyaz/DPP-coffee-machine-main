// src/shared/ProcessMap.jsx
import L from "leaflet";
import React, { useMemo } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";

const CATEGORY_COLORS = {
  production: "#2ca02c",
  transport: "#1f77b4",
  secondary: "#d62728",
};

/** Creates divIcon used for counts. */
function createLabelIcon(text) {
  return L.divIcon({
    className: "edge-count",
    html: `<div style="
      background: rgba(255,255,255,0.85);
      border: 1px solid #bbb;
      border-radius: 8px;
      padding: 0 6px;
      font-size: 11px;
      line-height: 18px;
      white-space: nowrap;
    ">${text}</div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

/** rotated arrowhead icon. */
function createArrowIcon(angleDeg) {
  return L.divIcon({
    className: "arrow-icon",
    html: `<div style="
      transform: rotate(${angleDeg}deg);
      font-size: 16px;
      line-height: 16px;
      color: ${CATEGORY_COLORS.transport};
      text-shadow: 0 0 2px #fff;
    ">➤</div>`,
    iconSize: [0, 0],
    iconAnchor: [8, 8],
  });
}

/** Calculates great-circle bearing from point A to point B. */
function calculateBearing([lat1, lng1], [lat2, lng2]) {
  const toRad = (d) => (d * Math.PI) / 180;
  const toDeg = (r) => (r * 180) / Math.PI;
  const dLon = toRad(lng2 - lng1);
  const y = Math.sin(dLon) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) - Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(dLon);
  const brng = Math.atan2(y, x);
  return (toDeg(brng) + 360) % 360;
}

function interpolateMidpoint([lat1, lng1], [lat2, lng2], t = 0.5) {
  return [lat1 + (lat2 - lat1) * t, lng1 + (lng2 - lng1) * t];
}

function FitBounds({ nodes }) {
  const map = useMap();
  React.useEffect(() => {
    if (!nodes?.length) return;
    const bounds = L.latLngBounds(nodes.map((n) => [n.latitude, n.longitude]));
    if (bounds.isValid()) map.fitBounds(bounds.pad(0.2));
  }, [nodes, map]);
  return null;
}
export default function ProcessMap({ data, height = 360 }) {
  const nodes = data?.nodes ?? [];
  const edges = data?.edges ?? [];

  const nodeIndex = useMemo(() => {
    const index = new Map();
    nodes.forEach((node) => index.set(node.id ?? `${node.latitude},${node.longitude}`, node));
    return index;
  }, [nodes]);

  return (
    <div style={{ height, width: "100%", borderRadius: 12, overflow: "hidden" }}>
      <MapContainer style={{ height: "100%", width: "100%" }} zoom={5} center={[50, 9]}>
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <FitBounds nodes={nodes} />

        {edges.map((edge, i) => {
          const sourceNode = nodeIndex.get(edge.sourceId);
          const targetNode = nodeIndex.get(edge.targetId);
          if (!sourceNode || !targetNode) return null;

          const path = [
            [sourceNode.latitude, sourceNode.longitude],
            [targetNode.latitude, targetNode.longitude],
          ];

          const edgeBearing = calculateBearing(path[0], path[1]);
          const midpoint = interpolateMidpoint(path[0], path[1], 0.5);
          const arrowPos = interpolateMidpoint(path[0], path[1], 0.82);

          return (
            <React.Fragment key={`edge-${i}`}>
              <Polyline
                positions={path}
                pathOptions={{
                  color: CATEGORY_COLORS[edge.category] || "#666",
                  weight: 3,
                  opacity: 0.9,
                }}
              />
              {edge.count > 1 && (
                <Marker position={midpoint} icon={createLabelIcon(`× ${edge.count}`)} interactive={false} />
              )}
              <Marker position={arrowPos} icon={createArrowIcon(edgeBearing)} interactive={false} />
            </React.Fragment>
          );
        })}

        {nodes.map((node, i) => {
          const counts = node.categoryCounts || {};
          const ringSpecs = [
            { category: "transport", radius: 9, weight: 5 },
            { category: "production", radius: 6.5, weight: 5 },
            { category: "secondary", radius: 4, weight: 5 },
          ];

          return (
            <React.Fragment key={`node-${i}`}>
              {ringSpecs.map((ring) =>
                (counts[ring.category] ?? 0) > 0 ? (
                  <CircleMarker
                    key={`${i}-${ring.category}`}
                    center={[node.latitude, node.longitude]}
                    radius={ring.radius}
                    pathOptions={{ color: CATEGORY_COLORS[ring.category], weight: ring.weight, fill: false }}
                  />
                ) : null,
              )}
              <CircleMarker
                center={[node.latitude, node.longitude]}
                radius={2.2}
                pathOptions={{ color: "#222", weight: 2, fill: true, fillOpacity: 1 }}
              />
              {node.totalCount > 0 && (
                <Marker
                  position={[node.latitude, node.longitude]}
                  icon={createLabelIcon(`${node.totalCount}`)}
                  interactive={false}
                />
              )}
              <Marker position={[node.latitude, node.longitude]}>
                <Popup>
                  <div>
                    <div className="fw-semibold">{node.name || node.id}</div>
                    <div className="text-muted small">
                      {node.latitude.toFixed(3)}, {node.longitude.toFixed(3)}
                    </div>
                    <div className="mt-1 small">
                      <div>Production: {counts.production ?? 0}</div>
                      <div>Transport: {counts.transport ?? 0}</div>
                      <div>Secondary: {counts.secondary ?? 0}</div>
                    </div>
                  </div>
                </Popup>
              </Marker>
            </React.Fragment>
          );
        })}
      </MapContainer>
    </div>
  );
}
