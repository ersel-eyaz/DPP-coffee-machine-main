import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const allowed = (process.env.VITE_ALLOWED_HOSTS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

// API proxy target for /api → backend
const target = process.env.VITE_PROXY_TARGET || "http://localhost:8000";

// Optional explicit HMR host (only set this when tunneling via ngrok)
const hmrHost = process.env.VITE_HMR_HOST || ""; // e.g. xx.ngrok-free.app
const hmr = hmrHost
  ? { host: hmrHost, clientPort: 443, protocol: "wss" } // ngrok HTTPS
  : undefined; // default local HMR (works in Docker and on host)

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: allowed,
    proxy: {
      "/api": {
        target,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
    hmr,
  },
  preview: {
    host: true,
    port: 4173,
    strictPort: true,
    allowedHosts: allowed,
  },
});
