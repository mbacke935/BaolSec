/** Liste des incidents (C15, EF-07/EF-08) : regroupements d'alertes corrélées, du plus grave au moins grave. */
import { useDeferredValue, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { useFreshKeys } from '../lib/motion';
import { prefetchIncident } from '../lib/prefetch';
import { incidents } from '../api/endpoints';
import { useAuth } from '../auth/AuthContext';
import {
  Card, Empty, ErrorNotice, Field, IncidentStateBadge, LoadingRows, PageHeader, Segmented, SeverityBadge,
} from '../components/ui';
import { IconCheck } from '../components/icons';
import { ago, bySeverity, dateTime, SEVERITIES, SEVERITY } from '../lib/format';
import type { IncidentState, Severity } from '../types/api';

type View = 'active' | IncidentState | 'all';

export function IncidentsListPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [view, setView] = useState<View>('active');
  const [severity, setSeverity] = useState<'' | Severity>('');
  const [mine, setMine] = useState(false);
  const [text, setText] = useState('');

  const q = useQuery({
    queryKey: ['incidents', view, severity, mine], placeholderData: keepPreviousData,
    queryFn: () => incidents.list({
      active_only: view === 'active' || undefined,
      state: view === 'ouvert' || view === 'en_cours' || view === 'clos' ? view : undefined,
      severity: severity || undefined,
      assigned_to_me: mine || undefined,
      limit: 200,
    }),
    refetchInterval: 30_000,
  });
  const all = useQuery({ queryKey: ['incidents', 'counts'], queryFn: () => incidents.list({ limit: 200 }), refetchInterval: 30_000 });
  const n = (s: IncidentState) => (all.data ?? []).filter((i) => i.state === s).length;

  const fresh = useFreshKeys(q.isPlaceholderData ? undefined : q.data?.map((i) => i.id), `${view}|${severity}|${mine}`);
  const needle = useDeferredValue(text).trim().toLowerCase();
  const rows = [...(q.data ?? [])]
    .filter((i) => !needle || `${i.title} ${i.description ?? ''} ${(i.metadata.users ?? []).join(' ')} ${(i.metadata.hosts ?? []).join(' ')} ${(i.metadata.source_ips ?? []).join(' ')}`.toLowerCase().includes(needle))
    .sort((a, b) => (view === 'clos' || view === 'all' ? b.updated_at.localeCompare(a.updated_at) : bySeverity(a, b) || b.updated_at.localeCompare(a.updated_at)));

  return (
    <>
      <PageHeader title="Incidents"
        subtitle={user?.role === 'ANALYST'
          ? 'Chaque incident regroupe les alertes corrélées sur un même utilisateur, hôte ou adresse IP. Ouvrez-le pour l’instruire : attribution, suivi, commentaires, clôture.'
          : 'Consultation des incidents. Leur traitement est réservé aux analystes.'} />

      <Card>
        <div className="card-body">
          <div className="filters">
            <Segmented<View> value={view} onChange={setView} options={[
              { value: 'active', label: 'À traiter', count: n('ouvert') + n('en_cours') },
              { value: 'ouvert', label: 'Ouverts', count: n('ouvert') },
              { value: 'en_cours', label: 'En cours', count: n('en_cours') },
              { value: 'clos', label: 'Clos', count: n('clos') },
              { value: 'all', label: 'Tous', count: all.data?.length },
            ]} />
            <Field label="Gravité">
              <select className="select" value={severity} onChange={(e) => setSeverity(e.target.value as Severity | '')}>
                <option value="">Toutes</option>
                {SEVERITIES.map((s) => <option key={s} value={s}>{SEVERITY[s].label}</option>)}
              </select>
            </Field>
            <Field label="Filtrer" className="grow">
              <input className="input" placeholder="Titre, utilisateur, hôte, adresse IP…" value={text} onChange={(e) => setText(e.target.value)} />
            </Field>
            {user?.role === 'ANALYST' && (
              <label className="check" style={{ paddingBottom: 10 }}><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />Mes incidents</label>
            )}
          </div>
        </div>

        {q.error ? <div className="card-body"><ErrorNotice error={q.error} retry={() => q.refetch()} /></div> : (
          <div className={`table-wrap ${q.isPlaceholderData ? 'is-stale' : ''}`}>
            <table className="table">
              <thead><tr><th>Gravité</th><th>Incident</th><th>État</th><th>Responsable</th><th className="num">Alertes</th><th>Entités</th><th>Dernière activité</th></tr></thead>
              {q.isLoading ? <LoadingRows cols={7} /> : (
                <tbody>
                  {rows.map((i) => {
                    const entities = [...(i.metadata.users ?? []), ...(i.metadata.hosts ?? []), ...(i.metadata.source_ips ?? [])];
                    return (
                      <tr key={i.id} className={`clickable ${i.state === 'clos' ? 'dim' : ''} ${fresh.has(i.id) ? 'is-fresh' : ''}`}
                        onClick={() => navigate(`/incidents/${i.id}`)} onMouseEnter={() => prefetchIncident(qc, i.id)}>
                        <td><SeverityBadge value={i.severity} /></td>
                        <td className="title-cell" style={{ maxWidth: 420 }}><strong className="truncate">{i.title}</strong><span>Ouvert le {dateTime(i.opened_at)}</span></td>
                        <td><IncidentStateBadge value={i.state} /></td>
                        <td className={i.assigned_to_name ? '' : 'faint'}>{i.assigned_to_name ?? 'Non attribué'}</td>
                        <td className="num">{i.alert_count}</td>
                        <td className="small">
                          {entities.slice(0, 3).map((e) => <span key={e} className="tag mono" style={{ marginRight: 4 }}>{e}</span>)}
                          {entities.length > 3 && <span className="faint">+{entities.length - 3}</span>}
                          {!entities.length && <span className="faint">—</span>}
                        </td>
                        <td className="faint nowrap" title={dateTime(i.updated_at)}>{ago(i.updated_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              )}
            </table>
            {!q.isLoading && rows.length === 0 && (
              <Empty title={view === 'active' ? 'Aucun incident à traiter' : 'Aucun incident'} icon={<IconCheck />}>
                {view === 'active' ? 'Les alertes corrélées par le service Incidents apparaîtront ici.' : 'Aucun incident ne correspond à ces filtres.'}
              </Empty>
            )}
          </div>
        )}
      </Card>
    </>
  );
}
