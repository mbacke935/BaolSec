import type { CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { coverage as coverageApi, toList, type CoverageState } from '../api/analyst';
import '../styles/design-system.css';

function NormBar({ ratio }: { ratio: number }) {
  const pct   = Math.round(Math.min(1, Math.max(0, ratio)) * 100);
  const color = pct > 90 ? 'var(--success)' : pct > 60 ? 'var(--warn)' : 'var(--danger)';
  return (
    <div>
      <div className="bs-flex-between bs-mb-4">
        <span className="bs-text-xs bs-text-muted">Taux de normalisation</span>
        <span className="bs-text-xs" style={{ color, fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{pct}%</span>
      </div>
      <div className="bs-progress-bar">
        <div className="bs-progress-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function stateClass(s: string) {
  if (s === 'ACTIVE')        return 'active';
  if (s === 'SILENCIEUSE')   return 'silencieuse';
  if (s === 'FLUX_INCOMPLET')return 'flux_incomplet';
  return 'neutral';
}

function stateLabel(s: string) {
  const labels: Record<string, string> = {
    ACTIVE:        'Active',
    SILENCIEUSE:   'Silencieuse',
    FLUX_INCOMPLET:'Flux incomplet',
    DESACTIVEE:    'Désactivée',
    INCONNUE:      'Inconnue',
  };
  return labels[s] ?? s;
}

export function CoveragePage() {
  const { data: listRaw, isLoading } = useQuery({
    queryKey: ['coverage'],
    queryFn: () => coverageApi.list(),
    refetchInterval: 30_000,
  });

  const list = toList<CoverageState>(listRaw);

  const active      = list.filter((c) => c.state === 'ACTIVE').length;
  const degraded    = list.filter((c) => ['SILENCIEUSE', 'FLUX_INCOMPLET'].includes(c.state)).length;
  const totalEvents = list.reduce((acc, c) => acc + (c.received_count ?? 0), 0);

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title">Couverture <span>sources</span></h1>
          <p className="bs-page-sub">Actualisation automatique toutes les 30 secondes</p>
        </div>
      </div>

      {/* KPIs */}
      <div className="bs-kpi-grid">
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--success)' } as CSSProperties}>
          <div className="bs-kpi-label">Sources actives</div>
          <div className="bs-kpi-value bs-glow-accent">{isLoading ? '…' : active}</div>
          <div className="bs-kpi-sub">Flux en réception nominale</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--warn)' } as CSSProperties}>
          <div className="bs-kpi-label">Sources dégradées</div>
          <div className={`bs-kpi-value ${degraded > 0 ? 'bs-glow-warn' : ''}`}>
            {isLoading ? '…' : degraded}
          </div>
          <div className="bs-kpi-sub">Silencieuses ou flux incomplets</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent2)' } as CSSProperties}>
          <div className="bs-kpi-label">Total sources</div>
          <div className="bs-kpi-value">{isLoading ? '…' : list.length}</div>
          <div className="bs-kpi-sub">Sources configurées</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent)' } as CSSProperties}>
          <div className="bs-kpi-label">Événements reçus</div>
          <div className="bs-kpi-value" style={{ fontSize: 28 }}>
            {isLoading ? '…' : totalEvents.toLocaleString('fr-FR')}
          </div>
          <div className="bs-kpi-sub">Cumul toutes sources</div>
        </div>
      </div>

      {isLoading ? (
        <div className="bs-loading"><div className="bs-spinner" /> Chargement de la couverture…</div>
      ) : list.length === 0 ? (
        <div className="bs-card">
          <div className="bs-empty">
            <div className="bs-empty-icon">◎</div>
            <div className="bs-empty-text">Aucune source configurée</div>
            <div className="bs-empty-sub">Ajoutez des sources depuis l'administration</div>
          </div>
        </div>
      ) : (
        <div className="bs-source-grid">
          {list.map((c) => {
            const normRatio = c.received_count > 0 ? c.normalized_count / c.received_count : 0;
            return (
              <div key={c.source_id} className="bs-card bs-card-hover">
                <div className="bs-flex-between bs-mb-16">
                  <span style={{ fontWeight: 600, color: 'var(--fg)', fontSize: 14 }}>
                    {c.source_name}
                  </span>
                  <span className={`bs-badge ${stateClass(c.state)}`}>{stateLabel(c.state)}</span>
                </div>

                <NormBar ratio={normRatio} />

                <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <div className="bs-detail-row">
                    <span className="bs-detail-key">Événements reçus</span>
                    <span className="bs-mono" style={{ fontSize: 12 }}>
                      {c.received_count.toLocaleString('fr-FR')}
                    </span>
                  </div>
                  <div className="bs-detail-row">
                    <span className="bs-detail-key">Normalisés</span>
                    <span className="bs-mono" style={{ fontSize: 12 }}>
                      {c.normalized_count.toLocaleString('fr-FR')}
                    </span>
                  </div>
                  <div className="bs-detail-row">
                    <span className="bs-detail-key">Dernière réception</span>
                    <span className="bs-mono" style={{ fontSize: 11, color: 'var(--fg3)' }}>
                      {c.last_received_at
                        ? new Date(c.last_received_at).toLocaleString('fr-FR')
                        : '—'}
                    </span>
                  </div>
                  {c.last_processed_at && (
                    <div className="bs-detail-row">
                      <span className="bs-detail-key">Dernier traitement</span>
                      <span className="bs-mono" style={{ fontSize: 11, color: 'var(--fg3)' }}>
                        {new Date(c.last_processed_at).toLocaleString('fr-FR')}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
