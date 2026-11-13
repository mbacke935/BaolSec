/**
 * Tests de la page Tableau de bord (C23).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DashboardPage } from '../DashboardPage';

// Mock de l'API analyst
vi.mock('../../api/analyst', () => ({
  incidents: {
    list: vi.fn().mockResolvedValue([
      {
        id: 1,
        title: 'Intrusion détectée',
        severity: 'CRITIQUE',
        state: 'OUVERT',
        opened_at: '2024-01-01T10:00:00Z',
        alert_count: 3,
      },
    ]),
  },
  coverage: {
    list: vi.fn().mockResolvedValue([
      { source_id: 1, source_name: 'Firewall', normalization_rate: 0.92, event_count: 5000 },
    ]),
  },
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('DashboardPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('affiche le titre de la page', () => {
    wrap(<DashboardPage />);
    expect(screen.getByText(/tableau de bord/i)).toBeInTheDocument();
  });

  it('affiche les KPI cards', () => {
    wrap(<DashboardPage />);
    // Les KPIs sont toujours présents (même en chargement).
    // « Incidents ouverts » apparaît aussi comme titre de section → getAllByText.
    expect(screen.getAllByText(/incidents ouverts/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/critiques/i)).toBeInTheDocument();
    expect(screen.getByText(/sources actives/i)).toBeInTheDocument();
  });
});
