/** Accueil de l'Administrateur : état du référentiel, de la plateforme et dernières actions tracées. */
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { admin, coverage, rules, sources, system, users } from '../api/endpoints';
import { useAuth } from '../auth/AuthContext';
import { Badge, Card, CoverageBadge, Empty, ErrorNotice, LoadingRows, PageHeader, Stat } from '../components/ui';
import { ago, count, dateTime } from '../lib/format';
import { describeAudit, SERVICE_NAME } from '../lib/readable';

export function AdminOverviewPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const u = useQuery({ queryKey: ['users'], queryFn: users.list });
  const s = useQuery({ queryKey: ['sources', 'all'], queryFn: () => sources.list() });
  const r = useQuery({ queryKey: ['rules'], queryFn: () => rules.list() });
  const h = useQuery({ queryKey: ['system', 'health'], queryFn: system.health, refetchInterval: 30_000 });
  const d = useQuery({ queryKey: ['dlq', 'summary'], queryFn: () => admin.dlq({ limit: 1 }), refetchInterval: 60_000, retry: false });
  const c = useQuery({ queryKey: ['coverage'], queryFn: coverage.list, refetchInterval: 60_000 });
  const a = useQuery({ queryKey: ['audit', 'recent'], queryFn: () => admin.audit({ limit: 8 }), refetchInterval: 30_000 });

  const activeUsers = (u.data?.items ?? []).filter((x) => x.is_active);
  const locked = (u.data?.items ?? []).filter((x) => x.locked_until && new Date(x.locked_until) > new Date());
  const activeSources = (s.data?.items ?? []).filter((x) => x.active);
  const enabledRules = (r.data?.items ?? []).filter((x) => x.enabled);
  const down = (h.data?.components ?? []).filter((x) => x.status !== 'up');
  const silent = (c.data?.items ?? []).filter((x) => x.state === 'SILENCIEUSE' || x.state === 'FLUX_INCOMPLET');

  return (
    <>
      <PageHeader title={`Administration`}
        subtitle={`Connecté en tant que ${user?.username}. Gérez les comptes, les sources et les règles ; suivez la santé de la plateforme et la traçabilité des actions.`} />

      <div className="grid grid-4 mb-16">
        <Stat label="Comptes actifs" value={u.isLoading ? '…' : activeUsers.length} href="/users"
          sub={locked.length ? `${locked.length} compte(s) verrouillé(s)` : `${(u.data?.items.length ?? 0) - activeUsers.length} désactivé(s)`} tone={locked.length ? 'warn' : undefined} />
        <Stat label="Sources en service" value={s.isLoading ? '…' : activeSources.length} href="/sources"
          sub={silent.length ? `${silent.length} à surveiller` : 'Toutes remontent'} tone={silent.length ? 'warn' : 'ok'} />
        <Stat label="Règles actives" value={r.isLoading ? '…' : enabledRules.length} href="/rules" sub={`sur ${r.data?.items.length ?? 0} règle(s)`} />
        <Stat label="File de rejet" value={d.isLoading ? '…' : d.error ? '—' : count(d.data?.total)} href="/dlq"
          tone={d.data?.total ? 'warn' : 'ok'} sub={d.error ? 'Broker injoignable' : d.data?.total ? 'Messages à examiner' : 'Aucun message rejeté'} />
      </div>

      <div className="grid grid-main">
        <div className="stack">
          <Card title="Dernières actions tracées" actions={<Link className="btn sm" to="/audit">Journal complet</Link>}>
            {a.error ? <div className="card-body"><ErrorNotice error={a.error} /></div> : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Quand</th><th>Action</th><th>Résultat</th></tr></thead>
                  {a.isLoading ? <LoadingRows cols={3} rows={5} /> : (
                    <tbody>
                      {(a.data?.items ?? []).map((e) => {
                        const v = describeAudit(e);
                        return (
                          <tr key={e.id} className="clickable" onClick={() => navigate('/audit')}>
                            <td className="faint nowrap" title={dateTime(e.occurred_at)}>{ago(e.occurred_at)}</td>
                            <td><div>{v.sentence}</div>{v.reason && <div className="small" style={{ color: 'var(--warn)' }}>Motif : {v.reason}</div>}</td>
                            <td><Badge tone={e.outcome === 'succes' ? 'ok' : e.outcome === 'refus' ? 'warn' : 'critical'}>{e.outcome === 'succes' ? 'Effectuée' : e.outcome === 'refus' ? 'Refusée' : 'Échouée'}</Badge></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  )}
                </table>
                {!a.isLoading && !a.data?.items.length && <Empty title="Aucune action tracée" />}
              </div>
            )}
          </Card>
        </div>

        <div className="stack">
          <Card title="Santé de la plateforme" actions={<Link className="btn sm" to="/monitor">Supervision</Link>} pad>
            {h.error ? <ErrorNotice error={h.error} /> : h.isLoading ? <div className="skeleton" /> : down.length === 0 ? (
              <div className="row"><span className="pulse" /><span>Tous les composants répondent ({h.data?.components.length}).</span></div>
            ) : (
              <div className="stack" style={{ gap: 8 }}>
                {down.map((x) => (
                  <div key={x.name} className="row between"><span className="small">{SERVICE_NAME[x.name] ?? x.name}</span>
                    <Badge tone={x.status === 'down' ? 'critical' : 'warn'}>{x.status === 'down' ? 'Indisponible' : 'Dégradé'}</Badge></div>
                ))}
              </div>
            )}
          </Card>
          <Card title="Sources à surveiller" actions={<Link className="btn sm" to="/coverage">Couverture</Link>} pad>
            {silent.length === 0 ? <p className="muted small">Aucune source silencieuse ni au flux incomplet.</p> : (
              <div className="stack" style={{ gap: 10 }}>
                {silent.map((x) => (
                  <div key={x.source_id} className="row between">
                    <div style={{ minWidth: 0 }}><div className="truncate" style={{ fontWeight: 600 }}>{x.source_name}</div>
                      <div className="small faint">{x.affected_rules.length} règle(s) privée(s) de données</div></div>
                    <CoverageBadge value={x.state} />
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
