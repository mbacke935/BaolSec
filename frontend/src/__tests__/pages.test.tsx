import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('../api/endpoints', () => ({
  auth: { login: vi.fn(), me: vi.fn(), logout: vi.fn() },
  alerts: { list: vi.fn(), get: vi.fn(), setStatus: vi.fn(), assign: vi.fn() },
  incidents: { list: vi.fn() },
  coverage: { list: vi.fn() },
  sources: { create: vi.fn(), newToken: vi.fn(), addCertificate: vi.fn() },
}));

import * as api from '../api/endpoints';
import { AuthProvider } from '../auth/AuthContext';
import { ToastProvider } from '../components/ui';
import { LoginPage } from '../pages/LoginPage';
import { AlertsPage } from '../pages/AlertsPage';
import { SourceWizard } from '../pages/SourceWizard';

function wrap(ui: ReactNode, path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><ToastProvider><AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route path="*" element={ui} /></Routes>
      </MemoryRouter>
    </AuthProvider></ToastProvider></QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('Connexion', () => {
  it('demande les deux champs avant d’appeler l’API', async () => {
    wrap(<LoginPage />, '/login');
    await userEvent.click(screen.getByRole('button', { name: 'Se connecter' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Saisissez votre identifiant et votre mot de passe.');
    expect(api.auth.login).not.toHaveBeenCalled();
  });

  it('affiche le message du serveur en cas d’échec', async () => {
    vi.mocked(api.auth.login).mockRejectedValue(Object.assign(new Error('x'), {
      isAxiosError: true, response: { status: 401, data: { detail: 'Identifiants invalides' } },
    }));
    wrap(<LoginPage />, '/login');
    await userEvent.type(screen.getByPlaceholderText('prenom.nom@entreprise.sn'), 'analyste');
    await userEvent.type(document.querySelector('input[type=password]')!, 'mauvais');
    await userEvent.click(screen.getByRole('button', { name: 'Se connecter' }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(api.auth.login).toHaveBeenCalledWith('analyste', 'mauvais');
  });
});

describe('Alertes', () => {
  it('liste les alertes avec leurs libellés français et le lien vers l’incident', async () => {
    vi.mocked(api.alerts.list).mockResolvedValue([{
      id: 'a1b2c3d4e5f6a7b8', rule_id: 'r', rule_code: 'AUTH-001', severity: 'elevee', status: 'nouvelle', assigned_to: null,
      assigned_to_name: null, incident_id: 'i1', incident_title: 'Force brute sur un compte — bob', title: 'Force brute sur un compte',
      detail: {}, fired_at: new Date().toISOString(),
    }]);
    wrap(<AlertsPage />, '/alerts');
    expect(await screen.findAllByText('Force brute sur un compte')).not.toHaveLength(0);
    expect(screen.getAllByText('Élevée').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: 'Force brute sur un compte — bob' })).toHaveAttribute('href', '/incidents/i1');
  });
});

describe('Ajout d’une source', () => {
  it('refuse un nom invalide puis déclare la source et génère le jeton', async () => {
    vi.mocked(api.sources.create).mockResolvedValue({
      id: 's1', name: 'srv-web-01', description: null, type: 'linux', active: true, silence_threshold_s: 900,
      config: { transport: 'https', ingestion_mode: 'direct', host: null, criticality: null, expected_min_events_per_h: null, hostname: null, ip_address: null, environment: 'production', tags: [], responsible: null },
      created_at: '', updated_at: '',
    });
    vi.mocked(api.sources.newToken).mockResolvedValue({ credential_id: 'c1', created_at: '', token: 'bsk_test_token', note: '' });
    wrap(<SourceWizard onClose={() => undefined} />);
    await userEvent.type(screen.getByPlaceholderText('srv-web-01'), 'nom invalide');
    await userEvent.click(screen.getByRole('button', { name: 'Continuer' }));
    expect(screen.getByRole('alert')).toHaveTextContent('sans espace');
    await userEvent.clear(screen.getByPlaceholderText('srv-web-01'));
    await userEvent.type(screen.getByPlaceholderText('srv-web-01'), 'srv-web-01');
    await userEvent.click(screen.getByRole('button', { name: 'Continuer' }));
    await userEvent.click(screen.getByRole('button', { name: 'Déclarer la source' }));
    await waitFor(() => expect(api.sources.create).toHaveBeenCalled());
    expect(vi.mocked(api.sources.create).mock.calls[0][0]).toMatchObject({ name: 'srv-web-01', type: 'linux', silence_threshold_s: 900 });
    await userEvent.click(await screen.findByRole('button', { name: /Générer le jeton/ }));
    expect(await screen.findByText('bsk_test_token')).toBeInTheDocument();
  });
});

