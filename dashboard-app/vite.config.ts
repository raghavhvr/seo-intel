import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Builds straight into ../docs (the GitHub Pages root). emptyOutDir stays
// false because docs/data.json is written by the Python pipeline, not by this
// build — the deploy workflow clears docs/assets/ before building instead.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  build: { outDir: "../docs", emptyOutDir: false },
});
