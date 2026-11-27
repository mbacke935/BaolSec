/** Tableau de bord de l'Analyste (C23) : ce qui demande une action, du plus grave au moins grave. */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useFreshKeys } from '../lib/motion';
import { prefetchIncident } from '../lib/prefetch';
import { Link, useNavigate } from 'react-router-dom';
import { alerts, coverage, incidents } from '../api/endpoints';
import { useAuth } from '../auth/AuthContext';
import {
  AlertStatusBadge, Card, CoverageBadge, Empty, ErrorNotice, IncidentStateBadge, LoadingRows, PageHeader,
  SeverityBadge, Stat,
} from '../components/ui';
import { IconCheck, IconRadar } from '../components/icons';
import { ago, bySeverity } from '../lib/format';

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const inc = useQuery({ queryKey: ['incidents', 'active'], queryFn: () => incidents.list({ active_only: true }), refetchInterval: 30_000 });
  const al = useQuery({ queryKey: ['alerts', 'recent'], queryFn: () => alerts.list({ limit: 50 }), refetchInterval: 30_000 });
  const cov = useQuery({ queryKey: ['coverage'], queryFn: coverage.list, refetchInterval: 60_000 });

  const qc = useQueryClient();
  const freshInc = useFreshKeys(inc.data?.map((i) => i.id));
  const freshAl = useFreshKeys(al.data?.map((a) => a.id));
  const active = [...(inc.data ?? [])].sort((a, b) => bySeverity(a, b) || b.updated_at.localeCompare(a.updated_at));
  const newAlerts = (al.data ?? []).filter((a) => a.status === 'nouvelle');
  const mine = active.filter((i) => i.assigned_to === user?.id);
  const degraded = (cov.data?.items ?? []).filter((c) => c.state === 'SILENCIEUSE' || c.state === 'FLUX_INCOMPLET');
  const severeActive = active.filter((i) => i.severity === 'critique' || i.severity === 'elevee').length;
  const hello = new Date().getHours() < 18 ? 'Bonjour' : 'Bonsoir';

  return (
    <>
      <PageHeader title={`${hello} ${user?.username ?? ''}`}
        subtitle="Vue d'ensemble de ce qui demande votre attention. Actualisation automatique toutes les 30 secondes." />

      <div className="grid grid-4 mb-16">
        <Stat label="Alertes nouvelles" value={al.isLoading ? '…' : newAlerts.length} tone={newAlerts.length ? 'critical' : 'ok'}
          sub={newAlerts.length ? 'À prendre en charge' : 'Aucune alerte en attente'} href="/alerts" />
        <Stat label="Incidents actifs" value={inc.isLoading ? '…' : active.length} tone={active.length ? 'warn' : 'ok'}
          sub={`${active.filter((i) => i.state === 'ouvert').length} ouvert(s) · ${active.filter((i) => i.state === 'en_cours').length} en cours`} href="/incidents" />
        <Stat label="Critiques ou élevés" value={inc.isLoading ? '…' : severeActive} tone={severeActive ? 'critical' : 'ok'}
          sub="Incidents actifs à traiter en priorité" href="/incidents" />
        <Stat label="Sources à surveiller" value={cov.isLoading ? '…' : degraded.length} tone={degraded.length ? 'warn' : 'ok'}
          sub={degraded.length ? 'Silencieuses ou flux incomplet' : 'Toutes les sources actives remontent'} href="/coverage" />
      </div>

      <div className="grid grid-main">
        <div className="stack">
          <Card title="Incidents à traiter" hint={`${active.length} actif(s)`} actions={<Link className="btn sm" to="/incidents">Tous les incidents</Link>}>
            {inc.error ? <div className="card-body"><ErrorNotice error={inc.error} retry={() => inc.refetch()} /></div> : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Gravité</th><th>Incident</th><th>État</th><th>Responsable</th><th className="num">Alertes</th><th>Activité</th></tr></thead>
                  {inc.isLoading ? <LoadingRows cols={6} rows={4} /> : (
                    <tbody>
                      {active.slice(0, 8).map((i) => (
                        <tr key={i.id} className={`clickable ${freshInc.has(i.id) ? 'is-fresh' : ''}`} onClick={() => navigate(`/incidents/${i.id}`)} onMouseEnter={() => prefetchIncident(qc, i.id)}>
                          <td><SeverityBadge value={i.severity} /></td>
                          <td className="title-cell"><strong>{i.title}</strong><span>Ouvert {ago(i.opened_at)}</span></td>
                          <td><IncidentStateBadge value={i.state} /></td>
                          <td className={i.assigned_to_name ? '' : 'faint'}>{i.assigned_to_name ?? 'Non attribué'}</td>
                          <td className="num">{i.alert_count}</td>
                          <td className="faint nowrap">{ago(i.updated_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  )}
                </table>
                {!inc.isLoading && active.length === 0 && <Empty title="Aucun incident actif" icon={<IconCheck />}>Les nouvelles alertes corrélées apparaîtront ici.</Empty>}
              </div>
            )}
          </Card>

          <Card title="Dernières alertes" actions={<Link className="btn sm" to="/alerts">Toutes les alertes</Link>}>
            {al.error ? <div className="card-body"><ErrorNotice error={al.error} /></div> : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Gravité</th><th>Règle</th><th>Statut</th><th>Incident</th><th>Déclenchée</th></tr></thead>
                  {al.isLoading ? <LoadingRows cols={5} rows={4} /> : (
                    <tbody>
                      {(al.data ?? []).slice(0, 8).map((a) => (
                        <tr key={a.id} className={`clickable ${freshAl.has(a.id) ? 'is-fresh' : ''}`} onClick={() => navigate(a.incident_id ? `/incidents/${a.incident_id}` : '/alerts')}
                          onMouseEnter={() => { if (a.incident_id) prefetchIncident(qc, a.incident_id); }}>
                          <td><SeverityBadge value={a.severity} /></td>
                          <td className="title-cell"><strong>{a.title}</strong><span className="mono">{a.rule_code ?? ''}</span></td>
                          <td><AlertStatusBadge value={a.status} /></td>
                          <td className="truncate faint" style={{ maxWidth: 220 }}>{a.incident_title ?? '—'}</td>
                          <td className="faint nowrap">{ago(a.fired_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  )}
                </table>
                {!al.isLoading && !al.data?.length && <Empty title="Aucune alerte">Les alertes produites par les règles de détection s'afficheront ici.</Empty>}
              </div>
            )}
          </Card>
        </div>

        <div className="stack">
          <Card title="Mes dossiers" hint={`${mine.length} incident(s) attribué(s)`} pad>
            {mine.length === 0 ? <p className="muted small">Aucun incident ne vous est attribué. Ouvrez un incident et choisissez « M'attribuer ».</p> : (
              <ul className="mini-list" style={{ margin: '-16px -20px' }}>
                {mine.slice(0, 6).map((i) => (
                  <li key={i.id}><Link to={`/incidents/${i.id}`} className="grow"><div className="t" style={{ fontWeight: 600 }}>{i.title}</div>
                    <div className="small faint">{i.alert_count} alerte(s) · activité {ago(i.updated_at)}</div></Link><SeverityBadge value={i.severity} /></li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Couverture des sources" actions={<Link className="btn sm" to="/coverage">Détails</Link>}>
            {cov.error ? <div className="card-body"><ErrorNotice error={cov.error} /></div> : cov.isLoading ? <div className="card-body"><div className="skeleton" /></div> : (
              <ul className="mini-list">
                {[...(cov.data?.items ?? [])]
                  .sort((a, b) => Number(b.state === 'SILENCIEUSE' || b.state === 'FLUX_INCOMPLET') - Number(a.state === 'SILENCIEUSE' || a.state === 'FLUX_INCOMPLET'))
                  .slice(0, 8).map((c) => (
                    <li key={c.source_id}>
                      <div className="grow">
                        <div style={{ fontWeight: 600 }}>{c.source_name}</div>
                        <div className="small faint">
                          {c.affected_rules.length ? `${c.affected_rules.length} règle(s) privée(s) de données` : c.last_received_at ? `Dernier événement ${ago(c.last_received_at)}` : 'Aucun événement reçu'}
                        </div>
                      </div>
                      <CoverageBadge value={c.state} />
                    </li>
                  ))}
                {!cov.data?.items.length && <Empty title="Aucune source déclarée" icon={<IconRadar />} />}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
