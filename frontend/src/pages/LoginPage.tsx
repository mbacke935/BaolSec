/**
 * Connexion BaolSec — carte centrée reprenant la maquette, câblée à la vraie API
 * (login par e-mail → JWT). Le rôle vient du serveur ; les cartes de rôle sont
 * informatives (le masquage d'interface n'est pas un contrôle de sécurité).
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import logo from '../assets/logo.jpg';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(identifier, password);
      navigate('/app');
    } catch {
      setError('Identifiants incorrects');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="auth-logo">
          <img src={logo} alt="BaolSec" />
          <div className="t">Baol<span>Sec</span></div>
        </div>
        <h1>Connexion</h1>
        <p className="sub">Accédez à votre espace de supervision et de détection.</p>

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label className="lbl">Identifiant (e-mail)</label>
            <input
              className="input"
              type="text"
              autoComplete="username"
              placeholder="admin@baolsec.local"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label className="lbl">Mot de passe</label>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <div className="cards" style={{ gridTemplateColumns: '1fr', gap: 10, margin: '6px 0 18px' }}>
            <div className="feature" style={{ padding: 14, borderRadius: 12 }}>
              <h3 style={{ fontSize: 14, margin: '0 0 4px' }}>⚑ Analyste</h3>
              <p style={{ fontSize: 12 }}>Surveille les alertes et la couverture, recherche les événements, investigue et traite les incidents.</p>
            </div>
            <div className="feature" style={{ padding: 14, borderRadius: 12 }}>
              <h3 style={{ fontSize: 14, margin: '0 0 4px' }}>⚙ Administrateur</h3>
              <p style={{ fontSize: 12 }}>Gère les utilisateurs, les sources et les règles, en plus des capacités d'analyse.</p>
            </div>
          </div>

          {error && <p className="auth-err">{error}</p>}

          <button type="submit" className="btn primary" style={{ width: '100%', padding: '12px' }} disabled={loading}>
            {loading ? 'Connexion…' : 'Se connecter'}
          </button>
        </form>

        <p className="auth-note">
          Les droits sont vérifiés par l'API à chaque requête : le masquage dans l'interface
          n'est pas un contrôle de sécurité. Le rôle affiché provient de votre compte.
        </p>
      </div>
    </div>
  );
}
