/**
 * Supervision — santé des composants de la plateforme.
 * L'API BaolSec expose /health accessible depuis le frontend.
 * Les services internes (workers, broker, BDD) ne sont pas exposés directement.
 */
import type { CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import '../styles/design-system.css';

interface HealthResult {
  status: 'ok' | 'error' | 'loading';
  label: string;
  detail?: string;
}

async function fetchApiHealth(): Promise<HealthResult> {
  try {
    const res = await fetch('/health', { signal: AbortSignal.timeout(5_000) });
    if (!res.ok) return { status: 'error', label: 'baolsec-api', detail: `HTTP ${res.status}` };
    const data = await res.json() as { status: string; service?: string };
    return { status: 'ok', label: data.service ?? 'baolsec-api', detail: data.status };
  } catch {
    return { status: 'error', label: 'baolsec-api', detail: 'Inaccessible' };
  }
}

const INTERNAL_SERVICES = [
  { name: 'Ingestion Gateway',   icon: '→' },
  { name: 'Normalization Worker',icon: '⟳' },
  { name: 'Detection Worker',    icon: '⚡' },
  { name: 'Incident Builder',    icon: '◈' },
  { name: 'Coverage Worker',     icon: '◎' },
  { name: 'Indexing Worker',     icon: '▦' },
  { name: 'NATS JetStream',      icon: '⇄' },
  { name: 'PostgreSQL 17',       icon: '◉' },
  { name: 'OpenSearch 2.19',     icon: '⌕' },
];

export function MonitorPage() {
  const { data: apiHealth, isLoading, dataUpdatedAt } = useQuery({
    queryKey: ['health-api'],
    queryFn: fetchApiHealth,
    refetchInterval: 30_000,
  });

  const apiResult: HealthResult = isLoading
    ? { status: 'loading', label: 'baolsec-api' }
    : (apiHealth ?? { status: 'error', label: 'baolsec-api' });

  const isOk = apiResult.status === 'ok';

  const lastChecked = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '—';

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title">Supervision <span>plateforme</span></h1>
          <p className="bs-page-sub">
            Actualisation automatique toutes les 30 secondes
            {dataUpdatedAt ? ` · Dernière vérif. ${lastChecked}` : ''}
          </p>
        </div>
      </div>

      {/* KPIs */}
      <div className="bs-kpi-grid">
        <div className="bs-kpi" style={{ '--kpi-color': isOk ? 'var(--success)' : 'var(--danger)' } as CSSProperties}>
          <div className="bs-kpi-label">API BaolSec</div>
          <div className={`bs-kpi-value ${isOk ? 'bs-glow-accent' : 'bs-glow-danger'}`} style={{ fontSize: 20 }}>
            {isLoading ? '…' : isOk ? 'Opérationnelle' : 'Dégradée'}
          </div>
          <div className="bs-kpi-sub">{apiResult.detail ?? 'En cours…'}</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--fg4)' } as CSSProperties}>
          <div className="bs-kpi-label">Services internes</div>
          <div className="bs-kpi-value" style={{ fontSize: 28 }}>{INTERNAL_SERVICES.length}</div>
          <div className="bs-kpi-sub">Supervisés via Grafana (C19)</div>
        </div>
      </div>

      {/* Vérifiés en temps réel */}
      <div className="bs-card bs-mb-16">
        <div className="bs-section-header">
          <span className="bs-section-title">Vérifiés en temps réel</span>
          <span style={{ fontSize: 11, color: 'var(--fg4)' }} className="bs-mono">
            ping /health toutes les 30 s
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {/* API principale */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '12px 14px',
            background: isOk ? 'rgba(16,185,129,0.06)' : 'rgba(255,68,102,0.06)',
            borderRadius: 'var(--radius)',
            border: `1px solid ${isOk ? 'rgba(16,185,129,0.2)' : 'rgba(255,68,102,0.2)'}`,
          }}>
            <div style={{
              width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
              background: isOk ? 'var(--success)' : apiResult.status === 'loading' ? 'var(--fg4)' : 'var(--danger)',
              boxShadow: isOk ? '0 0 6px var(--success)' : apiResult.status === 'error' ? '0 0 6px var(--danger)' : 'none',
            }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>API BaolSec</div>
              <div className="bs-mono" style={{ fontSize: 11, color: 'var(--fg4)' }}>
                {apiResult.detail ?? '—'}
              </div>
            </div>
            <span className={`bs-badge ${isOk ? 'active' : apiResult.status === 'loading' ? 'neutral' : 'critique'}`}>
              {isLoading ? 'Vérification…' : isOk ? 'Opérationnel' : 'Dégradé'}
            </span>
          </div>
        </div>
      </div>

      {/* Services internes */}
      <div className="bs-card">
        <div className="bs-section-header">
          <span className="bs-section-title">Services internes</span>
          <a
            href="https://grafana.baolsec.local"
            target="_blank"
            rel="noopener noreferrer"
            className="bs-btn bs-btn-secondary bs-btn-xs"
          >
            Ouvrir Grafana ↗
          </a>
        </div>
        <p style={{ fontSize: 12, color: 'var(--fg4)', marginBottom: 14 }}>
          Ces services ne sont pas directement exposés au frontend.
          Leur supervision complète (métriques, logs, alertes) est assurée par <strong>Prometheus + Grafana (C19)</strong>.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 8 }}>
          {INTERNAL_SERVICES.map(({ name, icon }) => (
            <div
              key={name}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px',
                background: 'rgba(255,255,255,0.03)',
                borderRadius: 'calc(var(--radius) - 2px)',
                border: '1px solid var(--border)',
              }}
            >
              <span style={{
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                background: 'var(--fg4)',
              }} />
              <span style={{ flex: 1, fontSize: 13, color: 'var(--fg2)' }}>
                <span style={{ marginRight: 6, opacity: 0.5 }}>{icon}</span>
                {name}
              </span>
              <span style={{ fontSize: 11, color: 'var(--fg4)' }}>Non exposé</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
