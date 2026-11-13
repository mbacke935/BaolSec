/**
 * Tests de l'interface Admin (C22).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock useAuth
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'admin@test.local', role: 'ADMIN', is_active: true, created_at: '', updated_at: '' },
    logout: vi.fn(),
  }),
}));

import { AdminLayout } from '../AdminLayout';

describe('AdminLayout', () => {
  it('affiche les liens de navigation', () => {
    render(
      <MemoryRouter initialEntries={['/sources']}>
        <AdminLayout><div>Contenu</div></AdminLayout>
      </MemoryRouter>
    );
    expect(screen.getByText(/Sources/i)).toBeDefined();
    expect(screen.getByText(/Règles/i)).toBeDefined();
    expect(screen.getByText(/Utilisateurs/i)).toBeDefined();
  });

  it('affiche l\'email de l\'utilisateur connecté', () => {
    render(
      <MemoryRouter initialEntries={['/sources']}>
        <AdminLayout><div /></AdminLayout>
      </MemoryRouter>
    );
    expect(screen.getByText('admin@test.local')).toBeDefined();
  });

  it('affiche le contenu enfant', () => {
    render(
      <MemoryRouter initialEntries={['/sources']}>
        <AdminLayout><div data-testid="child">Enfant</div></AdminLayout>
      </MemoryRouter>
    );
    expect(screen.getByTestId('child')).toBeDefined();
  });
});
