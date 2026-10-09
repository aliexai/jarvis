import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Everything is bundled locally: no CDN, no external fonts, no remote assets.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2022',
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 1600,
  },
});
