/**
 * Tests de la page de connexion BaolSec (C26).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from '../LoginPage';

// Mock useAuth
const mockLogin = vi.fn();
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ login: mockLogin, user: null, logout: vi.fn() }),
}));

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// Mock l'import de l'asset logo (Vite le résout, jsdom non)
vi.mock('../../assets/logo.jpg', () => ({ default: 'logo.jpg' }));

function wrap(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe('LoginPage', () => {
  it('affiche le titre de connexion', () => {
    wrap(<LoginPage />);
    expect(screen.getByRole('heading', { name: /connexion/i })).toBeInTheDocument();
  });

  it('affiche le logo BaolSec', () => {
    wrap(<LoginPage />);
    expect(screen.getByText('Baol')).toBeInTheDocument();
    expect(screen.getByText('Sec')).toBeInTheDocument();
  });

  it('affiche les cartes de rôle Analyste et Administrateur', () => {
    wrap(<LoginPage />);
    expect(screen.getByText(/analyste/i)).toBeInTheDocument();
    expect(screen.getByText(/administrateur/i)).toBeInTheDocument();
  });

  it('affiche les champs identifiant et mot de passe', () => {
    wrap(<LoginPage />);
    expect(screen.getByPlaceholderText(/admin@baolsec.local/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/••/)).toBeInTheDocument();
  });

  it('affiche le bouton Se connecter', () => {
    wrap(<LoginPage />);
    expect(screen.getByRole('button', { name: /se connecter/i })).toBeInTheDocument();
  });

  it('appelle login() avec les valeurs saisies et redirige vers /app', async () => {
    mockLogin.mockResolvedValueOnce(undefined);
    wrap(<LoginPage />);

    fireEvent.change(screen.getByPlaceholderText(/admin@baolsec.local/i), {
      target: { value: 'analyst@baolsec.sn' },
    });
    fireEvent.change(screen.getByPlaceholderText(/••/), {
      target: { value: 'secret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /se connecter/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('analyst@baolsec.sn', 'secret123');
      expect(mockNavigate).toHaveBeenCalledWith('/app');
    });
  });

  it('affiche un message d\'erreur si les identifiants sont incorrects', async () => {
    mockLogin.mockRejectedValueOnce(new Error('401'));
    wrap(<LoginPage />);

    fireEvent.change(screen.getByPlaceholderText(/admin@baolsec.local/i), {
      target: { value: 'mauvais@test.sn' },
    });
    fireEvent.change(screen.getByPlaceholderText(/••/), {
      target: { value: 'mauvais' },
    });
    fireEvent.click(screen.getByRole('button', { name: /se connecter/i }));

    expect(await screen.findByText(/identifiants incorrects/i)).toBeInTheDocument();
  });

  it('désactive le bouton pendant le chargement', async () => {
    // login ne se résout jamais pendant le test → bouton reste désactivé
    mockLogin.mockReturnValueOnce(new Promise(() => {}));
    wrap(<LoginPage />);

    fireEvent.change(screen.getByPlaceholderText(/admin@baolsec.local/i), {
      target: { value: 'x@x.sn' },
    });
    fireEvent.change(screen.getByPlaceholderText(/••/), {
      target: { value: 'x' },
    });
    fireEvent.click(screen.getByRole('button', { name: /se connecter/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /connexion…/i })).toBeDisabled();
    });
  });
});
