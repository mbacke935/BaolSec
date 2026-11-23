/**
 * Flux d'événements — table câblée à POST /search/events (OpenSearch).
 * Champs lus au format ECS (aplatis ou imbriqués).
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { search } from '../api/analyst';
import '../styles/design-system.css';

/** Lit un champ ECS qu'il soit imbriqué (source.name) ou aplati. */
function pick(doc: Record<string, unknown>, path: string): string | undefined {
  if (doc[path] != null) return String(doc[path]);
  let cur: unknown = doc;
  for (const part of path.split('.')) {
    if (cur && typeof cur === 'object' && part in (cur as object))
      cur = (cur as Record<string, unknown>)[part];
    else return undefined;
  }
  return cur == null ? undefined : String(cur);
}

function fmtTs(val: string | undefined) {
  if (!val) return '—';
  return new Date(val).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

export function EventsPage() {
  const [query, setQuery]         = useState('');
  const [submitted, setSubmitted] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['events', submitted],
    queryFn: () => search.events(submitted || '*', 100),
    retry: false,
    enabled: true,
  });

  const hits  = data?.hits  ?? [];
  const total = data?.total ?? 0;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(query.trim());
  }

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title">Événements <span>bruts</span></h1>
          <p className="bs-page-sub">Exploration des événements normalisés (ECS) depuis OpenSearch</p>
        </div>
        {data && (
          <span className="bs-mono" style={{ fontSize: 12, color: 'var(--fg4)', alignSelf: 'center' }}>
            {total.toLocaleString('fr-FR')} événement(s)
          </span>
        )}
      </div>

      {/* Barre de recherche */}
      <div className="bs-card bs-mb-16">
        <form onSubmit={handleSubmit}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div className="bs-input-wrap" style={{ flex: 1 }}>
              <span className="bs-input-icon">⌕</span>
              <input
                className="bs-input"
                type="search"
                placeholder="Filtrer les événements… (laisser vide pour tout afficher)"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <button type="submit" className="bs-btn bs-btn-primary bs-btn-sm">
              {isLoading ? 'Chargement…' : 'Filtrer'}
            </button>
            {submitted && (
              <button
                type="button"
                className="bs-btn bs-btn-ghost bs-btn-sm"
                onClick={() => { setQuery(''); setSubmitted(''); }}
              >
                Réinitialiser
              </button>
            )}
          </div>
        </form>
      </div>

      {/* Contenu */}
      {isLoading ? (
        <div className="bs-loading"><div className="bs-spinner" /> Chargement des événements…</div>
      ) : isError ? (
        <div className="bs-card">
          <div className="bs-empty">
            <div className="bs-empty-icon" style={{ color: 'var(--danger)' }}>⚠</div>
            <div className="bs-empty-text">Service d'indexation indisponible</div>
            <div className="bs-empty-sub">
              OpenSearch ne répond pas. Vérifiez que le service d'indexation est opérationnel.
            </div>
          </div>
        </div>
      ) : hits.length === 0 ? (
        <div className="bs-card">
          <div className="bs-empty">
            <div className="bs-empty-icon">▦</div>
            <div className="bs-empty-text">Aucun événement</div>
            <div className="bs-empty-sub">
              {submitted ? `Aucun résultat pour « ${submitted} »` : 'Aucun événement indexé pour le moment.'}
            </div>
          </div>
        </div>
      ) : (
        <div className="bs-card" style={{ padding: 0 }}>
          <div style={{
            padding: '12px 16px', borderBottom: '1px solid var(--border)',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span style={{ fontSize: 13, color: 'var(--fg2)', fontWeight: 500 }}>
              {hits.length} événement(s) affichés
              {submitted ? ` pour « ${submitted} »` : ''}
            </span>
            <span className="bs-mono" style={{ fontSize: 11, color: 'var(--fg4)' }}>
              {total > hits.length ? `${total.toLocaleString('fr-FR')} total` : ''}
            </span>
          </div>
          <div className="bs-table-wrap" style={{ border: 'none' }}>
            <table className="bs-table">
              <thead>
                <tr>
                  <th>Horodatage</th>
                  <th>Source / Hôte</th>
                  <th>Catégorie</th>
                  <th>Action / Type</th>
                  <th>Résultat</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {hits.map((h, idx) => {
                  const ts   = pick(h, '@timestamp') ?? pick(h, 'timestamp');
                  const src  = pick(h, 'source.name') ?? pick(h, 'host.name') ?? pick(h, 'observer.name') ?? pick(h, 'source_id') ?? '—';
                  const cat  = pick(h, 'event.category') ?? '—';
                  const act  = pick(h, 'event.action') ?? pick(h, 'event.type') ?? '—';
                  const out  = pick(h, 'event.outcome');
                  const msg  = pick(h, 'message') ?? '';

                  return (
                    <tr key={pick(h, '_id') ?? String(idx)}>
                      <td className="bs-mono" style={{ fontSize: 11, color: 'var(--fg3)', whiteSpace: 'nowrap' }}>
                        {fmtTs(ts)}
                      </td>
                      <td>
                        <span className="bs-code" style={{ fontSize: 11 }}>{src}</span>
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--fg3)' }}>{cat}</td>
                      <td style={{ fontSize: 12, color: 'var(--fg2)' }}>{act}</td>
                      <td>
                        {out ? (
                          <span className={`bs-badge ${out === 'success' ? 'active' : out === 'failure' ? 'critique' : 'neutral'}`}>
                            {out}
                          </span>
                        ) : (
                          <span className="bs-text-muted">—</span>
                        )}
                      </td>
                      <td style={{ maxWidth: 300 }}>
                        <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 11, color: 'var(--fg3)' }}>
                          {msg || '—'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
