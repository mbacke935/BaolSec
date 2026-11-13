/** Centre des alertes — table (maquette) câblée à GET /alerts. */
import { useQuery } from '@tanstack/react-query';
import { alerts, coverage } from '../api/analyst';
import { useSearch } from '../components/AppShell';
import { sevBadge } from '../lib/ui';

export function AlertsPage() {
  const q = useSearch().toLowerCase();
  const alertQ = useQuery({ queryKey: ['alerts'], queryFn: () => alerts.list({ limit: 200 }) });
  const covQ = useQuery({ queryKey: ['coverage'], queryFn: () => coverage.list() });
  const srcName = new Map((covQ.data ?? []).map((c) => [c.source_id, c.source_name]));

  const rows = (alertQ.data ?? []).filter((a) =>
    !q || `${a.id} ${a.rule_id ?? ''} ${a.title} ${a.severity}`.toLowerCase().includes(q),
  );

  return (
    <div className="panel">
      <h3>Centre des alertes</h3>
      <p className="empty-note" style={{ padding: '0 0 12px' }}>
        Filtrez les alertes et sélectionnez une ligne pour consulter son contexte.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>IDENTIFIANT</th><th>RÈGLE</th><th>SOURCE</th><th>GRAVITÉ</th><th>STATUT</th></tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const b = sevBadge(a.severity);
              return (
                <tr key={a.id}>
                  <td>AL-{a.id.slice(0, 8)}</td>
                  <td>{a.rule_id ? a.rule_id.slice(0, 8) : '—'}</td>
                  <td>{a.source_id ? (srcName.get(a.source_id) ?? a.source_id.slice(0, 8)) : '—'}</td>
                  <td><span className={b.cls}>{b.label}</span></td>
                  <td>{a.incident_id ? 'Corrélée' : 'Nouvelle'}</td>
                </tr>
              );
            })}
            {alertQ.isLoading && <tr><td colSpan={5} className="empty-note">Chargement…</td></tr>}
            {!alertQ.isLoading && rows.length === 0 && (
              <tr><td colSpan={5} className="empty-note">Aucune alerte à afficher.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
