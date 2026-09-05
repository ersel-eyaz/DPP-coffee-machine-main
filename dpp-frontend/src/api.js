// src/api.js

/**
 * Minimal JSON API client for the DPP frontend.
 */

const RAW_BASE = import.meta.env.VITE_API_URL ?? "/api";
const API_BASE_URL = RAW_BASE.replace(/\/+$/, ""); // strip trailing "/"

/** Join base and path safely. */
function joinURL(base, path) {
  return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

async function fetchJSON(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const userSignal = options.signal;

  // Bridge userSignal -> controller (abort if userSignal aborts)
  if (userSignal) {
    if (userSignal.aborted) controller.abort();
    else userSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const hasBody = typeof options.body !== "undefined";
  const headers = {
    Accept: "application/json",
    ...(hasBody ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };

  let response;
  try {
    response = await fetch(url, { ...options, headers, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }

  const ct = response.headers.get("content-type") || "";

  if (!response.ok) {
    // Prefer JSON error payloads
    let errorDetail = "";
    if (ct.includes("application/json")) {
      try {
        const err = await response.json();
        errorDetail =
          typeof err?.detail === "string"
            ? `: ${err.detail}`
            : err?.detail
              ? `: ${JSON.stringify(err.detail)}`
              : `: ${JSON.stringify(err)}`;
      } catch {
        // fall back to text below
      }
    }
    if (!errorDetail) {
      try {
        const text = await response.text();
        if (text) errorDetail = `: ${text}`;
      } catch {
        // ignore
      }
    }
    throw new Error(`${response.status} ${response.statusText}${errorDetail}`);
  }

  // All endpoints return JSON; be tolerant:
  return ct.includes("application/json") ? response.json() : response.text();
}

async function fetchBlob(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const userSignal = options.signal;
  if (userSignal) {
    if (userSignal.aborted) controller.abort();
    else userSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers = {
    Accept: "application/ld+json, application/json;q=0.9, */*;q=0.1",
    ...(options.headers || {}),
  };

  let response;
  try {
    response = await fetch(url, { ...options, headers, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ${response.statusText}`);
  }
  return response.blob();
}

/**
 * POST JSON convenience wrapper.
 * @param {string} url
 * @param {any} body
 * @param {RequestInit} [options]
 * @returns {Promise<any>}
 */
function postJSON(url, body, options = {}) {
  return fetchJSON(url, { ...options, method: "POST", body: JSON.stringify(body) });
}

export const api = {
  /** List all DPP instances. */
  listInstances() {
    return fetchJSON(joinURL(API_BASE_URL, "/dpp/instance/"));
  },

  /**
   * Retrieve a single DPP instance (includes links).
   * @param {string} id
   */
  getInstance(id) {
    const iid = encodeURIComponent(id);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}`));
  },

  /**
   * User-facing summary for an instance.
   * @param {string} instanceId
   */
  getOverviewSummary(instanceId) {
    const iid = encodeURIComponent(instanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/user-summary`));
  },

  /**
   * Materials summary for a part instance (by name).
   * @param {string} partInstanceId
   */
  getMaterialsCombined(partInstanceId) {
    const pid = encodeURIComponent(partInstanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/part/instance/${pid}/combined_material_summary_by_name`));
  },

  /**
   * Returning places for a static DPP.
   * @param {string} dppStaticId
   */
  getReturningPlaces(dppStaticId) {
    const sid = encodeURIComponent(dppStaticId);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/${sid}/returning-places/`));
  },

  /**
   * Static-level images (web URLs).
   * @param {string} dppStaticId
   */
  listImagesWeb(dppStaticId) {
    const sid = encodeURIComponent(dppStaticId);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/${sid}/images-web/`));
  },

  /**
   * Service statistics for modular parts.
   * @param {string} instanceId
   */
  getServiceModular(instanceId) {
    const iid = encodeURIComponent(instanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/statistics/count-service-modular/`));
  },

  /**
   * Read a part instance and its static link.
   * @param {string} partInstanceId
   */
  getPartInstance(partInstanceId) {
    const pid = encodeURIComponent(partInstanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/part/instance/${pid}`));
  },

  /**
   * Materials summary for a part instance.
   * @param {string} partInstanceId
   */
  getPartMaterials(partInstanceId) {
    const pid = encodeURIComponent(partInstanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/part/instance/${pid}/combined_material_summary_by_name`));
  },

  /**
   * Child parts for a part instance.
   * @param {string} partInstanceId
   */
  getPartChildren(partInstanceId) {
    const pid = encodeURIComponent(partInstanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/part/instance/${pid}/children`));
  },

  /**
   * Rare-earth metrics for a part instance.
   * @param {string} partInstanceId
   */
  getPartRareEarth(partInstanceId) {
    const pid = encodeURIComponent(partInstanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/part/instance/${pid}/rare_earth_metrics`));
  },

  /**
   * Process map for an instance (production, transport, secondary).
   * @param {string} instanceId
   */
  getProcessMap(instanceId) {
    const iid = encodeURIComponent(instanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/process-map`));
  },

  /**
   * End-of-life summary for an instance.
   * @param {string} instanceId
   */
  getEolSummary(instanceId) {
    const iid = encodeURIComponent(instanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/eol-summary`));
  },

  /**
   * Service summary for an instance.
   * @param {string} instanceId
   */
  getServiceSummary(instanceId) {
    const iid = encodeURIComponent(instanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/service-summary`));
  },

  /** List places (service / processing locations). */
  getPlaces() {
    return fetchJSON(joinURL(API_BASE_URL, "/place/"));
  },

  // --- Service actions ---

  /**
   * Register a repair step.
   * @param {string} instanceId
   * @param {any} body
   */
  serviceRepair(instanceId, body) {
    const iid = encodeURIComponent(instanceId);
    return postJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/service/repair/`), body);
  },

  /**
   * Register a replace step.
   * @param {string} instanceId
   * @param {any} body
   */
  serviceReplace(instanceId, body) {
    const iid = encodeURIComponent(instanceId);
    return postJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/service/replace/`), body);
  },

  /**
   * Register a cleaning step.
   * @param {string} instanceId
   * @param {any} body
   */
  serviceCleaning(instanceId, body) {
    const iid = encodeURIComponent(instanceId);
    return postJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/service/cleaning/`), body);
  },

  /**
   * Register a remanufacturing step.
   * @param {string} instanceId
   * @param {any} body
   */
  serviceRemanufacturing(instanceId, body) {
    const iid = encodeURIComponent(instanceId);
    return postJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/service/remanufacturing/`), body);
  },

  /**
   * Register a refurbishment step.
   * @param {string} instanceId
   * @param {any} body
   */
  serviceRefurbishment(instanceId, body) {
    const iid = encodeURIComponent(instanceId);
    return postJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/service/refurbishment/`), body);
  },

  /**
   * Register a recycling step (and discontinue instance).
   * @param {string} instanceId
   * @param {any} body
   */
  serviceRecycling(instanceId, body) {
    const iid = encodeURIComponent(instanceId);
    return postJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/service/recycling/`), body);
  },

  /**
   * Toggle failstate on a specific part within an instance.
   * @param {string} instanceId
   * @param {string} partId
   */
  togglePartFailstate(instanceId, partId) {
    const iid = encodeURIComponent(instanceId);
    const pid = encodeURIComponent(partId);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/part/${pid}/toggle-failstate`), {
      method: "POST",
    });
  },

  getUtilitySummary(instanceId) {
    const iid = encodeURIComponent(instanceId);
    return fetchJSON(joinURL(API_BASE_URL, `/dpp/instance/${iid}/utility-summary`));
  },

  /**
   * Download JSON-LD for this instance as a file.
   * Backend route: GET /jsonld/dpp/instance/{instance_id}/download
   */
  async downloadJsonLdInstance(instanceId) {
    const iid = encodeURIComponent(instanceId);
    const url = joinURL(API_BASE_URL, `/jsonld/dpp/instance/${iid}/download`);
    return fetchBlob(url);
  },

  /**
   * Download bundle (DPPStatic + all its instances) as a file.
   * Backend route: GET /jsonld/export/{dpp_id}/download
   */
  async downloadJsonLdBundle(staticId) {
    const sid = encodeURIComponent(staticId);
    const url = joinURL(API_BASE_URL, `/jsonld/export/${sid}/download`);
    return fetchBlob(url);
  },

  /**
   * Run the isolated data-quality layer on an external JSON-LD document.
   * Local semantic-model initialization can make the first run noticeably slower.
   * @param {{scope: "auto"|"product"|"emission"|"service", mode: "harmonization"|"anomaly"|"both", document: any, selected_instance_id?: string, anomaly_options?: any}} body
   */
  runDataQuality(body) {
    return fetchJSON(
      joinURL(API_BASE_URL, "/data-quality/run"),
      { method: "POST", body: JSON.stringify(body) },
      300000
    );
  },

  listDataQualityExamples() {
    return fetchJSON(joinURL(API_BASE_URL, "/data-quality/examples"));
  },

  getDataQualityExample(name) {
    return fetchJSON(joinURL(API_BASE_URL, `/data-quality/examples/${encodeURIComponent(name)}`));
  },

  listDataQualityServiceConcepts() {
    return fetchJSON(joinURL(API_BASE_URL, "/data-quality/service-concepts"));
  },

  createDataQualityServiceTextFeedback(body) {
    return postJSON(joinURL(API_BASE_URL, "/data-quality/feedback/service-text"), body);
  },

  buildServiceConceptCandidateReport(body = {}) {
    return postJSON(joinURL(API_BASE_URL, "/data-quality/service-concept-candidates"), body);
  },

  explainServiceConceptCandidateMetrics(body = {}) {
    return postJSON(joinURL(API_BASE_URL, "/data-quality/service-concept-candidates/metric-interpretation"), body);
  },
};
