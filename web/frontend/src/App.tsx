import { NavLink, Route, Routes } from 'react-router-dom'

import { Dashboard } from '@/pages/Dashboard'
import { SubmissionWizard } from '@/pages/SubmissionWizard'
import { TrialResultsPage } from '@/pages/TrialResultsPage'

function App() {
  return (
    <div className="min-h-screen">
      <nav className="flex gap-4 border-b border-zinc-200 px-6 py-3">
        <NavLink
          to="/wizard"
          className={({ isActive }) =>
            `text-sm font-medium ${isActive ? 'text-zinc-900' : 'text-zinc-500'}`
          }
        >
          Wizard
        </NavLink>
        <NavLink
          to="/dashboard"
          className={({ isActive }) =>
            `text-sm font-medium ${isActive ? 'text-zinc-900' : 'text-zinc-500'}`
          }
        >
          Dashboard
        </NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<SubmissionWizard />} />
        <Route path="/wizard" element={<SubmissionWizard />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/trials/:trialId" element={<TrialResultsPage />} />
      </Routes>
    </div>
  )
}

export default App
