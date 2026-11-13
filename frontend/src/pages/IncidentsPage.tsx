/** Gestion des incidents — table (maquette) câblée à GET /incidents, lignes cliquables. */
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { incidents } from '../api/analyst';
import { useSearch } from '../components/AppShell';
import { sevBadge, incidentState } from '../lib/ui';

export function IncidentsPage() {
  const navigate = useNavigate();
  const q = useSearch().toLowerCase();
  const incQ = useQuery({ queryKey: ['incidents'], queryFn: () => incidents.list({ limit: 200 }) });

  const rows = (incQ.data ?? []).filter((i) =>
    !q || `${i.id} ${i.title} ${i.state} ${i.severity}`.toLowerCase().includes(q),
  );

  return (
    <div className="panel">
      <h3>Gestion des incidents</h3>
      <p className="empty-note" style={{ padding: '0 0 12px' }}>
        Regroupement et suivi des alertes liées. Sélectionnez un incident pour sa chronologie.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>INCIDENT</th><th>TITRE</th><th>ALERTES</th><th>PRIORITÉ</th><th>ÉTAT</th></tr>
          </thead>
          <tbody>
            {rows.map((i) => {
              const b = sevBadge(i.severity);
              const st = incidentState(i.state);
              const nb = (i.metadata as Record<string, unknown>)?.alert_count;
              return (
                <tr key={i.id} className="rowlink" onClick={() => navigate(`/app/incidents/${i.id}`)}>
                  <td>{i.id.slice(0, 8)}</td>
                  <td>{i.title}</td>
                  <td>{typeof nb === 'number' ? nb : '—'}</td>
                  <td><span className={b.cls}>{b.label}</span></td>
                  <td><span className={st.cls}>{st.label}</span></td>
                </tr>
              );
            })}
            {incQ.isLoading && <tr><td colSpan={5} className="empty-note">Chargement…</td></tr>}
            {!incQ.isLoading && rows.length === 0 && (
              <tr><td colSpan={5} className="empty-note">Aucun incident à afficher.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
