import { createBrowserRouter } from 'react-router'
import { AppShell } from './components/AppShell'
import { HomePage } from './pages/HomePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PlanPage } from './pages/PlanPage'
import { ResultPage } from './pages/ResultPage'
import { TripPage } from './pages/TripPage'
import { TripsPage } from './pages/TripsPage'

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'places/:siteId/plan', element: <PlanPage /> },
      { path: 'places/:siteId/result', element: <ResultPage /> },
      { path: 'trips', element: <TripsPage /> },
      { path: 'trips/:tripId', element: <TripPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
