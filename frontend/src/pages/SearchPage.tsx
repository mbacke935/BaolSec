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

function highlightMatch(text: string, term: string) {
  if (!term) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(term.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark style={{ background: 'rgba(0,212,170,0.25)', color: 'var(--accent)', borderRadius: 2 }}>
        {text.slice(idx, idx + term.length)}
      </mark>
      {text.slice(idx + term.length)}
    </>
  );
}

export function SearchPage() {
  const [query, setQuery]         = useState('');
  const [submitted, setSubmitted] = useState('');
  const [mode, setMode]           = useState<'events' | 'alerts' | 'incidents'>('events');
  const limit = 50;

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['search', mode, submitted],
    queryFn: () => search[mode](submitted, limit),
    enabled: submitted.trim().length >= 2,
  });

  // data est un SearchResult { total, hits[] }, pas un tableau
  const hits  = data?.hits ?? [];
  const total = data?.total ?? 0;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim().length < 2) return;
    setSubmitted(query.trim());
  }

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title">Recherche <span>SIEM</span></h1>
          <p className="bs-page-sub">Interrogez les événements, alertes et incidents indexés</p>
        </div>
      </div>

      {/* Formulaire de recherche */}
      <div className="bs-card bs-mb-16">
        <form onSubmit={handleSubmit}>
          <div className="bs-input-wrap" style={{ maxWidth: 640 }}>
            <span className="bs-input-icon">⌕</span>
            <input
              className="bs-input"
              type="search"
              placeholder="Rechercher… (min. 2 caractères)"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Sélection du mode */}
            <div className="bs-pill-group" style={{ marginRight: 8 }}>
              {(['events', 'alerts', 'incidents'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`bs-pill${mode === m ? ' active' : ''}`}
                  onClick={() => setMode(m)}
                >
                  {m === 'events' ? 'Événements' : m === 'alerts' ? 'Alertes' : 'Incidents'}
                </button>
              ))}
            </div>
            <button
              type="submit"
              className="bs-btn bs-btn-primary bs-btn-sm"
              disabled={query.trim().length < 2 || isLoading}
            >
              {isLoading ? 'Recherche…' : 'Rechercher'}
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
            {isFetching && !isLoading && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--fg4)' }}>
                <span className="bs-spinner" style={{ width: 12, height: 12 }} /> Actualisation…
              </span>
            )}
          </div>
        </form>
      </div>

      {/* État vide initial */}
      {!submitted && (
        <div className="bs-card">
          <div className="bs-empty">
            <div className="bs-empty-icon" style={{ fontSize: 32 }}>⌕</div>
            <div className="bs-empty-text">Lancez une recherche</div>
            <div className="bs-empty-sub">
              Saisissez un terme (min. 2 car.) puis sélectionnez le type de données à interroger
            </div>
          </div>
        </div>
      )}

      {/* Résultats */}
      {submitted && (
        <>
          {isLoading ? (
            <div className="bs-loading"><div className="bs-spinner" /> Recherche en cours…</div>
          ) : hits.length === 0 ? (
            <div className="bs-card">
              <div className="bs-empty">
                <div className="bs-empty-icon">◉</div>
                <div className="bs-empty-text">Aucun résultat</div>
                <div className="bs-empty-sub">
                  Aucune donnée ne correspond à « {submitted} »
                </div>
              </div>
            </div>
          ) : (
            <div className="bs-card" style={{ padding: 0 }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 13, color: 'var(--fg2)', fontWeight: 500 }}>
                  {total.toLocaleString('fr-FR')} résultat(s) pour « {submitted} »
                </span>
                <span className="bs-mono" style={{ fontSize: 11, color: 'var(--fg4)' }}>
                  {hits.length} affiché(s)
                </span>
              </div>

              <div className="bs-table-wrap" style={{ border: 'none' }}>
                <table className="bs-table">
                  <thead>
                    <tr>
                      <th>Horodatage</th>
                      <th>Source / ID</th>
                      <th>Type / Catégorie</th>
                      <th>Message / Résumé</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hits.map((h, i) => {
                      const ts  = pick(h, '@timestamp') ?? pick(h, 'fired_at') ?? pick(h, 'opened_at') ?? pick(h, 'created_at');
                      const src = pick(h, 'source_id') ?? pick(h, 'source.name') ?? pick(h, 'host.name') ?? '—';
                      const typ = pick(h, 'event.action') ?? pick(h, 'event.category') ?? pick(h, 'severity') ?? pick(h, 'state') ?? '—';
                      const msg = pick(h, 'message') ?? pick(h, 'title') ?? '—';
                      return (
                        <tr key={pick(h, '_id') ?? pick(h, 'id') ?? String(i)}>
                          <td className="bs-mono" style={{ fontSize: 11, color: 'var(--fg3)', whiteSpace: 'nowrap' }}>
                            {ts ? new Date(ts).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                          </td>
                          <td>
                            <span className="bs-code" style={{ fontSize: 11 }}>{src}</span>
                          </td>
                          <td style={{ color: 'var(--fg3)', fontSize: 12 }}>{typ}</td>
                          <td style={{ maxWidth: 400 }}>
                            <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12, color: 'var(--fg2)' }}>
                              {highlightMatch(msg, submitted)}
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
      )}
    </>
  );
}
