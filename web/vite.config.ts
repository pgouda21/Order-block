import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Output is served by the Worker as static assets (worker/wrangler.toml [assets]).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
});
