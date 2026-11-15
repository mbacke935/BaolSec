/** Centre des alertes — lecture incidents.alert_state ; triage par l'Analyste (commande statut_alerte). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { alerts } from '../api/analyst';
import type { AlertStatus } from '../types/api';
import { useAuth } from '../hooks/useAuth';
import { useSearch } from '../components/AppShell';
import { sevBadge } from '../lib/ui';

const STATUS_LABEL: Record<AlertStatus, string> = {
  nouvelle: 'Nouvelle',
  en_cours: 'En cours',
  cloturee: 'Clôturée',
};

export function AlertsPage() {
  const q = useSearch().toLowerCase();
  const { user } = useAuth();
  const isAnalyst = user?.role === 'ANALYST';
  const qc = useQueryClient();

  const alertQ = useQuery({ queryKey: ['alerts'], queryFn: () => alerts.list({ limit: 200 }) });
  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: AlertStatus }) => alerts.updateStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });

  const rows = (alertQ.data ?? []).filter((a) =>
    !q || `${a.id} ${a.rule_id} ${a.title} ${a.severity} ${a.status}`.toLowerCase().includes(q),
  );

  return (
    <div className="panel">
      <h3>Centre des alertes</h3>
      <p className="empty-note" style={{ padding: '0 0 12px' }}>
        {isAnalyst ? 'Qualifiez les alertes (le changement de statut est transmis au service Incidents).'
                   : 'Lecture seule — le traitement des alertes est réservé à l\'Analyste (C5).'}
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>IDENTIFIANT</th><th>RÈGLE</th><th>GRAVITÉ</th><th>STATUT</th><th>ANALYSTE</th></tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const b = sevBadge(a.severity);
              return (
                <tr key={a.id}>
                  <td style={{ fontFamily: 'ui-monospace,monospace', fontSize: 11 }}>{a.id.slice(0, 22)}</td>
                  <td>{a.title || a.rule_id.slice(0, 8)}</td>
                  <td><span className={b.cls}>{b.label}</span></td>
                  <td>
                    {isAnalyst ? (
                      <select
                        className="input"
                        style={{ padding: '3px 8px', fontSize: 11 }}
                        value={a.status}
                        disabled={statusMut.isPending}
                        onChange={(e) => statusMut.mutate({ id: a.id, status: e.target.value as AlertStatus })}
                      >
                        {(Object.keys(STATUS_LABEL) as AlertStatus[]).map((s) => (
                          <option key={s} value={s}>{STATUS_LABEL[s]}</option>
                        ))}
                      </select>
                    ) : (
                      <span className={a.status === 'cloturee' ? 'state-pill mute' : 'state-pill'}>{STATUS_LABEL[a.status]}</span>
                    )}
                  </td>
                  <td>{a.assigned_to ? a.assigned_to.slice(0, 8) : 'Non assignée'}</td>
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
