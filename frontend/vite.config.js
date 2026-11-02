import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// ConvoyConnect frontend — Vite config.
// Uses the Tailwind v4 Vite plugin (no tailwind.config.js / postcss.config.js
// needed with this approach — see src/index.css for the single @import line).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
  },
});
