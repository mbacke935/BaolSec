/**
 * BaolSec Login Page — Design luxe & moderne
 * Glassmorphism · Orbs animés · Logo réel · UX premium
 */
import { useState, type FormEvent, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import './LoginPage.css';

export function LoginPage() {
  const { login, user } = useAuth();
  const [pendingRedirect, setPendingRedirect] = useState(false);
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPwd, setShowPwd] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  // Subtle card tilt on mouse move
  useEffect(() => {
    const card = cardRef.current;
    if (!card) return;
    const onMove = (e: MouseEvent) => {
      const rect = card.getBoundingClientRect();
      const x = (e.clientX - rect.left - rect.width / 2) / rect.width;
      const y = (e.clientY - rect.top - rect.height / 2) / rect.height;
      card.style.transform = `perspective(900px) rotateY(${x * 4}deg) rotateX(${-y * 4}deg)`;
    };
    const onLeave = () => { card.style.transform = ''; };
    document.addEventListener('mousemove', onMove);
    card.addEventListener('mouseleave', onLeave);
    return () => {
      document.removeEventListener('mousemove', onMove);
      card.removeEventListener('mouseleave', onLeave);
    };
  }, []);

  
  // Redirect après login selon le rôle
  useEffect(() => {
    if (pendingRedirect && user) {
      navigate(user.role === 'ADMIN' ? '/admin' : '/dashboard', { replace: true });
    }
  }, [pendingRedirect, user, navigate]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
      setPendingRedirect(true);
    } catch {
      setError('Identifiants invalides. Vérifiez votre email et mot de passe.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="lp-login">
      {/* Background layers */}
      <div className="lp-login-bg">
        <div className="ll-orb ll-orb-1" />
        <div className="ll-orb ll-orb-2" />
        <div className="ll-orb ll-orb-3" />
        <div className="ll-grid" />
      </div>

      {/* Top bar avec logo */}
      <header className="ll-topbar">
        <div className="ll-topbar-logo">
          <img src="/assets/logo.jpg" alt="BaolSec" />
        </div>
        <div className="ll-topbar-badge">
          <span className="ll-badge-dot" />
          Accès sécurisé · Chiffrement TLS 1.3
        </div>
      </header>

      {/* Card centrale */}
      <main className="ll-center">
        <div className="ll-card" ref={cardRef}>
          {/* Glow border effect */}
          <div className="ll-card-glow" />

          {/* En-tête de la card */}
          <div className="ll-card-header">
            <div className="ll-card-logo">
              <img src="/assets/logo.jpg" alt="BaolSec" className="ll-logo-img" />
            </div>
            <h1 className="ll-card-title">Connexion</h1>
            <p className="ll-card-sub">Security Operations Platform</p>
          </div>

          {/* Formulaire */}
          <form onSubmit={handleSubmit} className="ll-form" noValidate>
            {error && (
              <div className="ll-error" role="alert">
                <span className="ll-error-icon">⚠</span>
                <span>{error}</span>
              </div>
            )}

            <div className="ll-field">
              <label className="ll-label" htmlFor="email">
                <span className="ll-label-icon">◎</span>
                Adresse email
              </label>
              <div className="ll-input-wrap">
                <input
                  id="email"
                  className="ll-input"
                  type="email"
                  autoComplete="username"
                  placeholder="analyst@baolsec.io"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={loading}
                />
                <div className="ll-input-line" />
              </div>
            </div>

            <div className="ll-field">
              <label className="ll-label" htmlFor="password">
                <span className="ll-label-icon">◈</span>
                Mot de passe
              </label>
              <div className="ll-input-wrap">
                <input
                  id="password"
                  className="ll-input"
                  type={showPwd ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                />
                <button
                  type="button"
                  className="ll-eye-btn"
                  onClick={() => setShowPwd((v) => !v)}
                  aria-label={showPwd ? 'Masquer' : 'Afficher'}
                  tabIndex={-1}
                >
                  {showPwd ? '◔' : '◉'}
                </button>
                <div className="ll-input-line" />
              </div>
            </div>

            <button
              type="submit"
              className={`ll-submit${loading ? ' loading' : ''}`}
              disabled={loading}
            >
              {loading ? (
                <span className="ll-spinner" />
              ) : (
                <>
                  <span>Se connecter</span>
                  <span className="ll-submit-arrow">→</span>
                </>
              )}
            </button>
          </form>

          {/* Footer card */}
          <div className="ll-card-footer">
            <span className="ll-shield-icon">🛡</span>
            Accès restreint — Personnel autorisé uniquement
          </div>
        </div>

        {/* Stats sous la card */}
        <div className="ll-stats">
          {[
            { val: '99.97%', label: 'Disponibilité' },
            { val: 'TLS 1.3', label: 'Chiffrement' },
            { val: '< 2s', label: 'Détection' },
          ].map((s) => (
            <div className="ll-stat" key={s.label}>
              <span className="ll-stat-val">{s.val}</span>
              <span className="ll-stat-label">{s.label}</span>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
