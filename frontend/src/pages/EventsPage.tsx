/**
 * Flux d'événements — table (maquette) câblée à POST /search/events (OpenSearch).
 * La recherche globale de la barre haute sert de requête. Champs lus au format ECS.
 */
import { useQuery } from '@tanstack/react-query';
import { search } from '../api/analyst';
import { useSearch } from '../components/AppShell';
import { fmtDateTime } from '../lib/ui';

/** Lit un champ ECS qu'il soit imbriqué (source.name) ou aplati ("source.name"). */
function pick(doc: Record<string, unknown>, path: string): string | undefined {
  if (doc[path] != null) return String(doc[path]);
  let cur: unknown = doc;
  for (const part of path.split('.')) {
    if (cur && typeof cur === 'object' && part in (cur as object)) cur = (cur as Record<string, unknown>)[part];
    else return undefined;
  }
  return cur == null ? undefined : String(cur);
}

export function EventsPage() {
  const q = useSearch();
  const evQ = useQuery({
    queryKey: ['events', q],
    queryFn: () => search.events(q, 50),
    retry: false,
  });

  const hits = evQ.data?.hits ?? [];

  return (
    <div className="panel">
      <h3>Flux d'événements {evQ.data ? <span style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 12 }}>· {evQ.data.total} résultat(s)</span> : null}</h3>
      <p className="empty-note" style={{ padding: '0 0 12px' }}>
        Exploration des événements bruts et normalisés. Saisissez une requête dans la barre de recherche.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>HORODATAGE</th><th>SOURCE</th><th>TYPE</th><th>RÉSULTAT</th></tr>
          </thead>
          <tbody>
            {hits.map((h, idx) => (
              <tr key={(h._id as string) ?? idx}>
                <td>{fmtDateTime(pick(h, '@timestamp'))}</td>
                <td>{pick(h, 'source.name') ?? pick(h, 'host.name') ?? pick(h, 'observer.name') ?? '—'}</td>
                <td>{pick(h, 'event.action') ?? pick(h, 'event.category') ?? pick(h, 'event.type') ?? '—'}</td>
                <td>{pick(h, 'event.outcome') ?? '—'}</td>
              </tr>
            ))}
            {evQ.isLoading && <tr><td colSpan={4} className="empty-note">Recherche…</td></tr>}
            {evQ.isError && <tr><td colSpan={4} className="empty-note">Indexation indisponible (OpenSearch). Vérifiez le service d'indexation.</td></tr>}
            {!evQ.isLoading && !evQ.isError && hits.length === 0 && (
              <tr><td colSpan={4} className="empty-note">Aucun événement pour cette requête.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
