// src/shared/ReturningPlacesMap.jsx
import "leaflet/dist/leaflet.css";

import L from "leaflet";
import React, { useEffect, useMemo } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

const PLACE_PIN_ICON = L.divIcon({
  className: "ret-pin",
  html: `<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#6f42c1;border:2px solid #fff;box-shadow:0 0 2px rgba(0,0,0,.4)"></span>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7],
});

function FitBounds({ coordinates }) {
  const map = useMap();
  useEffect(() => {
    if (!coordinates?.length) return;
    const bounds = L.latLngBounds(coordinates);
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [20, 20] });
  }, [coordinates, map]);
  return null;
}

export default function ReturningPlacesMap({ places = [], height = 280 }) {
  const mappablePlaces = useMemo(
    () =>
      (Array.isArray(places) ? places : []).filter(
        (p) => Number.isFinite(p?.latitude) && Number.isFinite(p?.longitude),
      ),
    [places],
  );

  const hasMappablePlaces = mappablePlaces.length > 0;
  const initialCenter = hasMappablePlaces ? [mappablePlaces[0].latitude, mappablePlaces[0].longitude] : [50, 8]; // sensible default (central Europe)

  const coordinates = mappablePlaces.map((p) => [p.latitude, p.longitude]);

  return (
    <div style={{ height, width: "100%" }}>
      {hasMappablePlaces ? (
        <MapContainer
          style={{ height: "100%", width: "100%", borderRadius: 12, overflow: "hidden" }}
          center={initialCenter}
          zoom={5}
          scrollWheelZoom={false}
        >
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitBounds coordinates={coordinates} />

          {mappablePlaces.map((place, idx) => (
            <Marker
              key={place.id || place.gln || idx}
              position={[place.latitude, place.longitude]}
              icon={PLACE_PIN_ICON}
            >
              <Popup>
                <div className="mb-1">
                  <strong>{place.name || place.id || "Place"}</strong>
                </div>
                {place.gln ? <div className="text-muted small">GLN: {place.gln}</div> : null}
                <div className="text-muted small">
                  {place.latitude.toFixed(3)}, {place.longitude.toFixed(3)}
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      ) : (
        <div className="text-muted">No map data.</div>
      )}
    </div>
  );
}
