/**
 * Recherche avancée (C5 POST /search/{index}) : requêtes Lucene sur les index d'événements,
 * d'alertes et d'incidents. Complète la recherche guidée de la page Événements.
 */
import { Fragment, useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { search } from '../api/endpoints';
import { Card, Empty, ErrorNotice, PageHeader, Pager, Segmented, LoadingRows } from '../components/ui';
import { IconSearch } from '../components/icons';
import { count, dateTime } from '../lib/format';
import { eventSummary } from '../lib/readable';
import type { EcsDocument } from '../types/api';
import { EventDrawer } from './EventsPage';

type Index = 'events' | 'alerts' | 'incidents';
const PAGE = 50;

const EXAMPLES: Record<Index, { q: string; label: string }[]> = {
  events: [
    { q: 'event.outcome:failure AND event.category:authentication', label: 'Échecs d’authentification' },
    { q: 'user.name:root', label: 'Activité du compte root' },
    { q: 'source.ip:"203.0.113.7"', label: 'Une adresse IP précise' },
  ],
  alerts: [
    { q: 'baolsec.severity.label:critique', label: 'Alertes critiques' },
    { q: 'rule.id:*', label: 'Toutes les alertes' },
  ],
  incidents: [
    { q: 'state:ouvert', label: 'Incidents ouverts' }, { q: 'severity:critique OR severity:elevee', label: 'Critiques ou élevés' },
    { q: '*', label: 'Tous les incidents' },
  ],
};

const FIELDS: Record<Index, [string, string][]> = {
  events: [['event.category', 'authentication, network, process, web…'], ['event.outcome', 'success ou failure'], ['event.action', 'action normalisée'],
    ['user.name', 'compte concerné'], ['source.ip', 'adresse à l’origine'], ['host.name', 'machine émettrice'], ['baolsec.source.name', 'source déclarée'], ['message', 'texte du journal']],
  alerts: [['rule.id', 'code de la règle (AUTH-001…)'], ['rule.name', 'nom de la règle'], ['baolsec.severity.label', 'faible, moyenne, elevee, critique'],
    ['user.name', 'compte concerné'], ['source.ip', 'adresse à l’origine'], ['host.name', 'machine concernée']],
  incidents: [['state', 'ouvert, en_cours, clos'], ['severity', 'faible, moyenne, elevee, critique'], ['title', 'titre de l’incident'], ['alert_count', 'nombre d’alertes']],
};

export function SearchPage() {
  const [index, setIndex] = useState<Index>('events');
  const [text, setText] = useState('');
  const [query, setQuery] = useState<{ index: Index; q: string } | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<EcsDocument | null>(null);

  const q = useQuery({
    queryKey: ['lucene', query, offset], placeholderData: keepPreviousData,
    queryFn: () => search.lucene(query!.index, query!.q, PAGE, offset),
    enabled: query != null,
  });

  const run = (e?: FormEvent, value = text) => {
    e?.preventDefault();
    setOffset(0);
    setQuery({ index, q: value.trim() || '*' });
  };
  const hits = q.data?.hits ?? [];

  return (
    <>
      <PageHeader title="Recherche avancée"
        subtitle="Interrogez directement les index avec la syntaxe Lucene (champ:valeur, AND, OR, NOT, guillemets, jokers *). Pour une recherche guidée, utilisez la page Événements." />

      <Card className="mb-16">
        <form className="card-body stack" style={{ gap: 14 }} onSubmit={run}>
          <div className="row between">
            <Segmented<Index> value={index} onChange={(v) => { setIndex(v); setQuery(null); }} options={[
              { value: 'events', label: 'Événements' }, { value: 'alerts', label: 'Alertes' }, { value: 'incidents', label: 'Incidents' },
            ]} />
          </div>
          <div className="row" style={{ flexWrap: 'nowrap' }}>
            <input className="input mono" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000}
              placeholder={EXAMPLES[index][0].q} aria-label="Requête Lucene" />
            <button className="btn primary" type="submit"><IconSearch />Rechercher</button>
          </div>
          <div className="row small">
            <span className="faint">Exemples :</span>
            {EXAMPLES[index].map((x) => (
              <button key={x.q} type="button" className="btn sm" onClick={() => { setText(x.q); run(undefined, x.q); }}>{x.label}</button>
            ))}
          </div>
        </form>
      </Card>

      {!query && (
        <div className="grid grid-2">
          <Card title="Champs utiles" pad>
            <dl className="kv">
              {FIELDS[index].map(([f, d]) => (<Fragment key={f}><dt className="mono small" style={{ color: 'var(--text-2)' }}>{f}</dt><dd className="small muted">{d}</dd></Fragment>))}
            </dl>
          </Card>
          <Card title="Syntaxe" pad>
            <dl className="kv">
              <dt className="mono small">a AND b</dt><dd className="small muted">les deux conditions (par défaut entre deux termes)</dd>
              <dt className="mono small">a OR b</dt><dd className="small muted">l’une ou l’autre</dd>
              <dt className="mono small">NOT a</dt><dd className="small muted">exclut les documents correspondants</dd>
              <dt className="mono small">"texte exact"</dt><dd className="small muted">expression entre guillemets</dd>
              <dt className="mono small">user.name:adm*</dt><dd className="small muted">joker sur la fin d’une valeur</dd>
              <dt className="mono small">@timestamp:[now-1h TO now]</dt><dd className="small muted">intervalle de dates</dd>
            </dl>
          </Card>
        </div>
      )}

      {query && (
        <Card title="Résultats" hint={q.data ? `${count(q.data.total)} document(s)` : undefined}
          footer={q.data && q.data.total > 0 ? <Pager offset={offset} limit={PAGE} total={Math.min(q.data.total, 10_000)} count={hits.length} onChange={setOffset} /> : undefined}>
          {q.error ? <div className="card-body"><ErrorNotice error={q.error} retry={() => q.refetch()} /></div> : (
            <div className={`table-wrap ${q.isPlaceholderData ? 'is-stale' : ''}`}>
              <table className="table">
                <thead><tr><th>Horodatage</th><th>Résumé</th><th>Utilisateur</th><th>IP source</th><th>Hôte</th></tr></thead>
                {q.isLoading ? <LoadingRows cols={5} /> : (
                  <tbody>
                    {hits.map((h) => (
                      <tr key={h._id} className="clickable" onClick={() => setSelected(h)}>
                        <td className="mono small nowrap">{dateTime((h['@timestamp'] as string | undefined) ?? (h.opened_at as string | undefined))}</td>
                        <td className="truncate" style={{ maxWidth: 520 }}>{summary(h)}</td>
                        <td className="mono small">{h.user?.name ?? '—'}</td>
                        <td className="mono small">{h.source?.ip ?? '—'}</td>
                        <td className="mono small">{h.host?.name ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                )}
              </table>
              {!q.isLoading && hits.length === 0 && <Empty title="Aucun document" icon={<IconSearch />}>Vérifiez la syntaxe ou élargissez la requête.</Empty>}
            </div>
          )}
        </Card>
      )}

      {selected && <EventDrawer doc={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

function summary(h: EcsDocument): string {
  if (typeof h.title === 'string') return h.title;
  if (h.rule?.name) return `${h.rule.name}${h.message ? ` — ${h.message}` : ''}`;
  return h.event ? eventSummary(h) : h.message ?? String(h._id);
}
