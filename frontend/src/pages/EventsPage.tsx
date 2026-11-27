/**
 * Recherche d'événements (EF-11, C5 GET /events) : filtres structurés sur les événements normalisés
 * ECS indexés dans OpenSearch, du plus récent au plus ancien, avec le message brut d'origine.
 */
import { useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { events, sources, type EventFilters } from '../api/endpoints';
import {
  Badge, Card, CopyButton, Drawer, Empty, ErrorNotice, Field, LoadingRows, PageHeader, Pager,
} from '../components/ui';
import { IconSearch } from '../components/icons';
import { dateTime, count } from '../lib/format';
import { actionLabel, CATEGORY, categoryLabel, eventSummary } from '../lib/readable';
import type { EcsDocument } from '../types/api';

const PAGE = 50;
const PERIODS: { value: string; label: string; hours: number | null }[] = [
  { value: '1h', label: 'Dernière heure', hours: 1 },
  { value: '24h', label: '24 dernières heures', hours: 24 },
  { value: '7d', label: '7 derniers jours', hours: 168 },
  { value: '30d', label: '30 derniers jours', hours: 720 },
  { value: 'all', label: 'Toute la rétention', hours: null },
  { value: 'custom', label: 'Période personnalisée', hours: null },
];
const CATEGORIES = ['authentication', 'iam', 'network', 'process', 'file', 'web', 'host', 'configuration', 'intrusion_detection'];

interface Form {
  q: string; period: string; from: string; to: string; source_id: string; user: string; ip: string; host: string; category: string; outcome: string;
}
const EMPTY: Form = { q: '', period: '24h', from: '', to: '', source_id: '', user: '', ip: '', host: '', category: '', outcome: '' };

function toFilters(f: Form): EventFilters {
  const p = PERIODS.find((x) => x.value === f.period);
  let from: string | undefined;
  let to: string | undefined;
  if (f.period === 'custom') {
    from = f.from ? new Date(f.from).toISOString() : undefined;
    to = f.to ? new Date(f.to).toISOString() : undefined;
  } else if (p?.hours) {
    from = new Date(Date.now() - p.hours * 3_600_000).toISOString();
  }
  return { q: f.q.trim() || undefined, from, to, source_id: f.source_id || undefined, user: f.user.trim() || undefined,
    ip: f.ip.trim() || undefined, host: f.host.trim() || undefined, category: f.category || undefined, outcome: f.outcome || undefined };
}

export function EventsPage() {
  const [form, setForm] = useState<Form>(EMPTY);
  const [applied, setApplied] = useState<EventFilters>(() => toFilters(EMPTY));
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<EcsDocument | null>(null);
  const src = useQuery({ queryKey: ['sources', 'all'], queryFn: () => sources.list() });
  const q = useQuery({ queryKey: ['events', applied, offset], placeholderData: keepPreviousData, queryFn: () => events.search({ ...applied, limit: PAGE, offset }) });

  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = (e?: FormEvent) => { e?.preventDefault(); setOffset(0); setApplied(toFilters(form)); };
  const reset = () => { setForm(EMPTY); setOffset(0); setApplied(toFilters(EMPTY)); };
  const items = q.data?.items ?? [];

  return (
    <>
      <PageHeader title="Événements"
        subtitle="Recherchez dans les événements normalisés reçus des sources : par période, source, utilisateur, adresse IP, hôte ou texte libre." />

      <Card className="mb-16">
        <form className="card-body stack" style={{ gap: 14 }} onSubmit={submit}>
          <div className="filters">
            <Field label="Texte libre" className="grow">
              <input className="input" value={form.q} onChange={set('q')} placeholder="Ex. : Failed password, sudo, 404…" />
            </Field>
            <Field label="Période">
              <select className="select" value={form.period} onChange={set('period')}>
                {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </Field>
            {form.period === 'custom' && (<>
              <Field label="Du"><input className="input" type="datetime-local" value={form.from} onChange={set('from')} /></Field>
              <Field label="Au"><input className="input" type="datetime-local" value={form.to} onChange={set('to')} /></Field>
            </>)}
          </div>
          <div className="filters">
            <Field label="Source">
              <select className="select" value={form.source_id} onChange={set('source_id')}>
                <option value="">Toutes les sources</option>
                {(src.data?.items ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
            <Field label="Utilisateur"><input className="input" value={form.user} onChange={set('user')} placeholder="root" /></Field>
            <Field label="Adresse IP"><input className="input" value={form.ip} onChange={set('ip')} placeholder="203.0.113.7" /></Field>
            <Field label="Hôte"><input className="input" value={form.host} onChange={set('host')} placeholder="srv-web-01" /></Field>
            <Field label="Catégorie">
              <select className="select" value={form.category} onChange={set('category')}>
                <option value="">Toutes</option>
                {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY[c] ?? c}</option>)}
              </select>
            </Field>
            <Field label="Résultat">
              <select className="select" value={form.outcome} onChange={set('outcome')}>
                <option value="">Tous</option><option value="success">Réussi</option><option value="failure">Échoué</option><option value="unknown">Inconnu</option>
              </select>
            </Field>
            <div className="row" style={{ paddingBottom: 1 }}>
              <button type="button" className="btn ghost" onClick={reset}>Réinitialiser</button>
              <button type="submit" className="btn primary"><IconSearch />Rechercher</button>
            </div>
          </div>
        </form>
      </Card>

      <Card title="Résultats" hint={q.data ? `${count(q.data.total)} événement(s)` : undefined}
        footer={q.data && q.data.total > 0 ? <Pager offset={offset} limit={PAGE} total={Math.min(q.data.total, 10_000)} count={items.length} onChange={setOffset} /> : undefined}>
        {q.error ? <div className="card-body"><ErrorNotice error={q.error} retry={() => q.refetch()} /></div> : (
          <div className={`table-wrap ${q.isPlaceholderData ? 'is-stale' : ''}`}>
            <table className="table">
              <thead><tr><th>Quand</th><th>Ce qui s’est passé</th><th>Source</th><th>Utilisateur</th><th>Adresse IP</th><th>Machine</th><th>Résultat</th></tr></thead>
              {q.isLoading ? <LoadingRows cols={7} /> : (
                <tbody>
                  {items.map((e) => {
                    const o = outcomeBadge(e.event?.outcome);
                    return (
                      <tr key={`${e._index}-${e._id}`} className="clickable" onClick={() => setSelected(e)}>
                        <td className="small nowrap" title={dateTime(e['@timestamp'])}>{dateTime(e['@timestamp'])}</td>
                        <td className="title-cell" style={{ maxWidth: 440 }}><strong className="truncate" style={{ fontWeight: 500 }}>{eventSummary(e)}</strong>
                          <span>{actionLabel(e.event?.action)} · {categoryLabel(e.event?.category)}</span></td>
                        <td className="nowrap">{e.baolsec?.source?.name ?? <span className="faint">—</span>}</td>
                        <td className="mono small">{e.user?.name ?? <span className="faint">—</span>}</td>
                        <td className="mono small">{e.source?.ip ?? <span className="faint">—</span>}</td>
                        <td className="mono small">{e.host?.name ?? <span className="faint">—</span>}</td>
                        <td>{o ? <Badge tone={o.tone}>{o.text}</Badge> : <span className="faint">—</span>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              )}
            </table>
            {!q.isLoading && items.length === 0 && (
              <Empty title="Aucun événement" icon={<IconSearch />}>Élargissez la période ou retirez des filtres.</Empty>
            )}
          </div>
        )}
      </Card>

      {selected && <EventDrawer doc={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

const outcomeBadge = (o?: string) => (o === 'success' ? { tone: 'ok' as const, text: 'Réussi' }
  : o === 'failure' ? { tone: 'critical' as const, text: 'Échoué' } : undefined);

export function EventDrawer({ doc, onClose }: { doc: EcsDocument; onClose: () => void }) {
  const original = doc.event?.original;
  const { _id, _index, ...rest } = doc;
  const json = JSON.stringify(rest, null, 2);
  const o = outcomeBadge(doc.event?.outcome);
  return (
    <Drawer title={actionLabel(doc.event?.action)} subtitle={dateTime(doc['@timestamp'])} onClose={onClose}>
      <div className="stack">
        <p style={{ fontSize: 15 }}>{eventSummary(doc)}</p>
        <dl className="kv">
          <dt>Quand</dt><dd>{dateTime(doc['@timestamp'])}</dd>
          <dt>Source</dt><dd>{doc.baolsec?.source?.name ?? '—'}</dd>
          <dt>Type d’activité</dt><dd>{categoryLabel(doc.event?.category)}</dd>
          <dt>Résultat</dt><dd>{o ? <Badge tone={o.tone}>{o.text}</Badge> : 'non précisé'}</dd>
          <dt>Utilisateur</dt><dd className="mono">{doc.user?.name ?? '—'}</dd>
          <dt>Adresse IP d’origine</dt><dd className="mono">{doc.source?.ip ?? '—'}{doc.source?.port ? ` (port ${doc.source.port})` : ''}</dd>
          {doc.destination?.ip && (<><dt>Destination</dt><dd className="mono">{doc.destination.ip}{doc.destination.port ? ` (port ${doc.destination.port})` : ''}</dd></>)}
          <dt>Machine</dt><dd className="mono">{doc.host?.name ?? '—'}</dd>
        </dl>
        {original && (
          <div>
            <div className="section-title"><h2>Ligne reçue, telle quelle</h2><CopyButton text={original} /></div>
            <pre className="secret" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{original}</pre>
          </div>
        )}
        <details className="tech">
          <summary>Détails techniques (document ECS complet)</summary>
          <div className="stack mt-8" style={{ gap: 10 }}>
            <dl className="kv">
              <dt>Action (code)</dt><dd className="mono small">{doc.event?.action ?? '—'}</dd>
              <dt>Catégorie (code)</dt><dd className="mono small">{(doc.event?.category ?? []).join(', ') || '—'}</dd>
              <dt>Reçu par la passerelle</dt><dd>{dateTime(doc.baolsec?.received_at)}</dd>
              <dt>Index</dt><dd className="mono small">{_index}</dd>
              <dt>Identifiant</dt><dd className="mono small">{doc.event?.id ?? _id}</dd>
            </dl>
            <div className="row between"><span className="small faint">Document normalisé</span><CopyButton text={json} /></div>
            <pre className="secret code-block" style={{ maxHeight: 420, overflow: 'auto' }}>{json}</pre>
          </div>
        </details>
      </div>
    </Drawer>
  );
}
