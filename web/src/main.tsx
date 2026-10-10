import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { Toaster } from 'sonner'
import { queryClient } from '@/api/client'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Fleet } from '@/pages/fleet'
import { Integrations } from '@/pages/integrations'
import { Chat } from '@/pages/chat'
import { DemoEntry } from '@/pages/login'
import { Incidents, RunPage } from '@/pages/placeholders'
import { IncidentPage } from '@/pages/incident'
import './index.css'

try {
  const theme = localStorage.getItem('mirage-theme')
  if (theme) document.documentElement.dataset.theme = theme
} catch {
  /* no storage: follow the system theme */
}

const router = createBrowserRouter([
  {
    element: <DemoEntry />,
    children: [
      { path: '/', element: <Chat />, handle: { title: 'Chat' } },
      { path: '/fleet', element: <Fleet />, handle: { title: 'Fleet' } },
      { path: '/integrations', element: <Integrations />, handle: { title: 'API keys' } },
      { path: '/incidents', element: <Incidents />, handle: { title: 'Incidents' } },
      { path: '/incidents/:id', element: <IncidentPage />, handle: { title: 'Incident' } },
      { path: '/runs/:id', element: <RunPage />, handle: { title: 'Run' } },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
        <Toaster
          position="bottom-right"
          toastOptions={{ className: '!bg-paper !text-ink !border-0 !shadow-float !rounded-node !font-sans !text-body' }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
)
