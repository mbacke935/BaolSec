/**
 * Page d'accueil publique : ce que fait BaolSec, comment, et pour qui.
 * Contenu factuel, tiré du cadrage et de la conception : aucun chiffre ni client inventé.
 * Aucune ressource externe (polices et images servies par la plateforme elle-même).
 */
import { Link } from 'react-router-dom';
import { homeFor, useAuth } from '../auth/AuthContext';
import {
  IconAudit, IconBell, IconFlame, IconLayers, IconLock, IconPulse, IconRadar, IconRule, IconSearch, IconServer, IconShield, IconUsers,
} from '../components/icons';
import './LandingPage.css';

const PIPELINE = [
  { n: '01', title: 'Collecte', text: 'Les agents Fluent Bit envoient en HTTPS avec un jeton par source ; les équipements réseau en Syslog sur TLS. Chaque lot est authentifié et horodaté à la réception.' },
  { n: '02', title: 'Normalisation', text: 'Chaque ligne est analysée et convertie au format ECS : utilisateur, adresse IP, hôte, action et résultat se lisent de la même façon quelle que soit la source.' },
  { n: '03', title: 'Détection', text: 'Des règles YAML versionnées évaluent chaque événement : correspondance simple ou seuil sur une fenêtre de temps, regroupé par utilisateur, IP ou hôte.' },
  { n: '04', title: 'Corrélation', text: 'Les alertes qui partagent un utilisateur, une adresse ou un hôte dans la même fenêtre sont regroupées en un incident unique, avec la justification du regroupement.' },
  { n: '05', title: 'Investigation', text: 'L’analyste prend l’incident en charge, consulte les événements à l’origine de chaque alerte, commente et clôt avec une conclusion tracée.' },
];

const FEATURES = [
  { icon: IconBell, title: 'Alertes expliquées', text: 'Chaque alerte renvoie aux événements qui l’ont déclenchée et au message d’origine, tel que reçu.' },
  { icon: IconFlame, title: 'Incidents corrélés', text: 'Moins de bruit : une attaque par force brute suivie d’une connexion réussie forme un seul dossier, pas dix alertes.' },
  { icon: IconRadar, title: 'Couverture des sources', text: 'Une source qui se tait est signalée, avec la liste des règles qui ne peuvent plus rien détecter.' },
  { icon: IconSearch, title: 'Recherche d’événements', text: 'Par période, source, utilisateur, adresse IP ou hôte, et en syntaxe Lucene pour les requêtes avancées.' },
  { icon: IconRule, title: 'Règles versionnées', text: 'Format YAML validé par le serveur ; chaque modification crée une version consultable et attribuée.' },
  { icon: IconPulse, title: 'Supervision intégrée', text: 'État de chaque service, retard des files de messages et file de rejet visibles depuis l’interface.' },
];

export function LandingPage() {
  const { user } = useAuth();
  const target = user ? homeFor(user.role) : '/login';
  const cta = user ? 'Ouvrir la console' : 'Se connecter';

  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="lp-wrap lp-nav__in">
          <Link to="/" className="lp-brand"><img src="/assets/logo-mark.png" alt="" /><span>Baol<b>Sec</b></span></Link>
          <nav className="lp-nav__links" aria-label="Sections">
            <a href="#chaine">Fonctionnement</a><a href="#fonctions">Fonctions</a><a href="#roles">Rôles</a><a href="#securite">Sécurité</a>
          </nav>
          <Link to={target} className="btn primary">{cta}</Link>
        </div>
      </header>

      <section className="lp-hero">
        <div className="lp-wrap lp-hero__in">
          <p className="lp-kicker">SIEM distribué · auto-hébergé</p>
          <h1>Voir ce qui se passe sur votre système d’information, <span>et ce que vous ne voyez plus.</span></h1>
          <p className="lp-lead">
            BaolSec centralise les journaux de vos serveurs, postes, pare-feu et applications, détecte les comportements
            suspects, les regroupe en incidents et vous prévient quand une source cesse d’émettre.
          </p>
          <div className="lp-hero__cta">
            <Link to={target} className="btn primary lg">{cta}</Link>
            <a href="#chaine" className="btn lg">Comment ça marche</a>
          </div>
          <ul className="lp-hero__facts">
            <li><IconServer />Linux, Windows, pare-feu, applications web</li>
            <li><IconLayers />Événements normalisés au format ECS</li>
            <li><IconLock />Données hébergées chez vous</li>
          </ul>
        </div>
      </section>

      <section id="chaine" className="lp-section">
        <div className="lp-wrap">
          <div className="lp-head">
            <p className="lp-kicker">Fonctionnement</p>
            <h2>Du journal brut à l’incident instruit</h2>
            <p>Cinq étapes, chacune assurée par un service indépendant relié aux autres par une file de messages persistante : si un service s’arrête, les messages attendent au lieu d’être perdus.</p>
          </div>
          <ol className="lp-pipeline">
            {PIPELINE.map((s) => (
              <li key={s.n}><span className="lp-pipeline__n">{s.n}</span><h3>{s.title}</h3><p>{s.text}</p></li>
            ))}
          </ol>
        </div>
      </section>

      <section id="fonctions" className="lp-section lp-section--alt">
        <div className="lp-wrap">
          <div className="lp-head">
            <p className="lp-kicker">Fonctions</p>
            <h2>Ce que l’équipe sécurité a sous la main</h2>
          </div>
          <div className="lp-features">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <article key={title} className="lp-feature"><div className="lp-feature__ico"><Icon /></div><h3>{title}</h3><p>{text}</p></article>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-section">
        <div className="lp-wrap lp-split">
          <div className="lp-split__img" style={{ backgroundImage: "url('/assets/shield.webp')" }} role="img" aria-label="Bouclier traversé par un signal" />
          <div className="lp-split__text">
            <p className="lp-kicker">Angles morts</p>
            <h2>Un silence est aussi une information</h2>
            <p>
              Un agent arrêté, un certificat expiré ou une règle de pare-feu modifiée suffisent à couper une source.
              Sans alerte, personne ne s’en aperçoit, et les règles qui en dépendent cessent de détecter.
            </p>
            <ul className="lp-checks">
              <li>Seuil de silence propre à chaque source</li>
              <li>Distinction entre source silencieuse et flux reçu mais non traité</li>
              <li>Liste des règles de détection privées de données, avec la cause</li>
              <li>Historique de chaque changement d’état</li>
            </ul>
          </div>
        </div>
      </section>

      <section id="roles" className="lp-section lp-section--alt">
        <div className="lp-wrap">
          <div className="lp-head">
            <p className="lp-kicker">Rôles</p>
            <h2>Deux rôles, des droits séparés</h2>
            <p>Les droits sont vérifiés par le serveur à chaque requête, pas seulement masqués dans l’interface.</p>
          </div>
          <div className="lp-roles">
            <article className="lp-role">
              <div className="lp-role__head"><IconShield /><h3>Analyste</h3></div>
              <ul>
                <li>Tableau de bord des alertes et incidents à traiter</li>
                <li>Prise en charge, attribution, commentaires, clôture et réouverture</li>
                <li>Recherche dans les événements et consultation de la couverture</li>
                <li>Lecture des sources et des règles</li>
              </ul>
            </article>
            <article className="lp-role">
              <div className="lp-role__head"><IconUsers /><h3>Administrateur</h3></div>
              <ul>
                <li>Comptes utilisateurs, verrouillage et déverrouillage</li>
                <li>Déclaration des sources et de leurs identifiants d’ingestion</li>
                <li>Règles de détection et paramètres de corrélation</li>
                <li>Journal d’audit, supervision et file de rejet</li>
              </ul>
            </article>
          </div>
        </div>
      </section>

      <section id="securite" className="lp-section">
        <div className="lp-wrap lp-split lp-split--rev">
          <div className="lp-split__text">
            <p className="lp-kicker">Sécurité</p>
            <h2>Une plateforme de sécurité qui s’applique ses propres règles</h2>
            <ul className="lp-sec">
              <li><IconLock /><div><strong>Échanges chiffrés</strong><span>HTTPS pour l’interface et la collecte, Syslog sur TLS, mots de passe hachés avec Argon2.</span></div></li>
              <li><IconShield /><div><strong>Comptes protégés</strong><span>Verrouillage temporaire après plusieurs échecs, sessions courtes, limitation du débit des requêtes.</span></div></li>
              <li><IconAudit /><div><strong>Traçabilité</strong><span>Connexions, refus et modifications enregistrés avec l’auteur, la cible et l’adresse d’origine.</span></div></li>
              <li><IconServer /><div><strong>Souveraineté</strong><span>Déploiement Docker Compose sur votre infrastructure, sauvegardes PostgreSQL et instantanés OpenSearch.</span></div></li>
            </ul>
          </div>
          <div className="lp-split__img" style={{ backgroundImage: "url('/assets/soc-room.webp')" }} role="img" aria-label="Salle de supervision de sécurité" />
        </div>
      </section>

      <section className="lp-cta">
        <div className="lp-wrap lp-cta__in">
          <h2>Accéder à la console BaolSec</h2>
          <p>Les comptes sont créés par un administrateur de la plateforme.</p>
          <Link to={target} className="btn primary lg">{cta}</Link>
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-wrap lp-foot__in">
          <span className="lp-brand small"><img src="/assets/logo-mark.png" alt="" /><span>Baol<b>Sec</b></span></span>
          <span>SIEM distribué · collecte, détection, corrélation, couverture</span>
        </div>
      </footer>
    </div>
  );
}
