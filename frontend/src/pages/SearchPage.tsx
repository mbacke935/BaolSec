/**
 * Page de recherche full-text sur événements/alertes/incidents (C23).
 */
import { useState } from 'react';
import { search as searchApi } from '../api/analyst';

type SearchIndex = 'events' | 'alerts' | 'incidents';

export function SearchPage() {
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState<SearchIndex>('events');
  const [results, setResults] = useState<{ total: number; hits: Array<Record<string, unknown>> } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError('');
    setResults(null);
    try {
      const res = await searchApi[index](query.trim());
      setResults(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erreur de recherche');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '1.5rem' }}>Recherche</h1>

      <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {/* Sélecteur d'index */}
        <div style={{ display: 'flex', borderRadius: '0.375rem', overflow: 'hidden', border: '1px solid #334155' }}>
          {(['events', 'alerts', 'incidents'] as SearchIndex[]).map((idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => setIndex(idx)}
              style={{
                padding: '0.4rem 0.75rem', background: index === idx ? '#0ea5e9' : '#1e293b',
                color: index === idx ? '#fff' : '#94a3b8', border: 'none', cursor: 'pointer',
                fontSize: '0.85rem', textTransform: 'capitalize',
              }}
            >
              {idx === 'events' ? 'Événements' : idx === 'alerts' ? 'Alertes' : 'Incidents'}
            </button>
          ))}
        </div>

        {/* Champ de recherche */}
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder='Requête Lucene (ex: severity:ELEVE AND source:"firewall")'
          style={{
            flex: 1, minWidth: '300px', padding: '0.4rem 0.75rem', borderRadius: '0.375rem',
            border: '1px solid #334155', background: '#0f172a', color: '#e2e8f0', fontSize: '0.9rem',
          }}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          style={{ padding: '0.4rem 1.25rem', background: '#0ea5e9', color: '#fff', border: 'none', borderRadius: '0.375rem', cursor: 'pointer' }}
        >
          {loading ? '…' : 'Rechercher'}
        </button>
      </form>

      {error && <p style={{ color: '#f87171', marginBottom: '1rem' }}>{error}</p>}

      {results && (
        <div>
          <p style={{ color: '#64748b', fontSize: '0.85rem', marginBottom: '1rem' }}>
            {results.total} résultat(s)
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {results.hits.map((hit, idx) => (
              <div key={idx} style={{ background: '#1e293b', borderRadius: '0.375rem', padding: '0.75rem 1rem' }}>
                <pre style={{
                  margin: 0, fontSize: '0.78rem', color: '#94a3b8',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  fontFamily: 'ui-monospace, monospace',
                }}>
                  {JSON.stringify(hit, null, 2)}
                </pre>
              </div>
            ))}
            {results.hits.length === 0 && (
              <p style={{ color: '#64748b', fontSize: '0.9rem' }}>Aucun résultat</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
