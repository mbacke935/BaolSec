/**
 * Tests du layout d'analyse BaolSec (C23).
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AnalystLayout } from '../AnalystLayout';

function wrap(ui: React.ReactNode, initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      {ui}
    </MemoryRouter>
  );
}

describe('AnalystLayout', () => {
  it('affiche le logo BaolSec', () => {
    wrap(<AnalystLayout><div /></AnalystLayout>);
    expect(screen.getByText('Baol')).toBeInTheDocument();
    expect(screen.getByText('Sec')).toBeInTheDocument();
  });

  it('affiche le badge Analyse', () => {
    wrap(<AnalystLayout><div /></AnalystLayout>);
    expect(screen.getByText('Analyse')).toBeInTheDocument();
  });

  it('affiche tous les liens de navigation', () => {
    wrap(<AnalystLayout><div /></AnalystLayout>);
    expect(screen.getByText('Tableau de bord')).toBeInTheDocument();
    expect(screen.getByText('Incidents')).toBeInTheDocument();
    expect(screen.getByText('Recherche')).toBeInTheDocument();
    expect(screen.getByText('Couverture')).toBeInTheDocument();
  });

  it('affiche l\'email utilisateur si fourni', () => {
    wrap(<AnalystLayout userEmail="analyst@baolsec.sn"><div /></AnalystLayout>);
    expect(screen.getByText('analyst@baolsec.sn')).toBeInTheDocument();
  });

  it('rend le contenu enfant', () => {
    wrap(<AnalystLayout><span data-testid="child">Contenu</span></AnalystLayout>);
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('marque "Tableau de bord" comme actif sur /', () => {
    wrap(<AnalystLayout><div /></AnalystLayout>, '/');
    const link = screen.getByText('Tableau de bord').closest('a');
    // Le lien actif a background:#123a3a défini inline
    expect(link).toHaveStyle({ background: '#123a3a' });
  });

  it('marque "Incidents" comme actif sur /incidents', () => {
    wrap(<AnalystLayout><div /></AnalystLayout>, '/incidents');
    const link = screen.getByText('Incidents').closest('a');
    expect(link).toHaveStyle({ background: '#123a3a' });
  });
});
