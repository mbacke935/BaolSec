/**
 * Page état de couverture (C23).
 */
import { useQuery } from '@tanstack/react-query';
import { coverage as coverageApi, type CoverageState } from '../api/analyst';

const STATE_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  ACTIVE:         { bg: '#052e16', text: '#6ee7b7', label: 'Active' },
  SILENCIEUSE:    { bg: '#422006', text: '#fde68a', label: 'Silencieuse' },
  FLUX_INCOMPLET: { bg: '#431407', text: '#fdba74', label: 'Flux incomplet' },
  DESACTIVEE:     { bg: '#1e293b', text: '#64748b', label: 'Désactivée' },
  INCONNUE:       { bg: '#1e293b', text: '#64748b', label: 'Inconnue' },
};

function Bar({ ratio }: { ratio: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, ratio)) * 100);
  return (
    <div style={{ background: '#0f172a', borderRadius: '99px', height: '6px', overflow: 'hidden', minWidth: '80px' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: pct > 90 ? '#22c55e' : pct > 60 ? '#eab308' : '#ef4444', transition: 'width 0.3s' }} />
    </div>
  );
}

export function CoveragePage() {
  const { data: list = [], isLoading } = useQuery({
    queryKey: ['coverage'],
    queryFn: () => coverageApi.list(),
    refetchInterval: 30_000,  // actualisation toutes les 30s
  });

  const active = list.filter((c: CoverageState) => c.state === 'ACTIVE').length;
  const degraded = list.filter((c: CoverageState) => ['SILENCIEUSE', 'FLUX_INCOMPLET'].includes(c.state)).length;

  return (
    <div>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>Couverture sources</h1>
      <p style={{ color: '#64748b', fontSize: '0.85rem', marginBottom: '1.5rem' }}>
        {active} active(s) · {degraded} dégradée(s) · actualisé toutes les 30 s
      </p>

      {isLoading ? (
        <p style={{ color: '#64748b' }}>Chargement…</p>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
          {list.map((c: CoverageState) => {
            const ss = STATE_STYLE[c.state] || STATE_STYLE.INCONNUE;
            const normRatio = c.received_count > 0 ? c.normalized_count / c.received_count : 0;
            return (
              <div key={c.source_id} style={{ background: '#1e293b', borderRadius: '0.5rem', padding: '1.25rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <span style={{ fontWeight: 600 }}>{c.source_name}</span>
                  <span style={{ padding: '0.2rem 0.5rem', borderRadius: '0.25rem', fontSize: '0.7rem', background: ss.bg, color: ss.text }}>
                    {ss.label}
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#94a3b8' }}>
                    <span>Normalisation</span>
                    <span>{c.normalized_count} / {c.received_count}</span>
                  </div>
                  <Bar ratio={normRatio} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#64748b' }}>
                    <span>Dernière réception</span>
                    <span>{c.last_received_at ? new Date(c.last_received_at).toLocaleString('fr-FR') : '—'}</span>
                  </div>
                </div>
              </div>
            );
          })}
          {list.length === 0 && <p style={{ color: '#64748b', fontSize: '0.9rem' }}>Aucune source</p>}
        </div>
      )}
    </div>
  );
}
