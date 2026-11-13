/**
 * Application BaolSec Nexus — IA de la maquette : landing publique, connexion,
 * puis un espace de travail unifié (/app) protégé par authentification.
 *
 *   /            → LandingPage (publique)
 *   /login       → LoginPage (publique)
 *   /app         → AppShell (protégé) :
 *                   index → Vue générale ; events ; alerts ; incidents(+/:id) ;
 *                   sources ; rules (Détection) ; monitor (Supervision) ;
 *                   users (Administrateur uniquement)
 */
import type { ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useAuth } from './hooks/useAuth';
import { AppShell } from './components/AppShell';

import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { OverviewPage } from './pages/OverviewPage';
import { EventsPage } from './pages/EventsPage';
import { AlertsPage } from './pages/AlertsPage';
import { IncidentsPage } from './pages/IncidentsPage';
import { IncidentDetailPage } from './pages/IncidentDetailPage';
import { SourcesPage } from './pages/SourcesPage';
import { RulesPage } from './pages/RulesPage';
import { MonitorPage } from './pages/MonitorPage';
import { UsersPage } from './pages/UsersPage';

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

/** Réservé à l'administrateur ; sinon redirige vers la vue générale. */
function AdminOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user?.role !== 'ADMIN') return <Navigate to="/app" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />

          <Route path="/app" element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="events" element={<EventsPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="incidents" element={<IncidentsPage />} />
            <Route path="incidents/:id" element={<IncidentDetailPage />} />
            <Route path="sources" element={<SourcesPage />} />
            <Route path="rules" element={<RulesPage />} />
            <Route path="monitor" element={<MonitorPage />} />
            <Route path="users" element={<AdminOnly><UsersPage /></AdminOnly>} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
