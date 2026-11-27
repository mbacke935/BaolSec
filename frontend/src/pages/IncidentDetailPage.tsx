/**
 * Détail d'un incident (C15, EF-07/EF-08) : contexte corrélé, alertes rattachées, chronologie
 * et actions de l'analyste. Chaque action est une commande incident_command/v1 traitée par le
 * service Incidents ; l'écran se rafraîchit à partir de l'état réellement enregistré.
 */
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { incidents } from '../api/endpoints';
import { useAuth } from '../auth/AuthContext';
import {
  AlertStatusBadge, Badge, Card, Empty, ErrorNotice, IncidentStateBadge, Loading, Modal, Notice, SeverityBadge,
  useToast,
} from '../components/ui';
import { IconArrowLeft } from '../components/icons';
import { refusal } from '../lib/commands';
import { ago, dateTime, SEVERITY_HELP, TIMELINE } from '../lib/format';
import { attachmentReason, FAMILY, timelineSummary } from '../lib/readable';
import type { CommandResult, Incident, TimelineEntry } from '../types/api';

type Dialog = null | 'close' | 'reopen';

export function IncidentDetailPage() {
  const { id = '' } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const isAnalyst = user?.role === 'ANALYST';
  const [comment, setComment] = useState('');
  const [dialog, setDialog] = useState<Dialog>(null);
  const [reason, setReason] = useState('');

  const inc = useQuery({ queryKey: ['incident', id], queryFn: () => incidents.get(id), refetchInterval: 20_000 });
  const timeline = useQuery({ queryKey: ['incident', id, 'timeline'], queryFn: () => incidents.timeline(id), refetchInterval: 20_000 });
  const linked = useQuery({ queryKey: ['incident', id, 'alerts'], queryFn: () => incidents.alerts(id), refetchInterval: 20_000 });

  const act = useMutation({
    mutationFn: ({ run }: { run: () => Promise<CommandResult>; ok: string }) => run(),
    onSuccess: (res, vars) => {
      const refused = refusal(res);
      if (refused) toast.error(refused); else toast.ok(vars.ok);
      qc.invalidateQueries({ queryKey: ['incident', id] });
      qc.invalidateQueries({ queryKey: ['incidents'] });
      qc.invalidateQueries({ queryKey: ['nav'] });
      if (!refused) { setDialog(null); setReason(''); }
    },
    onError: (err) => toast.error(err),
  });

  const busy = (ok: string) => act.isPending && act.variables?.ok === ok;

  if (inc.error) return <><BackLink /><ErrorNotice error={inc.error} retry={() => inc.refetch()} /></>;
  if (!inc.data) return <><BackLink /><Loading label="Chargement de l’incident…" /></>;
  const i = inc.data;
  const mine = i.assigned_to === user?.id;

  const sendComment = () => {
    const body = comment.trim();
    if (!body) return;
    act.mutate({ run: () => incidents.comment(id, body), ok: 'Commentaire ajouté.' }, { onSuccess: (r) => { if (r.result === 'acceptee') setComment(''); } });
  };

  return (
    <>
      <BackLink />
      <header className="page-head">
        <div style={{ minWidth: 0 }}>
          <div className="row" style={{ marginBottom: 10 }}>
            <SeverityBadge value={i.severity} /><IncidentStateBadge value={i.state} />
            <span className="faint small mono">#{i.id.slice(0, 8)}</span>
          </div>
          <h1 style={{ textWrap: 'balance' }}>{i.title}</h1>
          <p>Ouvert le {dateTime(i.opened_at)} · dernière activité {ago(i.updated_at)}{i.closed_at ? ` · clos le ${dateTime(i.closed_at)}` : ''}</p>
        </div>
        {isAnalyst && (
          <div className="actions">
            {i.state !== 'clos' && (mine
              ? <button className="btn" disabled={act.isPending} onClick={() => act.mutate({ run: () => incidents.assign(id, null), ok: 'Attribution retirée.' })}>{busy('Attribution retirée.') && <span className="spinner" />}Retirer l’attribution</button>
              : <button className="btn" disabled={act.isPending} onClick={() => act.mutate({ run: () => incidents.assign(id, user!.id), ok: 'Incident attribué.' })}>{busy('Incident attribué.') && <span className="spinner" />}M’attribuer</button>)}
            {i.state === 'ouvert' && <button className="btn primary" disabled={act.isPending} onClick={() => act.mutate({ run: () => incidents.setState(id, 'en_cours'), ok: 'Incident pris en charge.' })}>{busy('Incident pris en charge.') && <span className="spinner" />}Prendre en charge</button>}
            {i.state === 'en_cours' && <button className="btn" disabled={act.isPending} onClick={() => act.mutate({ run: () => incidents.setState(id, 'ouvert'), ok: 'Incident remis en attente.' })}>{busy('Incident remis en attente.') && <span className="spinner" />}Remettre en attente</button>}
            {i.state !== 'clos' && <button className="btn danger" onClick={() => setDialog('close')}>Clore</button>}
            {i.state === 'clos' && <button className="btn primary" onClick={() => setDialog('reopen')}>Rouvrir</button>}
          </div>
        )}
      </header>

      {!isAnalyst && <div className="mb-16"><Notice kind="info">Consultation seule : l’instruction des incidents est réservée aux analystes.</Notice></div>}

      <div className="grid grid-main">
        <div className="stack">
          {i.description && <Card title="Résumé" pad><p className="muted" style={{ whiteSpace: 'pre-wrap' }}>{i.description}</p></Card>}

          <Card title="Alertes rattachées" hint={`${linked.data?.length ?? i.alert_count}`}>
            {linked.error ? <div className="card-body"><ErrorNotice error={linked.error} /></div> : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Gravité</th><th>Alerte</th><th>Statut</th><th>Pourquoi dans cet incident</th><th>Déclenchée</th></tr></thead>
                  <tbody>
                    {(linked.data ?? []).map((a) => (
                      <tr key={a.id}>
                        <td><SeverityBadge value={a.severity} /></td>
                        <td className="title-cell"><strong>{a.title}</strong><span className="mono">{a.rule_code ?? ''}</span></td>
                        <td><AlertStatusBadge value={a.status} /></td>
                        <td className="small muted">{attachmentReason(a.detail as Record<string, unknown>)}</td>
                        <td className="faint nowrap" title={dateTime(a.fired_at)}>{ago(a.fired_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {linked.isLoading && <Loading />}
                {!linked.isLoading && !linked.data?.length && <Empty title="Aucune alerte rattachée" />}
              </div>
            )}
          </Card>

          <Card title="Chronologie" hint="Corrélations, alertes, changements d’état et commentaires">
            <div className="card-body">
              {timeline.error ? <ErrorNotice error={timeline.error} /> : timeline.isLoading ? <Loading /> : (
                timeline.data?.length ? <Timeline entries={timeline.data} alertTitles={Object.fromEntries((linked.data ?? []).map((x) => [x.id, x.title]))} /> : <p className="muted small">Aucune entrée.</p>
              )}
              {isAnalyst && (
                <div className="stack mt-16" style={{ gap: 10 }}>
                  <textarea className="textarea" placeholder="Ajouter un commentaire : constat, hypothèse, action menée…" maxLength={10000}
                    value={comment} onChange={(e) => setComment(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) sendComment(); }} />
                  <div className="row between">
                    <span className="small faint">Ctrl + Entrée pour envoyer · le commentaire est horodaté et signé.</span>
                    <button className="btn primary" disabled={!comment.trim() || act.isPending} onClick={sendComment}>{busy('Commentaire ajouté.') && <span className="spinner" />}Commenter</button>
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="stack">
          <Card title="Prise en charge" pad>
            <dl className="kv">
              <dt>État</dt><dd><IncidentStateBadge value={i.state} /></dd>
              <dt>Responsable</dt><dd>{i.assigned_to_name ?? <span className="faint">Non attribué</span>}</dd>
              <dt>Gravité</dt><dd><SeverityBadge value={i.severity} /><div className="small faint mt-8">{SEVERITY_HELP[i.severity]}</div></dd>
              <dt>Alertes</dt><dd>{i.alert_count}</dd>
              <dt>Ouvert le</dt><dd>{dateTime(i.opened_at)}</dd>
              {i.closed_at && (<><dt>Clos le</dt><dd>{dateTime(i.closed_at)}</dd></>)}
            </dl>
          </Card>
          <ContextCard incident={i} />
        </div>
      </div>

      {dialog && (
        <Modal title={dialog === 'close' ? 'Clore l’incident' : 'Rouvrir l’incident'}
          subtitle={dialog === 'close' ? 'L’incident sort de la file de traitement. Il pourra être rouvert.' : 'L’incident repasse « en cours ».'}
          onClose={() => setDialog(null)}
          footer={<>
            <button className="btn ghost" onClick={() => setDialog(null)}>Annuler</button>
            <button className={`btn ${dialog === 'close' ? 'danger' : 'primary'}`} disabled={act.isPending}
              onClick={() => act.mutate(dialog === 'close'
                ? { run: () => incidents.close(id, reason.trim() || undefined), ok: 'Incident clos.' }
                : { run: () => incidents.reopen(id, reason.trim() || undefined), ok: 'Incident rouvert.' })}>{busy('Incident rouvert.') && <span className="spinner" />}
              {act.isPending && <span className="spinner" />}{dialog === 'close' ? 'Clore' : 'Rouvrir'}
            </button>
          </>}>
          <label className="field">
            <span>{dialog === 'close' ? 'Conclusion (recommandée)' : 'Motif de réouverture'}</span>
            <textarea className="textarea" maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder={dialog === 'close' ? 'Ex. : faux positif confirmé, compte réinitialisé, adresse bloquée au pare-feu…' : 'Ex. : nouvelle activité observée sur le même compte'} />
            <span className="help">Le texte est conservé dans la chronologie de l’incident.</span>
          </label>
        </Modal>
      )}
    </>
  );
}

function BackLink() {
  return <Link to="/incidents" className="btn ghost sm mb-16" style={{ paddingLeft: 4 }}><IconArrowLeft /> Incidents</Link>;
}

function Timeline({ entries, alertTitles }: { entries: TimelineEntry[]; alertTitles: Record<string, string> }) {
  return (
    <ul className="timeline">
      {[...entries].reverse().map((e) => {
        const kind = TIMELINE[e.entry_type] ?? { label: e.entry_type, tone: 'neutral' as const };
        const body = typeof e.detail?.body === 'string' ? e.detail.body : null;
        const reason = typeof e.detail?.reason === 'string' && e.entry_type === 'status_change' ? e.detail.reason : null;
        return (
          <li key={e.id} className={`tone-${kind.tone}`}>
            <div className="t-head">
              <Badge tone={kind.tone}>{kind.label}</Badge>
              <span className="t-time" title={dateTime(e.occurred_at)}>{dateTime(e.occurred_at)}</span>
              {e.user_name && <span className="small muted">par <strong>{e.user_name}</strong></span>}
            </div>
            <div className="t-body">{e.entry_type === 'comment' ? null : timelineSummary(e.summary, e.detail, e.alert_id ? alertTitles[e.alert_id] : undefined)}</div>
            {body && <div className="t-extra" style={{ whiteSpace: 'pre-wrap' }}>{body}</div>}
            {reason && <div className="t-extra" style={{ whiteSpace: 'pre-wrap' }}>{reason}</div>}
          </li>
        );
      })}
    </ul>
  );
}

function ContextCard({ incident }: { incident: Incident }) {
  const m = incident.metadata ?? {};
  const groups: [string, string[] | undefined][] = [
    ['Utilisateurs', m.users], ['Machines', m.hosts], ['Adresses IP d’origine', m.source_ips], ['Types d’activité', m.activity_families?.map((f) => FAMILY[f] ?? f)],
  ];
  const any = groups.some(([, v]) => v?.length);
  return (
    <Card title="Ce que les alertes ont en commun" hint="Utilisateurs, machines et adresses qui relient les alertes de cet incident" pad>
      {!any ? <p className="muted small">Aucun élément commun enregistré.</p> : (
        <div className="stack" style={{ gap: 14 }}>
          {groups.filter(([, v]) => v?.length).map(([label, values]) => (
            <div key={label}>
              <div className="small faint" style={{ marginBottom: 6 }}>{label}</div>
              <div className="row" style={{ gap: 6 }}>{values!.map((v) => <span key={v} className="tag mono">{v}</span>)}</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
