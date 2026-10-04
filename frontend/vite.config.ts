import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type ProxyOptions } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// The backend does not send CORS headers, so the browser talks to `/api` on our own origin
// and the dev/preview server forwards it. Set API_PROXY_TARGET to use a local backend.
const apiTarget = process.env.API_PROXY_TARGET ?? 'https://offline-ai-trip-advisor.vercel.app'

const proxy: Record<string, ProxyOptions> = {
  '/api': {
    target: apiTarget,
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // Ask before swapping in a new version, so an update never reloads mid-trip.
      registerType: 'prompt',
      injectRegister: false, // registered from React, see src/pwa/PwaStatus.tsx
      includeAssets: ['icon.svg'],
      manifest: {
        name: 'Offline Trip Advisor',
        short_name: 'Trip Advisor',
        description: 'Plan a heritage-site trip in Nigeria and keep the advice with you offline.',
        theme_color: '#14532d',
        background_color: '#f8faf7',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [{ src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }],
      },
      workbox: {
        // The service worker caches the app shell only. Trip data lives in IndexedDB.
        globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
  server: { proxy },
  preview: { proxy },
})
