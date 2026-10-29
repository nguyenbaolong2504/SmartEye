import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
const proxy={ '/api': process.env.API_TARGET || 'http://127.0.0.1:8000' };
export default defineConfig({ plugins: [react()], build:{rollupOptions:{output:{manualChunks:{'street-map':['leaflet']}}}}, server: { port: 5173, proxy }, preview:{proxy} });
