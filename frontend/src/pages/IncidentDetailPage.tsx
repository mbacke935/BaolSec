/** Détail d'un incident — en-tête, changement d'état et chronologie (design maquette). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { incidents } from '../api/analyst';
import type { IncidentState } from '../types/api';
import { sevBadge, incidentState, fmtDateTime } from '../lib/ui';

const STATES: IncidentState[] = ['OUVERT', 'EN_COURS', 'RESOLU', 'CLOS', 'FAUX_POSITIF'];

export function IncidentDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const incQ = useQuery({ queryKey: ['incident', id], queryFn: () => incidents.get(id), enabled: !!id });
  const tlQ = useQuery({ queryKey: ['incident', id, 'timeline'], queryFn: () => incidents.timeline(id), enabled: !!id });

  const stateMut = useMutation({
    mutationFn: (state: IncidentState) => incidents.updateState(id, state),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['incident', id] }); qc.invalidateQueries({ queryKey: ['incidents'] }); },
  });

  const inc = incQ.data;
  if (incQ.isLoading) return <div className="panel"><p className="empty-note">Chargement…</p></div>;
  if (!inc) return <div className="panel"><p className="empty-note">Incident introuvable.</p></div>;

  const b = sevBadge(inc.severity);
  const st = incidentState(inc.state);

  return (
    <div>
      <button className="pill" style={{ marginBottom: 14 }} onClick={() => navigate('/app/incidents')}>← Incidents</button>

      <div className="panel">
        <div className="panel-head">
          <h3 style={{ fontSize: 18 }}>{inc.title}</h3>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <span className={b.cls}>{b.label}</span>
            <span className={st.cls}>{st.label}</span>
          </div>
        </div>
        <div className="filters" style={{ alignItems: 'center' }}>
          <span style={{ color: 'var(--muted)', fontSize: 12 }}>Ouvert le {fmtDateTime(inc.opened_at)}</span>
          <span style={{ color: 'var(--muted)', fontSize: 12 }}>· Clôturé {inc.closed_at ? fmtDateTime(inc.closed_at) : '—'}</span>
          <span style={{ marginLeft: 'auto', color: 'var(--muted)', fontSize: 12 }}>Changer l'état :</span>
          <select className="input" value={inc.state} onChange={(e) => stateMut.mutate(e.target.value as IncidentState)} disabled={stateMut.isPending}>
            {STATES.map((s) => <option key={s} value={s}>{incidentState(s).label}</option>)}
          </select>
        </div>
        {inc.description && <p style={{ color: '#cbd7e2', fontSize: 13 }}>{inc.description}</p>}
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <h3>Chronologie</h3>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>HORODATAGE</th><th>TYPE</th><th>DÉTAIL</th></tr></thead>
            <tbody>
              {(tlQ.data ?? []).map((t) => (
                <tr key={t.id}>
                  <td>{fmtDateTime(t.occurred_at)}</td>
                  <td>{t.entry_type}</td>
                  <td style={{ color: '#9fb3c6', fontFamily: 'ui-monospace,monospace', fontSize: 11 }}>{JSON.stringify(t.detail)}</td>
                </tr>
              ))}
              {tlQ.isLoading && <tr><td colSpan={3} className="empty-note">Chargement…</td></tr>}
              {!tlQ.isLoading && (tlQ.data ?? []).length === 0 && (
                <tr><td colSpan={3} className="empty-note">Aucune entrée de chronologie.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
