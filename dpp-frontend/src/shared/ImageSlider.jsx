// src/shared/ImageSlider.jsx
import React, { useCallback, useEffect, useRef, useState } from "react";

import { toApiURL } from "./toApiURL";

export default function ImageSlider({
  images = [],
  startIndex = 0,
  className = "",
  maxWidth = 600,
  placeholderHeight = 280,
}) {
  const normalized = Array.isArray(images)
    ? images
        .map((item, i) => {
          const srcRaw = typeof item === "string" ? item : (item?.src ?? item?.url ?? "");
          const alt = typeof item === "string" ? "image" : (item?.alt ?? item?.title ?? "image");
          if (typeof srcRaw !== "string" || !srcRaw.trim()) return null;

          const key = (typeof item === "object" && (item.id || item._id || item.key)) ?? `${i}-${srcRaw}`;

          return { key, src: toApiURL(srcRaw), alt };
        })
        .filter(Boolean)
    : [];

  const count = normalized.length;
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [errorImg, setErrorImg] = useState(false);

  const imgRef = useRef(null);
  const wrapRef = useRef(null);

  // keep index valid on data change
  useEffect(() => {
    const safe = Math.max(0, Math.min(count - 1, Number.isInteger(startIndex) ? startIndex : 0));
    setIdx(safe);
    setErrorImg(false);
    setLoading(true);
  }, [count, startIndex]);

  const goPrev = useCallback(() => {
    if (count < 2) return;
    setIdx((i) => (i - 1 + count) % count);
    setErrorImg(false);
    setLoading(true);
  }, [count]);

  const goNext = useCallback(() => {
    if (count < 2) return;
    setIdx((i) => (i + 1) % count);
    setErrorImg(false);
    setLoading(true);
  }, [count]);

  const onKeyDown = (e) => {
    if (e.key === "ArrowLeft") goPrev();
    if (e.key === "ArrowRight") goNext();
  };

  const onLoad = () => {
    setLoading(false);
    setErrorImg(false);
  };

  const onError = () => {
    setLoading(false);
    setErrorImg(true);
  };

  if (!count) {
    return (
      <div className={className} style={{ width: "100%", maxWidth, display: "inline-block" }}>
        <div
          style={{
            position: "relative",
            width: "100%",
            minHeight: placeholderHeight,
            background: "#fff",
            border: "1px solid #e9ecef",
            borderRadius: 8,
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div style={{ color: "#6c757d", fontSize: 14 }}>No images available.</div>
        </div>
      </div>
    );
  }

  const current = normalized[idx];

  return (
    <div
      className={className}
      tabIndex={0}
      onKeyDown={onKeyDown}
      style={{
        width: "100%",
        maxWidth,
        display: "inline-block",
      }}
    >
      <div
        ref={wrapRef}
        style={{
          position: "relative",
          width: "100%",
          minHeight: loading ? 140 : 0,
          background: "#fff",
          border: "1px solid #e9ecef",
          borderRadius: 8,
          overflow: "hidden",
        }}
      >
        {/* IMAGE */}
        {!errorImg ? (
          <img
            key={current.key}
            ref={imgRef}
            src={current.src}
            alt={current.alt || "image"}
            onLoad={onLoad}
            onError={onError}
            loading="lazy"
            style={{
              width: "100%",
              height: "auto",
              display: "block",
              objectFit: "contain",
              background: "#f8f9fa",
            }}
          />
        ) : (
          <div
            style={{
              width: "100%",
              padding: "32px 12px",
              textAlign: "center",
              color: "#6c757d",
              background: "#f8f9fa",
            }}
          >
            Image failed to load.
          </div>
        )}

        {/* CONTROLS */}
        {count > 1 && !errorImg && (
          <>
            <button type="button" aria-label="Previous image" onClick={goPrev} style={btnStyle("left")}>
              ‹
            </button>
            <button type="button" aria-label="Next image" onClick={goNext} style={btnStyle("right")}>
              ›
            </button>
            <div
              style={{
                position: "absolute",
                bottom: 8,
                right: 10,
                background: "rgba(0,0,0,0.55)",
                color: "#fff",
                fontSize: 12,
                padding: "2px 6px",
                borderRadius: 12,
              }}
            >
              {idx + 1} / {count}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function btnStyle(side) {
  return {
    position: "absolute",
    top: "50%",
    transform: "translateY(-50%)",
    [side]: 8,
    width: 36,
    height: 36,
    borderRadius: "50%",
    background: "rgba(0,0,0,0.55)",
    color: "#fff",
    border: "none",
    cursor: "pointer",
    fontSize: 22,
    lineHeight: "36px",
    textAlign: "center",
    userSelect: "none",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  };
}
