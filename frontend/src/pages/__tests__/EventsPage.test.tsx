/**
 * Tests de la page Flux d'événements (C26).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { EventsPage } from '../EventsPage';

// Mock de l'API search
vi.mock('../../api/analyst', () => ({
  search: {
    events: vi.fn().mockResolvedValue({ hits: [], total: 0 }),
  },
}));

// Mock du hook useSearch (barre de recherche globale de l'AppShell)
vi.mock('../../components/AppShell', () => ({
  useSearch: () => '',
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('EventsPage', () => {
  it('affiche le titre de la page', () => {
    wrap(<EventsPage />);
    expect(screen.getByRole('heading', { name: /flux d'événements/i })).toBeInTheDocument();
  });

  it('affiche les en-têtes du tableau', () => {
    wrap(<EventsPage />);
    expect(screen.getByText('HORODATAGE')).toBeInTheDocument();
    expect(screen.getByText('SOURCE')).toBeInTheDocument();
    expect(screen.getByText('TYPE')).toBeInTheDocument();
    expect(screen.getByText('RÉSULTAT')).toBeInTheDocument();
  });

  it('affiche un message quand aucun événement n\'est trouvé', async () => {
    wrap(<EventsPage />);
    // La requête retourne [] → ligne "Aucun événement"
    expect(await screen.findByText(/aucun événement/i)).toBeInTheDocument();
  });

  it('affiche les données d\'un événement retourné par l\'API', async () => {
    const { search } = await import('../../api/analyst');
    (search.events as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      total: 1,
      hits: [{
        _id: 'evt-001',
        '@timestamp': '2026-11-17T22:00:00Z',
        'source': { name: 'srv-test' },
        'event': { action: 'login', outcome: 'success' },
      }],
    });
    wrap(<EventsPage />);
    expect(await screen.findByText('srv-test')).toBeInTheDocument();
    expect(screen.getByText('login')).toBeInTheDocument();
    expect(screen.getByText('success')).toBeInTheDocument();
  });

  it('affiche le total de résultats quand la requête aboutit', async () => {
    const { search } = await import('../../api/analyst');
    (search.events as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      total: 42,
      hits: [],
    });
    wrap(<EventsPage />);
    expect(await screen.findByText(/42 résultat/i)).toBeInTheDocument();
  });
});
