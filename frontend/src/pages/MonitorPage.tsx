/**
 * Supervision — vue composants de la plateforme (maquette). L'état détaillé des
 * workers n'est pas exposé par une API dédiée : affichage illustratif, la
 * disponibilité réelle se vérifie via la supervision technique (Prometheus/Grafana).
 */
const COMPONENTS = [
  'Ingestion Gateway — opérationnel',
  'Normalization Worker — opérationnel',
  'Detection Worker — opérationnel',
  'Incident Builder — opérationnel',
  'Coverage Worker — opérationnel',
  'Indexing Worker — opérationnel',
];

export function MonitorPage() {
  return (
    <div>
      <div className="kpis">
        <div className="kpi"><small>Broker</small><strong style={{ color: 'var(--green2)' }}>Actif</strong><span className="up">NATS JetStream</span></div>
        <div className="kpi"><small>Base de données</small><strong style={{ color: 'var(--green2)' }}>Active</strong><span className="up">PostgreSQL 17</span></div>
        <div className="kpi"><small>Indexation</small><strong style={{ color: 'var(--green2)' }}>Active</strong><span className="up">OpenSearch 2.19</span></div>
        <div className="kpi"><small>Disponibilité</small><strong>99,9 %</strong><span className="up">Valeur illustrative</span></div>
      </div>
      <div className="panel">
        <h3>Santé des composants</h3>
        {COMPONENTS.map((c) => (
          <div className="health" style={{ margin: '15px 0' }} key={c}><i />{c}</div>
        ))}
        <p className="empty-note">Vue illustrative : la supervision temps réel est assurée par Prometheus et Grafana (C19).</p>
      </div>
    </div>
  );
}
