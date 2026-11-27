/**
 * Alertes (C15, EF-06). Le document d'alerte est immuable (OpenSearch) ; l'état de traitement
 * (statut, analyste) est modifié par commande au service Incidents, réservée à l'Analyste.
 */
import { useDeferredValue, useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { alerts, rules } from '../api/endpoints';
import { useAuth } from '../auth/AuthContext';
import {
  AlertStatusBadge, Card, Drawer, Empty, ErrorNotice, Field, LoadingRows, Notice, PageHeader, Segmented,
  SeverityBadge, useToast,
} from '../components/ui';
import { IconCheck } from '../components/icons';
import { refusal } from '../lib/commands';
import { useFreshKeys } from '../lib/motion';
import { actionLabel, eventSummary, ruleInPlainWords } from '../lib/readable';
import { ago, ALERT_STATUSES, ALERT_STATUS, dateTime, SEVERITIES, SEVERITY, SEVERITY_HELP } from '../lib/format';
import type { Alert, AlertEvidence, AlertStatus, CommandResult, Severity } from '../types/api';

type StatusFilter = 'all' | AlertStatus;

export function AlertsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState<StatusFilter>('nouvelle');
  const [severity, setSeverity] = useState<'' | Severity>('');
  const [mine, setMine] = useState(false);
  const [text, setText] = useState('');
  const [selected, setSelected] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ['alerts', status, severity, mine], placeholderData: keepPreviousData,
    queryFn: () => alerts.list({ status: status === 'all' ? undefined : status, severity: severity || undefined, assigned_to_me: mine || undefined, limit: 200 }),
    refetchInterval: 30_000,
  });
  const all = useQuery({ queryKey: ['alerts', 'counts'], queryFn: () => alerts.list({ limit: 200 }), refetchInterval: 30_000 });
  const counts = Object.fromEntries(ALERT_STATUSES.map((s) => [s, (all.data ?? []).filter((a) => a.status === s).length]));

  const fresh = useFreshKeys(list.isPlaceholderData ? undefined : list.data?.map((a) => a.id), `${status}|${severity}|${mine}`);
  const needle = useDeferredValue(text).trim().toLowerCase();
  const rows = (list.data ?? []).filter((a) => !needle || `${a.title} ${a.rule_code ?? ''} ${a.incident_title ?? ''}`.toLowerCase().includes(needle));

  return (
    <>
      <PageHeader title="Alertes"
        subtitle={user?.role === 'ANALYST'
          ? 'Alertes produites par les règles de détection. Prenez-les en charge, attribuez-les et clôturez-les une fois traitées.'
          : 'Consultation des alertes (lecture seule pour l’administrateur : le traitement est réservé aux analystes).'} />

      <Card>
        <div className="card-body">
          <div className="filters">
            <Segmented<StatusFilter> value={status} onChange={setStatus} options={[
              { value: 'nouvelle', label: 'Nouvelles', count: counts.nouvelle },
              { value: 'en_cours', label: 'En cours', count: counts.en_cours },
              { value: 'cloturee', label: 'Clôturées', count: counts.cloturee },
              { value: 'all', label: 'Toutes', count: all.data?.length },
            ]} />
            <Field label="Gravité">
              <select className="select" value={severity} onChange={(e) => setSeverity(e.target.value as Severity | '')}>
                <option value="">Toutes</option>
                {SEVERITIES.map((s) => <option key={s} value={s}>{SEVERITY[s].label}</option>)}
              </select>
            </Field>
            <Field label="Filtrer" className="grow">
              <input className="input" placeholder="Règle, code ou incident…" value={text} onChange={(e) => setText(e.target.value)} />
            </Field>
            {user?.role === 'ANALYST' && (
              <label className="check" style={{ paddingBottom: 10 }}><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />Mes alertes</label>
            )}
          </div>
        </div>
        {list.error ? <div className="card-body"><ErrorNotice error={list.error} retry={() => list.refetch()} /></div> : (
          <div className={`table-wrap ${list.isPlaceholderData ? 'is-stale' : ''}`}>
            <table className="table">
              <thead><tr><th>Gravité</th><th>Alerte</th><th>Statut</th><th>Analyste</th><th>Incident</th><th>Déclenchée</th></tr></thead>
              {list.isLoading ? <LoadingRows cols={6} /> : (
                <tbody>
                  {rows.map((a) => (
                    <tr key={a.id} className={`clickable ${fresh.has(a.id) ? 'is-fresh' : ''}`} onClick={() => setSelected(a.id)}
                      onMouseEnter={() => qc.prefetchQuery({ queryKey: ['alert', a.id], queryFn: () => alerts.get(a.id), staleTime: 15_000 })}>
                      <td><SeverityBadge value={a.severity} /></td>
                      <td className="title-cell"><strong>{a.title}</strong><span>Règle {a.rule_code ?? '—'}</span></td>
                      <td><AlertStatusBadge value={a.status} /></td>
                      <td className={a.assigned_to_name ? '' : 'faint'}>{a.assigned_to_name ?? '—'}</td>
                      <td className="truncate" style={{ maxWidth: 260 }}>
                        {a.incident_id ? <Link to={`/incidents/${a.incident_id}`} onClick={(e) => e.stopPropagation()} className="btn link">{a.incident_title ?? 'Voir l’incident'}</Link> : <span className="faint">—</span>}
                      </td>
                      <td className="faint nowrap" title={dateTime(a.fired_at)}>{ago(a.fired_at)}</td>
                    </tr>
                  ))}
                </tbody>
              )}
            </table>
            {!list.isLoading && rows.length === 0 && (
              <Empty title={status === 'nouvelle' ? 'Aucune alerte en attente' : 'Aucune alerte'} icon={<IconCheck />}>
                {status === 'nouvelle' ? 'Toutes les alertes ont été prises en charge.' : 'Aucune alerte ne correspond à ces filtres.'}
              </Empty>
            )}
          </div>
        )}
      </Card>

      {selected && <AlertDrawer id={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

function AlertDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ['alert', id], queryFn: () => alerts.get(id) });
  const a = q.data;
  const rule = useQuery({ queryKey: ['rule', a?.rule_id], queryFn: () => rules.get(a!.rule_id), enabled: !!a?.rule_id, staleTime: 60_000 });
  const plain = rule.data ? ruleInPlainWords(rule.data) : null;
  const isAnalyst = user?.role === 'ANALYST';

  const act = useMutation({
    mutationFn: ({ run }: { run: () => Promise<CommandResult>; key: string }) => run(),
    onSuccess: (res, _v) => {
      const refused = refusal(res);
      if (refused) toast.error(refused); else toast.ok('Alerte mise à jour.');
      qc.invalidateQueries({ queryKey: ['alerts'] });
      qc.invalidateQueries({ queryKey: ['alert', id] });
      qc.invalidateQueries({ queryKey: ['nav'] });
    },
    onError: (err) => toast.error(err),
  });

  const busy = (key: string) => act.isPending && act.variables?.key === key;
  const evidence = (a?.detail ?? {}) as AlertEvidence;
  const doc = evidence.alert;

  return (
    <Drawer title={a?.title ?? 'Alerte'} subtitle={a ? `Déclenchée ${ago(a.fired_at)} · règle ${a.rule_code ?? ''}` : null} onClose={onClose}
      footer={isAnalyst && a ? (
        <div className="row" style={{ width: '100%', justifyContent: 'space-between' }}>
          <div className="row">
            {a.assigned_to === user?.id
              ? <button className="btn" disabled={act.isPending} onClick={() => act.mutate({ run: () => alerts.assign(a.id, null), key: 'unassign' })}>{busy('unassign') && <span className="spinner" />}Retirer l’attribution</button>
              : a.status !== 'cloturee' && <button className="btn" disabled={act.isPending} onClick={() => act.mutate({ run: () => alerts.assign(a.id, user!.id), key: 'assign' })}>{busy('assign') && <span className="spinner" />}M’attribuer</button>}
          </div>
          <div className="row">
            {a.status === 'nouvelle' && <button className="btn primary" disabled={act.isPending} onClick={() => act.mutate({ run: () => alerts.setStatus(a.id, 'en_cours'), key: 'take' })}>{busy('take') && <span className="spinner" />}Prendre en charge</button>}
            {a.status !== 'cloturee' && <button className="btn" disabled={act.isPending} onClick={() => act.mutate({ run: () => alerts.setStatus(a.id, 'cloturee'), key: 'close' })}>{busy('close') && <span className="spinner" />}Clôturer</button>}
            {a.status === 'cloturee' && <button className="btn" disabled={act.isPending} onClick={() => act.mutate({ run: () => alerts.setStatus(a.id, 'en_cours'), key: 'reopen' })}>{busy('reopen') && <span className="spinner" />}Rouvrir</button>}
          </div>
        </div>
      ) : undefined}>
      {q.error ? <ErrorNotice error={q.error} /> : !a ? <div className="skeleton" /> : (
        <div className="stack">
          <div className="row"><SeverityBadge value={a.severity} /><AlertStatusBadge value={a.status} /></div>
          <p className="small muted" style={{ marginTop: -6 }}>{SEVERITY_HELP[a.severity]}</p>
          {doc?.message && <p style={{ fontSize: 15 }}>{doc.message}</p>}
          <dl className="kv">
            <dt>Déclenchée</dt><dd>{dateTime(a.fired_at)} <span className="faint">({ago(a.fired_at)})</span></dd>
            <dt>Analyste</dt><dd>{a.assigned_to_name ?? <span className="faint">Non attribuée</span>}</dd>
            <dt>Incident</dt><dd>{a.incident_id ? <Link className="btn link" to={`/incidents/${a.incident_id}`}>{a.incident_title ?? 'Voir l’incident'}</Link> : <span className="faint">Non rattachée</span>}</dd>
            <dt>Statut</dt><dd>{ALERT_STATUS[a.status].label}</dd>
          </dl>
          {!isAnalyst && <Notice kind="info">Le traitement des alertes est réservé aux analystes (matrice des droits C2).</Notice>}

          <div>
            <div className="section-title"><h2>Pourquoi cette alerte ?</h2></div>
            {rule.data ? (
              <div className="stack" style={{ gap: 8 }}>
                {rule.data.description && <p className="muted">{rule.data.description}</p>}
                {plain && <p>{plain.trigger}</p>}
                {plain && plain.conditions.length > 0 && (
                  <div className="small muted">Événements pris en compte :<ul className="plain-list mt-8">{plain.conditions.map((c) => <li key={c}>{c}</li>)}</ul></div>
                )}
              </div>
            ) : <p className="muted small">{a.title}</p>}
          </div>

          <div>
            <div className="section-title"><h2>Ce qui a été observé</h2></div>
            {!evidence.available ? (
              <Notice kind="warn">Le moteur de recherche ne répond pas : les événements à l’origine de l’alerte ne peuvent pas être affichés pour l’instant. Le statut et l’attribution ci-dessus restent à jour.</Notice>
            ) : !evidence.found ? (
              <Notice kind="info">Les détails de l’alerte arrivent dans quelques secondes (enregistrement en cours dans le moteur de recherche).</Notice>
            ) : (
              <div className="stack" style={{ gap: 12 }}>
                <dl className="kv">
                  {doc?.user?.name && (<><dt>Utilisateur concerné</dt><dd className="mono">{doc.user.name}</dd></>)}
                  {doc?.source?.ip && (<><dt>Adresse IP d’origine</dt><dd className="mono">{doc.source.ip}</dd></>)}
                  {doc?.host?.name && (<><dt>Machine</dt><dd className="mono">{doc.host.name}</dd></>)}
                  {doc?.baolsec?.alert?.window_start && (<><dt>Période observée</dt><dd>depuis le {dateTime(doc.baolsec.alert.window_start)}</dd></>)}
                </dl>
                <div className="section-title"><h2>Les événements qui l’ont déclenchée</h2><span className="hint">{evidence.events?.length ?? 0}</span></div>
                {evidence.events?.length ? (
                  <ul className="timeline">
                    {evidence.events.map((e) => (
                      <li key={e._id} className="tone-info">
                        <div className="t-head"><span className="t-time">{dateTime(e['@timestamp'])}</span><span className="faint small">{actionLabel(e.event?.action)}</span></div>
                        <div className="t-body">{eventSummary(e)}</div>
                      </li>
                    ))}
                  </ul>
                ) : <p className="muted small">Ces événements ne sont plus disponibles (au-delà de la durée de conservation) ou pas encore enregistrés.</p>}
              </div>
            )}
          </div>
        </div>
      )}
    </Drawer>
  );
}

export type { Alert };
