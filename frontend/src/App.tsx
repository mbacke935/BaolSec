/**
 * Application BaolSec : page publique, connexion, interfaces Analyste (C23) et Administrateur (C22).
 * Les droits sont appliqués par l'API (ES-03) ; les routes ne font que diriger chaque rôle vers ses écrans.
 */
import type { ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AuthProvider, RequireAuth, homeFor, useAuth } from './auth/AuthContext';
import { AppShell } from './components/AppShell';
import { ToastProvider } from './components/ui';
import type { UserRole } from './types/api';

import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { AlertsPage } from './pages/AlertsPage';
import { IncidentsListPage } from './pages/IncidentsListPage';
import { IncidentDetailPage } from './pages/IncidentDetailPage';
import { EventsPage } from './pages/EventsPage';
import { SearchPage } from './pages/SearchPage';
import { CoveragePage } from './pages/CoveragePage';
import { MonitorPage } from './pages/MonitorPage';
import { AdminOverviewPage } from './pages/AdminOverviewPage';
import { SourcesPage } from './pages/SourcesPage';
import { RulesPage } from './pages/RulesPage';
import { UsersPage } from './pages/UsersPage';
import { SettingsPage } from './pages/SettingsPage';
import { AuditPage } from './pages/AuditPage';
import { DlqPage } from './pages/DlqPage';

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 15_000, refetchOnWindowFocus: false } },
});

const BOTH: UserRole[] = ['ADMIN', 'ANALYST'];

function Screen({ roles = BOTH, children }: { roles?: UserRole[]; children: ReactNode }) {
  return <RequireAuth roles={roles}><AppShell>{children}</AppShell></RequireAuth>;
}

function Home() {
  const { user } = useAuth();
  return <Navigate to={homeFor(user?.role)} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/app" element={<RequireAuth><Home /></RequireAuth>} />

      {/* Analyse (Analyste : traitement ; Administrateur : lecture, matrice C2 §3) */}
      <Route path="/dashboard" element={<Screen roles={['ANALYST']}><DashboardPage /></Screen>} />
      <Route path="/alerts" element={<Screen><AlertsPage /></Screen>} />
      <Route path="/incidents" element={<Screen><IncidentsListPage /></Screen>} />
      <Route path="/incidents/:id" element={<Screen><IncidentDetailPage /></Screen>} />
      <Route path="/events" element={<Screen><EventsPage /></Screen>} />
      <Route path="/search" element={<Screen><SearchPage /></Screen>} />
      <Route path="/coverage" element={<Screen><CoveragePage /></Screen>} />
      <Route path="/monitor" element={<Screen><MonitorPage /></Screen>} />

      {/* Référentiel : écriture Administrateur, lecture Analyste */}
      <Route path="/sources" element={<Screen><SourcesPage /></Screen>} />
      <Route path="/rules" element={<Screen><RulesPage /></Screen>} />

      {/* Administration */}
      <Route path="/admin" element={<Screen roles={['ADMIN']}><AdminOverviewPage /></Screen>} />
      <Route path="/users" element={<Screen roles={['ADMIN']}><UsersPage /></Screen>} />
      <Route path="/settings" element={<Screen roles={['ADMIN']}><SettingsPage /></Screen>} />
      <Route path="/audit" element={<Screen roles={['ADMIN']}><AuditPage /></Screen>} />
      <Route path="/dlq" element={<Screen roles={['ADMIN']}><DlqPage /></Screen>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <AppRoutes />
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
