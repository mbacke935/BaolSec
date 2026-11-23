/**
 * Application BaolSec — authentification + interface admin (C22) + interface analyste (C23).
 *
 * Routes publiques :  /login
 * Interface admin    (AdminLayout)   : /sources, /rules, /users
 * Interface analyste (AnalystLayout) : /, /incidents, /incidents/:id, /search, /coverage
 *
 * Toutes les routes applicatives sont protégées : sans session valide,
 * on est redirigé vers /login (plus de boucle de 401).
 */
import type { ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useAuth } from './hooks/useAuth';
import { AdminLayout } from './components/AdminLayout';
import { AnalystLayout } from './components/AnalystLayout';

import { LoginPage } from './pages/LoginPage';
import { LandingPage } from './pages/LandingPage';
import { AdminOverviewPage } from './pages/AdminOverviewPage';
import { SourcesPage } from './pages/SourcesPage';
import { RulesPage } from './pages/RulesPage';
import { UsersPage } from './pages/UsersPage';
import { DashboardPage } from './pages/DashboardPage';
import { IncidentsListPage } from './pages/IncidentsListPage';
import { IncidentDetailPage } from './pages/IncidentDetailPage';
import { SearchPage } from './pages/SearchPage';
import { CoveragePage } from './pages/CoveragePage';
import { AlertsPage } from './pages/AlertsPage';
import { EventsPage } from './pages/EventsPage';
import { MonitorPage } from './pages/MonitorPage';

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

function Loading() {
  return <div style={{ padding: '2rem', color: '#9aadc0', fontFamily: 'system-ui' }}>Chargement…</div>;
}

/** Interface admin, protégée. */
function Admin({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  return <AdminLayout>{children}</AdminLayout>;
}

/** Interface analyste, protégée. */
function Analyst({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  return <AnalystLayout>{children}</AnalystLayout>;
}

export function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />

          {/* Interface administrateur (C22) */}
          <Route path="/admin"   element={<Admin><AdminOverviewPage /></Admin>} />
          <Route path="/sources" element={<Admin><SourcesPage /></Admin>} />
          <Route path="/rules"   element={<Admin><RulesPage /></Admin>} />
          <Route path="/users"   element={<Admin><UsersPage /></Admin>} />

          {/* Interface analyste (C23) */}
          <Route path="/dashboard"       element={<Analyst><DashboardPage /></Analyst>} />
          <Route path="/incidents"      element={<Analyst><IncidentsListPage /></Analyst>} />
          <Route path="/incidents/:id"  element={<Analyst><IncidentDetailPage /></Analyst>} />
          <Route path="/alerts"         element={<Analyst><AlertsPage /></Analyst>} />
          <Route path="/events"         element={<Analyst><EventsPage /></Analyst>} />
          <Route path="/search"         element={<Analyst><SearchPage /></Analyst>} />
          <Route path="/coverage"       element={<Analyst><CoveragePage /></Analyst>} />
          <Route path="/monitor"        element={<Analyst><MonitorPage /></Analyst>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
