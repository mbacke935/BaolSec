/** Connexion (C3 4.6, ES-01) : e-mail ou nom d'utilisateur, messages explicites, verrouillage signalé. */
import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { errorMessage } from '../api/client';
import { homeFor, useAuth } from '../auth/AuthContext';
import { IconArrowLeft, IconEye, IconEyeOff, IconLock, IconShield } from '../components/icons';
import './LoginPage.css';

export function LoginPage() {
  const { user, login, expired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);   // relance l'animation d'erreur à chaque essai

  if (user && !busy) return <Navigate to={from && from !== '/login' ? from : homeFor(user.role)} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!identifier.trim() || !password) {
      setError('Saisissez votre identifiant et votre mot de passe.');
      setAttempt((n) => n + 1);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const me = await login(identifier.trim(), password);
      navigate(from && from !== '/login' ? from : homeFor(me.role), { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'Connexion impossible.'));
      setAttempt((n) => n + 1);
      setPassword('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login__aside">
        <Link to="/" className="login__back"><IconArrowLeft /> Retour à l'accueil</Link>
        <div className="login__pitch">
          <img src="/assets/logo-mark.png" alt="" className="login__mark" />
          <h1>Le poste de travail du SOC</h1>
          <p>Alertes, incidents corrélés, recherche d'événements et couverture des sources, au même endroit.</p>
          <ul>
            <li><IconShield /> Droits vérifiés par le serveur à chaque action</li>
            <li><IconLock /> Compte verrouillé temporairement après plusieurs échecs</li>
            <li><IconShield /> Chaque connexion et chaque action sensible sont tracées</li>
          </ul>
        </div>
        <p className="login__foot">BaolSec · SIEM distribué</p>
      </div>

      <main className="login__main">
        <form className="login__card" onSubmit={submit} noValidate>
          <h2>Connexion</h2>
          <p className="login__lead">Utilisez le compte fourni par votre administrateur.</p>

          {expired && !error && <div className="login__msg info">Votre session a expiré : reconnectez-vous.</div>}
          {error && <div key={attempt} className="login__msg error shake" role="alert">{error}</div>}

          <label className="login__field">
            <span>Adresse e-mail ou identifiant</span>
            <input className="input" autoComplete="username" autoFocus value={identifier}
              onChange={(e) => setIdentifier(e.target.value)} placeholder="prenom.nom@entreprise.sn" />
          </label>
          <label className="login__field">
            <span>Mot de passe</span>
            <div className="login__pw">
              <input className="input" type={show ? 'text' : 'password'} autoComplete="current-password" value={password}
                onChange={(e) => setPassword(e.target.value)} />
              <button type="button" className="btn ghost icon" onClick={() => setShow((s) => !s)}
                aria-label={show ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}>{show ? <IconEyeOff /> : <IconEye />}</button>
            </div>
          </label>
          <button className="btn primary login__submit" type="submit" disabled={busy}>
            {busy && <span className="spinner" />}{busy ? 'Connexion…' : 'Se connecter'}
          </button>
          <p className="login__note">Mot de passe oublié ou compte verrouillé ? Contactez un administrateur BaolSec.</p>
        </form>
      </main>
    </div>
  );
}
