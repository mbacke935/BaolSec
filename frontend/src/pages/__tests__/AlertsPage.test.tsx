/**
 * Tests du Centre des alertes (C26).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AlertsPage } from '../AlertsPage';

// Mock de l'API alerts
vi.mock('../../api/analyst', () => ({
  alerts: {
    list: vi.fn().mockResolvedValue([]),
    updateStatus: vi.fn().mockResolvedValue({}),
  },
}));

// Mock useSearch (barre globale)
vi.mock('../../components/AppShell', () => ({
  useSearch: () => '',
}));

// vi.hoisted garantit que mockUseAuth est initialisé avant le hoisting de vi.mock
const { mockUseAuth } = vi.hoisted(() => ({
  mockUseAuth: vi.fn(() => ({
    user: { role: 'ANALYST', email: 'analyst@baolsec.sn' },
    logout: vi.fn(),
  })),
}));
vi.mock('../../hooks/useAuth', () => ({
  useAuth: mockUseAuth,
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AlertsPage', () => {
  beforeEach(() => {
    // Remettre le rôle ANALYST par défaut avant chaque test
    mockUseAuth.mockReset();
    mockUseAuth.mockImplementation(() => ({
      user: { role: 'ANALYST', email: 'analyst@baolsec.sn' },
      logout: vi.fn(),
    }));
  });

  it('affiche le titre', () => {
    wrap(<AlertsPage />);
    expect(screen.getByRole('heading', { name: /centre des alertes/i })).toBeInTheDocument();
  });

  it('affiche les en-têtes du tableau', () => {
    wrap(<AlertsPage />);
    expect(screen.getByText('IDENTIFIANT')).toBeInTheDocument();
    expect(screen.getByText('RÈGLE')).toBeInTheDocument();
    expect(screen.getByText('GRAVITÉ')).toBeInTheDocument();
    expect(screen.getByText('STATUT')).toBeInTheDocument();
    expect(screen.getByText('ANALYSTE')).toBeInTheDocument();
  });

  it('affiche un message quand la liste est vide', async () => {
    wrap(<AlertsPage />);
    expect(await screen.findByText(/aucune alerte/i)).toBeInTheDocument();
  });

  it('affiche les alertes retournées par l\'API', async () => {
    const { alerts } = await import('../../api/analyst');
    (alerts.list as ReturnType<typeof vi.fn>).mockResolvedValueOnce([{
      id: 'alrt-00000001',
      rule_id: 'rule-ssh-brute',
      title: 'SSH brute-force',
      severity: 'haute',
      status: 'nouvelle',
      assigned_to: null,
    }]);
    wrap(<AlertsPage />);
    expect(await screen.findByText('SSH brute-force')).toBeInTheDocument();
  });

  it('affiche un <select> de statut pour un Analyste', async () => {
    const { alerts } = await import('../../api/analyst');
    (alerts.list as ReturnType<typeof vi.fn>).mockResolvedValueOnce([{
      id: 'alrt-00000002',
      rule_id: 'rule-ssh-brute',
      title: 'SSH brute-force',
      severity: 'haute',
      status: 'nouvelle',
      assigned_to: null,
    }]);
    wrap(<AlertsPage />);
    // Le sélecteur de statut doit être présent pour un Analyste
    const selects = await screen.findAllByRole('combobox');
    expect(selects.length).toBeGreaterThan(0);
  });

  it('affiche un statut en lecture seule pour un Admin', async () => {
    // Rôle ADMIN pour ce test
    mockUseAuth.mockImplementation(() => ({
      user: { role: 'ADMIN', email: 'admin@baolsec.local' },
      logout: vi.fn(),
    }));
    const { alerts } = await import('../../api/analyst');
    (alerts.list as ReturnType<typeof vi.fn>).mockResolvedValue([{
      id: 'alrt-00000003',
      rule_id: 'rule-test',
      title: 'Admin-Test-Alert',
      severity: 'basse',
      status: 'nouvelle',
      assigned_to: null,
    }]);
    wrap(<AlertsPage />);
    // L'alerte doit s'afficher…
    await screen.findByText('Admin-Test-Alert');
    // …sans aucun <select> de statut
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});
