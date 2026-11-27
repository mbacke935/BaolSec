/**
 * Journal d'audit (ES-07, C5 GET /audit), rédigé pour être lu sans connaissance technique :
 * une phrase par action (« admin a désactivé la source web-01 »), regroupée par jour, avec la
 * raison des refus en clair. Les détails techniques (requête, code de réponse, durée) restent
 * consultables, repliés.
 */
import { Fragment, useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { admin, rules, sources, users } from '../api/endpoints';
import { Badge, Card, Drawer, Empty, ErrorNotice, Field, LoadingRows, PageHeader, Pager, Segmented } from '../components/ui';
import { IconAudit, IconBell, IconLock, IconRule, IconServer, IconSettings, IconUsers } from '../components/icons';
import { count, dateTime } from '../lib/format';
import { AUDIT_DOMAIN, describeAudit, httpStatusText, type AuditDomain } from '../lib/readable';
import type { AuditEntry } from '../types/api';

const PAGE = 50;
const PERIODS = [
  { value: '1', label: 'Dernière heure' }, { value: '24', label: '24 dernières heures' },
  { value: '168', label: '7 derniers jours' }, { value: '720', label: '30 derniers jours' }, { value: '', label: 'Tout' },
];
const RESULT: Record<string, { label: string; tone: 'ok' | 'warn' | 'critical' }> = {
  succes: { label: 'Effectuée', tone: 'ok' }, refus: { label: 'Refusée', tone: 'warn' }, echec: { label: 'Échouée', tone: 'critical' },
};
const ICON: Record<AuditDomain, JSX.Element> = {
  connexion: <IconLock />, compte: <IconUsers />, source: <IconServer />, regle: <IconRule />,
  incident: <IconBell />, parametre: <IconSettings />, autre: <IconAudit />,
};

type DomainFilter = '' | Exclude<AuditDomain, 'autre'>;

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86_400_000);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, today)) return 'Aujourd’hui';
  if (same(d, yesterday)) return 'Hier';
  return new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(d);
}
const time = (iso: string) => new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(iso));

export function AuditPage() {
  const [domain, setDomain] = useState<DomainFilter>('');
  const [form, setForm] = useState({ actor: '', outcome: '', period: '24' });
  const [applied, setApplied] = useState(form);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<AuditEntry | null>(null);

  const q = useQuery({
    queryKey: ['audit', applied, domain, offset], placeholderData: keepPreviousData,
    queryFn: () => admin.audit({
      limit: PAGE, offset, domain: domain || undefined, actor: applied.actor.trim() || undefined, outcome: applied.outcome || undefined,
      occurred_after: applied.period ? new Date(Date.now() - Number(applied.period) * 3_600_000).toISOString() : undefined,
    }),
    refetchInterval: 30_000,
  });
  // Noms des éléments, pour les entrées enregistrées avant que l'API n'en garde le nom.
  const u = useQuery({ queryKey: ['users'], queryFn: users.list, staleTime: 60_000 });
  const s = useQuery({ queryKey: ['sources', 'all'], queryFn: () => sources.list(), staleTime: 60_000 });
  const r = useQuery({ queryKey: ['rules'], queryFn: () => rules.list(), staleTime: 60_000 });
  const names: Record<string, string> = Object.fromEntries([
    ...(u.data?.items ?? []).map((x) => [x.id, x.username]),
    ...(s.data?.items ?? []).map((x) => [x.id, x.name]),
    ...(r.data?.items ?? []).map((x) => [x.id, x.name]),
  ]);

  const submit = (e: FormEvent) => { e.preventDefault(); setOffset(0); setApplied(form); };
  const items = q.data?.items ?? [];
  const groups: [string, AuditEntry[]][] = [];
  for (const e of items) {
    const label = dayLabel(e.occurred_at);
    const last = groups[groups.length - 1];
    if (last && last[0] === label) last[1].push(e); else groups.push([label, [e]]);
  }

  return (
    <>
      <PageHeader title="Journal d’audit"
        subtitle="Qui a fait quoi, et quand. Chaque connexion et chaque modification est enregistrée, y compris les tentatives refusées. Ce journal ne peut pas être modifié." />

      <Card className="mb-16">
        <div className="card-body stack" style={{ gap: 14 }}>
          <Segmented<DomainFilter> value={domain} onChange={(v) => { setDomain(v); setOffset(0); }} options={[
            { value: '', label: 'Tout' },
            ...(Object.keys(AUDIT_DOMAIN) as AuditDomain[]).filter((k) => k !== 'autre')
              .map((k) => ({ value: k as DomainFilter, label: AUDIT_DOMAIN[k] })),
          ]} />
          <form className="filters" onSubmit={submit}>
            <Field label="Personne" className="grow"><input className="input" value={form.actor} onChange={(e) => setForm({ ...form, actor: e.target.value })} placeholder="Nom ou adresse e-mail" /></Field>
            <Field label="Résultat">
              <select className="select" value={form.outcome} onChange={(e) => setForm({ ...form, outcome: e.target.value })}>
                <option value="">Tous</option><option value="succes">Effectuées</option><option value="refus">Refusées</option><option value="echec">Échouées</option>
              </select>
            </Field>
            <Field label="Période">
              <select className="select" value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })}>
                {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </Field>
            <button className="btn primary" type="submit">Filtrer</button>
          </form>
        </div>
      </Card>

      <Card title="Actions" hint={q.data ? `${count(q.data.total)} enregistrée(s)` : undefined}
        footer={q.data && q.data.total > 0 ? <Pager offset={offset} limit={PAGE} total={q.data.total} count={items.length} onChange={setOffset} /> : undefined}>
        {q.error ? <div className="card-body"><ErrorNotice error={q.error} retry={() => q.refetch()} /></div> : (
          <div className={`table-wrap ${q.isPlaceholderData ? 'is-stale' : ''}`}>
            <table className="table audit-table">
              <thead><tr><th style={{ width: 96 }}>Heure</th><th>Action</th><th>Résultat</th><th>Depuis</th></tr></thead>
              {q.isLoading ? <LoadingRows cols={4} /> : (
                <tbody>
                  {groups.map(([day, entries]) => (
                    <Fragment key={day}>
                      <tr className="day-row"><td colSpan={4}>{day}</td></tr>
                      {entries.map((e) => {
                        const v = describeAudit(e, names);
                        const res = RESULT[e.outcome] ?? RESULT.echec;
                        return (
                          <tr key={e.id} className="clickable" onClick={() => setSelected(e)}>
                            <td className="mono small faint nowrap">{time(e.occurred_at)}</td>
                            <td>
                              <div className="audit-line">
                                <span className={`audit-ico d-${v.domain}`}>{ICON[v.domain]}</span>
                                <div style={{ minWidth: 0 }}>
                                  <div className="audit-sentence">{v.sentence}</div>
                                  {v.reason && <div className="small" style={{ color: e.outcome === 'echec' ? 'var(--critical)' : 'var(--warn)' }}>Motif : {v.reason}</div>}
                                </div>
                              </div>
                            </td>
                            <td><Badge tone={res.tone}>{res.label}</Badge></td>
                            <td className="mono small faint">{e.client_ip ?? '—'}</td>
                          </tr>
                        );
                      })}
                    </Fragment>
                  ))}
                </tbody>
              )}
            </table>
            {!q.isLoading && items.length === 0 && <Empty title="Aucune action" icon={<IconAudit />}>Aucune action ne correspond à ces critères.</Empty>}
          </div>
        )}
      </Card>

      {selected && <AuditDrawer entry={selected} names={names} onClose={() => setSelected(null)} />}
    </>
  );
}

function AuditDrawer({ entry, names, onClose }: { entry: AuditEntry; names: Record<string, string>; onClose: () => void }) {
  const v = describeAudit(entry, names);
  const d = (entry.details ?? {}) as Record<string, any>;
  const res = RESULT[entry.outcome] ?? RESULT.echec;
  return (
    <Drawer title={v.sentence} subtitle={`${dayLabel(entry.occurred_at)} à ${time(entry.occurred_at)}`} onClose={onClose}>
      <div className="stack">
        <dl className="kv">
          <dt>Personne</dt><dd>{entry.actor_username}{d.role ? <span className="faint"> · {d.role === 'ADMIN' ? 'administrateur' : 'analyste'}</span> : null}</dd>
          <dt>Domaine</dt><dd>{AUDIT_DOMAIN[v.domain]}</dd>
          <dt>Résultat</dt><dd><Badge tone={res.tone}>{res.label}</Badge></dd>
          {v.reason && (<><dt>Motif</dt><dd>{v.reason}</dd></>)}
          {d.label && (<><dt>Élément concerné</dt><dd>{d.label}</dd></>)}
          <dt>Adresse de connexion</dt><dd className="mono">{entry.client_ip ?? '—'}</dd>
        </dl>
        {d.changes && Object.keys(d.changes).length > 0 && (
          <div>
            <div className="section-title"><h2>Ce qui a été demandé</h2></div>
            <dl className="kv">{Object.entries(d.changes as Record<string, unknown>).filter(([k]) => k !== 'assignee_id').map(([k, val]) => (
              <Fragment key={k}><dt>{CHANGE_LABEL[k] ?? k}</dt><dd>{changeValue(k, val)}</dd></Fragment>
            ))}</dl>
          </div>
        )}
        <details className="tech">
          <summary>Détails techniques</summary>
          <dl className="kv mt-8">
            <dt>Requête</dt><dd className="mono small">{entry.action}</dd>
            <dt>Réponse</dt><dd>{httpStatusText(d.status)}</dd>
            {d.duration_ms != null && (<><dt>Durée</dt><dd>{d.duration_ms} ms</dd></>)}
            <dt>Cible</dt><dd className="mono small">{entry.target_type} · {entry.target_id}</dd>
            <dt>Horodatage</dt><dd className="mono small">{dateTime(entry.occurred_at)}</dd>
            <dt>N° d’entrée</dt><dd className="mono small">{entry.id}</dd>
          </dl>
        </details>
      </div>
    </Drawer>
  );
}

const CHANGE_LABEL: Record<string, string> = {
  status: 'Statut', state: 'État', enabled: 'Activée', active: 'Active', is_active: 'Compte actif', role: 'Rôle',
  silence_threshold_s: 'Seuil de silence', type: 'Type', name: 'Nom', username: 'Identifiant', email: 'Adresse e-mail',
  value: 'Nouvelle valeur', reason: 'Motif saisi', assignee_name: 'Attribué à', config: 'Configuration',
  password_changed: 'Mot de passe', definition_changed: 'Définition', comment_length: 'Commentaire', cert_fingerprint: 'Empreinte du certificat',
};

function changeValue(key: string, val: unknown): string {
  if (key === 'password_changed') return 'modifié (non enregistré dans le journal)';
  if (key === 'definition_changed') return 'nouvelle version de la règle';
  if (key === 'comment_length') return `${val} caractère(s) (texte visible dans la chronologie de l’incident)`;
  if (key === 'silence_threshold_s' && typeof val === 'number') return `${Math.round(val / 60)} min`;
  if (key === 'role') return val === 'ADMIN' ? 'administrateur' : val === 'ANALYST' ? 'analyste' : String(val);
  if (typeof val === 'boolean') return val ? 'oui' : 'non';
  if (val === null) return 'aucun';
  if (typeof val === 'object') return Object.entries(val as Record<string, unknown>).map(([k, x]) => `${k} : ${x}`).join(', ');
  return String(val).replace(/^en_cours$/, 'en cours');
}
