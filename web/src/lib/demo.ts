// Startup context only; engine state and actions still come from the HTTP API.
export const isDemo = import.meta.env.VITE_MIRAGE_UI_MODE === 'demo'
