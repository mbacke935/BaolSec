/** Règles de détection — table (maquette), bascule actif/inactif pour l'ADMIN (PUT /rules). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { rules } from '../api/resources';
import { useAuth } from '../hooks/useAuth';
import { useSearch } from '../components/AppShell';
import { sevBadge } from '../lib/ui';

export function RulesPage() {
  const q = useSearch().toLowerCase();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const qc = useQueryClient();

  const rulesQ = useQuery({ queryKey: ['rules'], queryFn: () => rules.list({ limit: 200 }) });
  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => rules.update(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  });

  const rows = (rulesQ.data ?? []).filter((r) =>
    !q || `${r.name} ${r.severity}`.toLowerCase().includes(q),
  );

  return (
    <div className="panel">
      <h3>Règles de détection</h3>
      <p className="empty-note" style={{ padding: '0 0 12px' }}>
        {isAdmin ? "Activez ou désactivez les règles ; l'API applique le changement." : 'Vue en lecture seule (réservé à l\'administrateur pour la modification).'}
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>CODE</th><th>NOM</th><th>GRAVITÉ</th><th>ACTIVÉE</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const b = sevBadge(r.severity);
              return (
                <tr key={r.id}>
                  <td>{r.id.slice(0, 8)}</td>
                  <td>{r.name}</td>
                  <td><span className={b.cls}>{b.label}</span></td>
                  <td>
                    <button
                      className={`switch${r.enabled ? ' on' : ''}`}
                      disabled={!isAdmin || toggleMut.isPending}
                      title={isAdmin ? 'Basculer' : 'Réservé à l\'administrateur'}
                      onClick={() => toggleMut.mutate({ id: r.id, enabled: !r.enabled })}
                    />
                  </td>
                </tr>
              );
            })}
            {rulesQ.isLoading && <tr><td colSpan={4} className="empty-note">Chargement…</td></tr>}
            {!rulesQ.isLoading && rows.length === 0 && (
              <tr><td colSpan={4} className="empty-note">Aucune règle.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
