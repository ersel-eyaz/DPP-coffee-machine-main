// src/shared/toApiURL.js
const RAW = import.meta.env.VITE_API_URL ?? "/api";
const API_BASE = RAW.replace(/\/+$/, ""); // "/api" or "https://api.example.com"
const API_BASE_IS_PATH = API_BASE.startsWith("/");

// Hosts that represent “the backend” in dev/compose
const BACKEND_HOSTS = new Set(["backend", "backend:8000", "localhost:8000", "127.0.0.1:8000", "[::1]:8000"]);

/**
 * Normalize a path/URL so local backend assets are fetched via same-origin `/api`
 */
export function toApiURL(input) {
  if (!input || typeof input !== "string") return "";
  const value = input.trim();
  if (!value) return "";

  if (API_BASE_IS_PATH && value.startsWith(API_BASE + "/")) return value;

  if (value.startsWith("//")) return value;

  // Absolute URL?
  try {
    const u = new URL(value, window.location.origin);
    const hostKey = u.port ? `${u.hostname}:${u.port}` : u.hostname;
    if (BACKEND_HOSTS.has(hostKey)) {
      return `${API_BASE}${u.pathname}${u.search}${u.hash}`;
    }

    // Same-origin absolute
    if (u.origin === window.location.origin && API_BASE_IS_PATH) {
      return `${API_BASE}${u.pathname}${u.search}${u.hash}`;
    }

    // External URL → leave as-is
    return value;
  } catch {
    if (value.startsWith("/") && API_BASE_IS_PATH) return `${API_BASE}${value}`;
    return value;
  }
}
