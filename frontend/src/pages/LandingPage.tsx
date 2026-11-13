/**
 * Landing publique BaolSec — portée à l'identique de la maquette
 * (barre, hero, plateforme, fonctionnalités, approche, appel à l'action, footer).
 */
import { useNavigate } from 'react-router-dom';
import logo from '../assets/logo.jpg';

const FEATURES = [
  { ico: '⌁', h: 'Collecte centralisée', p: "Rassemblez les journaux et événements issus de vos serveurs, postes et équipements réseau." },
  { ico: '◎', h: 'Détection des menaces', p: "Identifiez les activités suspectes grâce à des règles de détection configurables." },
  { ico: '◈', h: 'Corrélation & incidents', p: "Regroupez les alertes liées et facilitez le travail d'investigation." },
  { ico: '▤', h: 'Supervision', p: "Suivez l'état des sources et des composants qui assurent le traitement." },
  { ico: '⌕', h: 'Investigation', p: "Explorez les événements, les preuves et le contexte associé à chaque alerte." },
  { ico: '◷', h: 'Traçabilité', p: "Conservez une lecture chronologique des actions et de l'évolution des incidents." },
];

const APPROACH = [
  { h: 'Pour les analystes', p: "Alertes, investigations, incidents et chronologie dans un espace de travail cohérent." },
  { h: 'Pour les administrateurs', p: "Gestion des sources, des règles, des utilisateurs et de la supervision technique." },
  { h: 'Pour les PME', p: "Une visibilité consolidée sur les signaux de sécurité de l'organisation." },
];

export function LandingPage() {
  const nav = useNavigate();
  const enter = () => nav('/login');

  return (
    <div>
      <header className="top">
        <div className="wrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
          <a className="brand" href="#" onClick={(e) => e.preventDefault()}>
            <img src={logo} alt="Logo BaolSec" />
            <span style={{ color: '#f2f6fa' }}>Baol<span>Sec</span></span>
          </a>
          <nav className="nav">
            <a href="#plateforme">Plateforme</a>
            <a href="#fonctionnalites">Fonctionnalités</a>
            <a href="#approche">Notre approche</a>
          </nav>
          <div className="actions">
            <button className="btn ghost" onClick={enter}>Se connecter</button>
            <button className="btn primary" onClick={enter}>Explorer la démo ↗</button>
          </div>
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="wrap hero-grid">
            <div>
              <div className="eyebrow"><i className="dot" />CYBERSÉCURITÉ • SIEM DISTRIBUÉ</div>
              <h1>Votre sécurité.<br /><em>En pleine maîtrise.</em></h1>
              <p className="lead">
                BaolSec centralise vos événements de sécurité, détecte les comportements suspects
                et vous aide à piloter vos incidents depuis une interface unique.
              </p>
              <div className="hero-buttons">
                <button className="btn primary" onClick={enter}>Découvrir la plateforme →</button>
                <a className="btn" href="#fonctionnalites" style={{ textDecoration: 'none' }}>Voir les fonctionnalités</a>
              </div>
              <div className="proof">
                <span>Visibilité centralisée</span>
                <span>Détection structurée</span>
                <span>Suivi des incidents</span>
              </div>
            </div>
            <div className="visual">
              <img className="logo-large" src={logo} alt="Logo officiel BaolSec" />
              <div className="float f1">Événements supervisés<b>24,8 M</b><span style={{ color: 'var(--green2)' }}>Flux de démonstration</span></div>
              <div className="float f2">État de la plateforme<b style={{ color: 'var(--green2)' }}>Opérationnelle</b></div>
            </div>
          </div>
        </section>

        <section className="section" id="plateforme">
          <div className="wrap">
            <div className="section-head">
              <div className="kicker">Une plateforme unifiée</div>
              <h2>De l'événement à l'incident.</h2>
              <p>Une chaîne de traitement pensée pour donner aux équipes une lecture claire de leur environnement de sécurité.</p>
            </div>
            <div className="band">
              <div>
                <h2>Une vision claire de votre posture de sécurité.</h2>
                <p>Centralisez les signaux, priorisez les alertes et suivez les investigations.</p>
              </div>
              <button className="btn primary" onClick={enter}>Ouvrir la démo →</button>
            </div>
          </div>
        </section>

        <section className="section" id="fonctionnalites">
          <div className="wrap">
            <div className="section-head">
              <div className="kicker">Capacités principales</div>
              <h2>La sécurité, sans perdre le fil.</h2>
              <p>Des outils opérationnels pour analyser, comprendre et agir.</p>
            </div>
            <div className="cards">
              {FEATURES.map((f) => (
                <div className="feature" key={f.h}>
                  <div className="ico">{f.ico}</div>
                  <h3>{f.h}</h3>
                  <p>{f.p}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="section" id="approche">
          <div className="wrap">
            <div className="section-head">
              <div className="kicker">Conçue pour les équipes</div>
              <h2>Comprendre. Prioriser. Répondre.</h2>
              <p>BaolSec met l'information utile au premier plan, avec une interface conçue pour les analystes et les administrateurs.</p>
            </div>
            <div className="cards">
              {APPROACH.map((f) => (
                <div className="feature" key={f.h}>
                  <h3>{f.h}</h3>
                  <p>{f.p}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <div className="band">
              <div>
                <div className="kicker">Passez à l'action</div>
                <h2>Découvrez BaolSec en situation.</h2>
                <p>Explorez une démonstration interactive avec des données réelles de votre instance.</p>
              </div>
              <button className="btn primary" onClick={enter}>Lancer la démonstration →</button>
            </div>
          </div>
        </section>
      </main>

      <footer className="footer">
        <div className="wrap">
          <div>© 2026 BaolSec. Tous droits réservés.</div>
          <div>Plateforme de supervision et de détection de sécurité.</div>
        </div>
      </footer>
    </div>
  );
}
