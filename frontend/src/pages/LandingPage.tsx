/**
 * BaolSec Landing Page — Design luxe & moderne
 * Glassmorphism · Animations · Transparences · Images cybersécurité
 */
import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import './LandingPage.css';

const FEATURES = [
  {
    ico: '⌁',
    h: 'Collecte centralisée',
    p: 'Rassemblez les journaux et événements issus de vos serveurs, postes et équipements réseau en temps réel.',
    tag: 'INGESTION',
  },
  {
    ico: '◎',
    h: 'Détection des menaces',
    p: 'Identifiez les activités suspectes grâce à des règles de détection configurables et du machine learning.',
    tag: 'DETECTION',
  },
  {
    ico: '◈',
    h: 'Corrélation & incidents',
    p: 'Regroupez les alertes liées et facilitez le travail d\'investigation avec une vue chronologique complète.',
    tag: 'CORRELATION',
  },
  {
    ico: '▤',
    h: 'Supervision temps réel',
    p: 'Suivez l\'état des sources et des composants qui assurent le traitement de votre infrastructure.',
    tag: 'MONITORING',
  },
  {
    ico: '⌕',
    h: 'Investigation forensique',
    p: 'Explorez les événements, les preuves et le contexte associé à chaque alerte avec un moteur de recherche puissant.',
    tag: 'INVESTIGATION',
  },
  {
    ico: '◷',
    h: 'Traçabilité complète',
    p: 'Conservez une lecture chronologique des actions et de l\'évolution des incidents pour l\'audit et la conformité.',
    tag: 'AUDIT',
  },
];

const APPROACH = [
  {
    h: 'Pour les analystes SOC',
    p: 'Alertes, investigations, incidents et chronologie dans un espace de travail cohérent et ergonomique.',
    img: '/assets/Gemini_Generated_Image_yfy78kyfy78kyfy7(1).jpeg',
  },
  {
    h: 'Pour les équipes sécurité',
    p: 'Gestion centralisée des sources, des règles de détection, des utilisateurs et de la supervision technique.',
    img: '/assets/Gemini_Generated_Image_yfy78kyfy78kyfy7(4).jpeg',
  },
  {
    h: 'Pour les organisations',
    p: 'Une visibilité consolidée sur l\'ensemble des signaux de sécurité avec reporting et conformité intégrés.',
    img: '/assets/Luxury_dark_cybersecurity_SIEM_hero_background__deep_navy_bl.png',
  },
];

const LOG_LINES = [
  { ts: '03:47:12.441', lvl: 'CRIT', cls: 'lvl-crit', msg: 'Brute-force SSH détecté — <em>192.168.1.47</em> → <span class="hi">10.0.0.3</span> (248 tentatives/min)' },
  { ts: '03:47:13.002', lvl: 'WARN', cls: 'lvl-warn', msg: 'Exfiltration suspecte — <em>proc:chrome</em> → <span class="hi">external:443</span> 48 MB' },
  { ts: '03:47:14.118', lvl: 'INFO', cls: 'lvl-info', msg: 'Règle SIGMA <em>T1110.001</em> corrélée — incident <span class="hi">#INC-2847</span> créé' },
  { ts: '03:47:15.330', lvl: 'OK',   cls: 'lvl-ok',   msg: 'Agent <em>linux-prod-07</em> — flux normalisé, <span class="hi">3 412</span> événements indexés' },
  { ts: '03:47:16.891', lvl: 'CRIT', cls: 'lvl-crit', msg: 'Lateral movement — <em>WIN-DC01</em> → <span class="hi">WIN-SRV04</span> Pass-the-Hash' },
  { ts: '03:47:17.204', lvl: 'INFO', cls: 'lvl-info', msg: 'Couverture MITRE ATT&CK — <span class="hi">67 %</span> des tactiques surveillées' },
];

export function LandingPage() {
  const nav = useNavigate();
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    // Nav scroll effect
    const onScroll = () => {
      if (navRef.current) {
        navRef.current.classList.toggle('scrolled', window.scrollY > 40);
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });

    // Scroll reveal
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.target.classList.toggle('visible', e.isIntersecting)),
      { threshold: 0.12 }
    );
    document.querySelectorAll('.reveal').forEach((el) => observer.observe(el));

    // Animated counters
    const counters = document.querySelectorAll<HTMLElement>('[data-count]');
    counters.forEach((el) => {
      const target = parseFloat(el.dataset.count || '0');
      const suffix = el.dataset.suffix || '';
      const decimals = el.dataset.dec ? parseInt(el.dataset.dec) : 0;
      let start = 0;
      const duration = 2000;
      const step = (timestamp: number) => {
        if (!start) start = timestamp;
        const progress = Math.min((timestamp - start) / duration, 1);
        const val = target * (1 - Math.pow(1 - progress, 3));
        el.textContent = val.toFixed(decimals) + suffix;
        if (progress < 1) requestAnimationFrame(step);
      };
      const obs2 = new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting) { requestAnimationFrame(step); obs2.disconnect(); }
      });
      obs2.observe(el);
    });

    return () => {
      window.removeEventListener('scroll', onScroll);
      observer.disconnect();
    };
  }, []);

  return (
    <div className="lp">
      {/* ── NAV ── */}
      <nav className="lp-nav" ref={navRef}>
        <div className="lp-nav-logo">
          <img src="/assets/logo.jpg" alt="BaolSec" />
        </div>
        <div className="lp-nav-links">
          <a href="#plateforme">Plateforme</a>
          <a href="#fonctionnalites">Fonctionnalités</a>
          <a href="#approche">Notre approche</a>
        </div>
        <div className="lp-nav-actions">
          <button className="lp-btn-ghost" onClick={() => nav('/login')}>Se connecter</button>
          <button className="lp-btn-cta" onClick={() => nav('/login')}>Accéder à la plateforme →</button>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className="lp-hero">
        <div className="lp-hero-bg" style={{ overflow: "hidden" }}>
          <img src="/assets/Futuristic_global_threat_map_visualization__dark_background_.png" alt="" className="lp-hero-img" />
          <div className="lp-orb lp-orb-1" />
          <div className="lp-orb lp-orb-2" />
          <div className="lp-orb lp-orb-3" />
          <div className="lp-grid" />
        </div>
        <div className="lp-hero-content">
          <div className="lp-badge">
            <span className="lp-badge-dot" />
            CYBERSÉCURITÉ · SIEM DISTRIBUÉ · DÉTECTION TEMPS RÉEL
          </div>
          <h1 className="lp-hero-title">
            Votre sécurité.<br />
            <span className="lp-gradient-text">En pleine maîtrise.</span>
          </h1>
          <p className="lp-hero-sub">
            BaolSec centralise vos événements de sécurité, détecte les comportements suspects
            et vous aide à piloter vos incidents depuis une interface unique et puissante.
          </p>
          <div className="lp-hero-actions">
            <button className="lp-btn-primary" onClick={() => nav('/login')}>
              <span>Accéder à la plateforme</span>
              <span className="lp-btn-arrow">→</span>
            </button>
            <button className="lp-btn-secondary" onClick={() => document.getElementById('fonctionnalites')?.scrollIntoView({ behavior: 'smooth' })}>
              Voir les fonctionnalités
            </button>
          </div>
          <div className="lp-hero-stats">
            {[
              { num: '24.8', suffix: 'M', label: 'Événements supervisés', dec: '1' },
              { num: '99.97', suffix: '%', label: 'Disponibilité garantie', dec: '2' },
              { num: '< 2', suffix: 's', label: 'Latence de détection', dec: '' },
              { num: '67', suffix: '%', label: 'Couverture MITRE ATT&CK', dec: '' },
            ].map((s, i) => (
              <div className="lp-stat" key={i}>
                <div className="lp-stat-num">
                  {s.dec !== undefined && s.num !== '< 2' ? (
                    <><span data-count={s.num} data-suffix={s.suffix} data-dec={s.dec}>0</span></>
                  ) : (
                    <>{s.num}<span style={{ color: 'var(--lp-accent)' }}>{s.suffix}</span></>
                  )}
                </div>
                <div className="lp-stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CONSOLE LIVE ── */}
      <section className="lp-section" id="plateforme">
        <div className="reveal">
          <div className="lp-section-label">PLATEFORME</div>
          <h2 className="lp-section-title">Intelligence de sécurité <em>en temps réel</em></h2>
          <p className="lp-section-sub">Visualisez, corréllez et répondez aux menaces au fur et à mesure qu'elles se produisent.</p>
        </div>
        <div className="lp-console reveal" style={{ animationDelay: '0.15s' }}>
          <div className="lp-console-bar">
            <span className="lp-dot lp-dot-r" />
            <span className="lp-dot lp-dot-y" />
            <span className="lp-dot lp-dot-g" />
            <span className="lp-console-title">BaolSec · Event Stream · LIVE</span>
            <span className="lp-console-status">● CONNECTÉ</span>
          </div>
          <div className="lp-console-body">
            {LOG_LINES.map((l, i) => (
              <div className="lp-log-line" key={i} style={{ animationDelay: `${i * 0.12}s` }}>
                <span className="lp-log-ts">{l.ts}</span>
                <span className={`lp-log-lvl ${l.cls}`}>{l.lvl}</span>
                <span className="lp-log-msg" dangerouslySetInnerHTML={{ __html: l.msg }} />
              </div>
            ))}
            <div className="lp-log-line">
              <span className="lp-log-ts">03:47:18.000</span>
              <span className="lp-log-lvl lvl-info">INFO</span>
              <span className="lp-log-msg">En attente de nouveaux événements <span className="lp-cursor" /></span>
            </div>
          </div>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section className="lp-section" id="fonctionnalites" style={{ backgroundImage: 'url("/assets/Gemini_Generated_Image_yfy78kyfy78kyfy7(2).jpeg")', backgroundSize: 'cover', backgroundPosition: 'center', maxWidth: '100%', padding: '100px 24px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <div className="reveal" style={{ textAlign: 'center', marginBottom: '4rem' }}>
            <div className="lp-section-label" style={{ justifyContent: 'center' }}>FONCTIONNALITÉS</div>
            <h2 className="lp-section-title" style={{ maxWidth: '100%', textAlign: 'center' }}>
              Tout ce dont votre SOC a <em>besoin</em>
            </h2>
          </div>
          <div className="lp-features-grid reveal">
            {FEATURES.map((f, i) => (
              <div className="lp-feature-card" key={i}>
                <div className="lp-feature-tag">{f.tag}</div>
                <div className="lp-feature-ico">{f.ico}</div>
                <h3 className="lp-feature-h">{f.h}</h3>
                <p className="lp-feature-p">{f.p}</p>
                <div className="lp-feature-glow" />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── APPROCHE ── */}
      <section className="lp-section" id="approche">
        <div className="reveal">
          <div className="lp-section-label">NOTRE APPROCHE</div>
          <h2 className="lp-section-title">Conçu pour <em>chaque équipe</em></h2>
          <p className="lp-section-sub">Une plateforme adaptée aux besoins spécifiques de chaque acteur de la sécurité.</p>
        </div>
        <div className="lp-approach-grid">
          {APPROACH.map((a, i) => (
            <div className="lp-approach-card reveal" key={i} style={{ animationDelay: `${i * 0.1}s` }}>
              <div className="lp-approach-img-wrap">
                <img src={a.img} alt={a.h} className="lp-approach-img" />
                <div className="lp-approach-overlay" />
              </div>
              <div className="lp-approach-body">
                <h3 className="lp-approach-h">{a.h}</h3>
                <p className="lp-approach-p">{a.p}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA FINAL ── */}
      <section className="lp-cta-section">
        <img src="/assets/Gemini_Generated_Image_yfy78kyfy78kyfy7(3).jpeg" alt="" className="lp-cta-bg-img" />
        <div className="lp-cta-overlay" />
        <div className="lp-cta-content reveal">
          <div className="lp-section-label" style={{ justifyContent: 'center' }}>COMMENCER</div>
          <h2 className="lp-cta-title">Votre sécurité mérite<br /><span className="lp-gradient-text">le meilleur outil</span></h2>
          <p className="lp-cta-sub">Rejoignez les équipes qui font confiance à BaolSec pour protéger leur infrastructure.</p>
          <button className="lp-btn-primary lp-cta-btn" onClick={() => nav('/login')}>
            <span>Accéder à la plateforme</span>
            <span className="lp-btn-arrow">→</span>
          </button>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="lp-footer">
        <div className="lp-footer-inner">
          <div className="lp-nav-logo">
            <img src="/assets/logo.jpg" alt="BaolSec" />
          </div>
          <p className="lp-footer-sub">SIEM distribué · Détection & Réponse · Projet de fin d'études L3</p>
          <p className="lp-footer-copy">© 2026 BaolSec. Tous droits réservés.</p>
        </div>
      </footer>
    </div>
  );
}
