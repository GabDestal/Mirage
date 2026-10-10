import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The avatars live outside this folder; dedupe makes them resolve react from here.
export default defineConfig({ plugins: [react()], resolve: { dedupe: ['react', 'react-dom'] } });
