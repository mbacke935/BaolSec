/**
 * Tests de la page Recherche OpenSearch (C23).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { SearchPage } from '../SearchPage';

vi.mock('../../api/analyst', () => ({
  search: {
    query: vi.fn().mockResolvedValue({ hits: { total: { value: 0 }, hits: [] } }),
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

describe('SearchPage', () => {
  it('affiche le titre', () => {
    wrap(<SearchPage />);
    // Cibler le titre (h1) : « Recherche » matche aussi le bouton « Rechercher ».
    expect(screen.getByRole('heading', { name: /recherche/i })).toBeInTheDocument();
  });

  it('affiche les options d\'index', () => {
    wrap(<SearchPage />);
    // Les index sont des boutons en français (Événements / Alertes / Incidents).
    expect(screen.getByRole('button', { name: /événements/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /alertes/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /incidents/i })).toBeInTheDocument();
  });

  it('affiche un champ de requête Lucene', () => {
    wrap(<SearchPage />);
    const input = screen.getByPlaceholderText(/lucene/i);
    expect(input).toBeInTheDocument();
  });

  it('permet de saisir une requête', () => {
    wrap(<SearchPage />);
    const input = screen.getByPlaceholderText(/lucene/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'severity:CRITIQUE' } });
    expect(input.value).toBe('severity:CRITIQUE');
  });
});
