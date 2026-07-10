import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxies /api requests to the Express backend during development
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:5000",
      "/uploads": "http://localhost:5000",
    },
  },
});
