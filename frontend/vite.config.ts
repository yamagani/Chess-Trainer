import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

// GitHub Pages serves the site under /<repo>/. The Pages workflow passes
// BASE_URL=/<repo>/ so forks work without editing this file; local dev uses /.
const pagesBase = "/Chess-Trainer/";

export default defineConfig(({ command, isPreview }) => ({
  plugins: [react(), tailwindcss()],
  // build + preview share the Pages base so `npm run preview` serves what Pages will
  base: process.env.BASE_URL || (command === "build" || isPreview ? pagesBase : "/"),
}));
