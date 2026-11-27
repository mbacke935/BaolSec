/** Préchargement au survol : l'écran de détail s'ouvre avec ses données déjà en cache. */
import type { QueryClient } from '@tanstack/react-query';
import { incidents } from '../api/endpoints';

export function prefetchIncident(qc: QueryClient, id: string): void {
  const opts = { staleTime: 15_000 };
  qc.prefetchQuery({ queryKey: ['incident', id], queryFn: () => incidents.get(id), ...opts });
  qc.prefetchQuery({ queryKey: ['incident', id, 'timeline'], queryFn: () => incidents.timeline(id), ...opts });
  qc.prefetchQuery({ queryKey: ['incident', id, 'alerts'], queryFn: () => incidents.alerts(id), ...opts });
}
