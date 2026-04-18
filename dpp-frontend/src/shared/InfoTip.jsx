// src/shared/InfoTip.jsx
import React from "react";
import { OverlayTrigger, Tooltip } from "react-bootstrap";
import { InfoCircleFill } from "react-bootstrap-icons";

export default function InfoTip({ text, placement = "right", className, size = 14, label = "Info" }) {
  if (!text) return null;

  const tooltipId =
    typeof React.useId === "function" ? React.useId() : `infotip-${Math.random().toString(36).slice(2, 9)}`;

  return (
    <OverlayTrigger
      placement={placement}
      delay={{ show: 150, hide: 100 }}
      trigger={["hover", "focus"]}
      overlay={<Tooltip id={tooltipId}>{text}</Tooltip>}
    >
      <button
        type="button"
        className={className || "btn p-0 ms-1 text-body-secondary bg-transparent border-0"}
        style={{ cursor: "pointer", lineHeight: 0 }}
        aria-label={label}
        aria-describedby={tooltipId}
      >
        <InfoCircleFill size={size} aria-hidden="true" focusable="false" />
      </button>
    </OverlayTrigger>
  );
}
