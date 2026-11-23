import type { CSSProperties } from 'react';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { alerts as alertsApi, toList } from '../api/analyst';
import type { Alert } from '../api/analyst';
import '../styles/design-system.css';

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1)  return 'à l\'instant';
  if (mins < 60) return `${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs} h`;
  return `${Math.floor(hrs / 24)} j`;
}

export function AlertsPage() {
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState('');
  const limit = 50;

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['alerts', page],
    queryFn: () => alertsApi.list({ limit, offset: page * limit }),
    refetchInterval: 30_000,
  });

  const list     = toList<Alert>(data);
  const critique = list.filter((a) => a.severity === 'CRITIQUE').length;
  const eleve    = list.filter((a) => a.severity === 'ELEVE').length;

  const filtered = filter.trim()
    ? list.filter(
        (a) =>
          a.title?.toLowerCase().includes(filter.toLowerCase()) ||
          a.rule_id?.toLowerCase().includes(filter.toLowerCase()),
      )
    : list;

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title"><span>Alertes</span></h1>
          <p className="bs-page-sub">Actualisation automatique toutes les 30 secondes</p>
        </div>
        {isFetching && !isLoading && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--fg4)' }}>
            <span className="bs-spinner" style={{ width: 12, height: 12 }} /> Actualisation…
          </span>
        )}
      </div>

      {/* KPIs */}
      <div className="bs-kpi-grid">
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--danger)' } as CSSProperties}>
          <div className="bs-kpi-label">Critique</div>
          <div className={`bs-kpi-value ${critique > 0 ? 'bs-glow-danger' : ''}`}>
            {isLoading ? '…' : critique}
          </div>
          <div className="bs-kpi-sub">Alertes de niveau critique</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--warn)' } as CSSProperties}>
          <div className="bs-kpi-label">Élevé</div>
          <div className={`bs-kpi-value ${eleve > 0 ? 'bs-glow-warn' : ''}`}>
            {isLoading ? '…' : eleve}
          </div>
          <div className="bs-kpi-sub">Alertes de niveau élevé</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent2)' } as CSSProperties}>
          <div className="bs-kpi-label">Total (page)</div>
          <div className="bs-kpi-value">{isLoading ? '…' : list.length}</div>
          <div className="bs-kpi-sub">Alertes sur cette page</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent)' } as CSSProperties}>
          <div className="bs-kpi-label">Pagination</div>
          <div className="bs-kpi-value">{page + 1}</div>
          <div className="bs-kpi-sub">Page actuelle</div>
        </div>
      </div>

      {/* Filtre */}
      <div className="bs-filter-bar">
        <div className="bs-input-wrap" style={{ flex: 1, maxWidth: 420 }}>
          <span className="bs-input-icon">⌕</span>
          <input
            className="bs-input"
            type="text"
            placeholder="Filtrer par titre ou identifiant de règle…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        {filter && (
          <span className="bs-stat-pill">
            {filtered.length} résultat(s)
          </span>
        )}
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="bs-loading"><div className="bs-spinner" /> Chargement des alertes…</div>
      ) : (
        <div className="bs-card" style={{ padding: 0 }}>
          <div className="bs-table-wrap" style={{ border: 'none', borderRadius: 'var(--radius) var(--radius) 0 0' }}>
            <table className="bs-table">
              <thead>
                <tr>
                  <th>Sévérité</th>
                  <th>Règle déclenchée</th>
                  <th>Source</th>
                  <th>Titre / Message</th>
                  <th>Délai</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <span className={`bs-badge ${a.severity.toLowerCase()}`}>{a.severity}</span>
                    </td>
                    <td style={{ color: 'var(--fg)', fontWeight: 500, fontSize: 13 }}>
                      {a.rule_id ?? <span className="bs-text-muted">—</span>}
                    </td>
                    <td>
                      <span className="bs-code">{a.source_id ?? '—'}</span>
                    </td>
                    <td style={{ color: 'var(--fg2)', fontSize: 12, maxWidth: 300 }}>
                      <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {a.title}
                      </span>
                    </td>
                    <td className="bs-mono" style={{ fontSize: 11, color: 'var(--fg4)', whiteSpace: 'nowrap' }}>
                      {relTime(a.fired_at)}
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <div className="bs-empty">
                        <div className="bs-empty-icon">◉</div>
                        <div className="bs-empty-text">Aucune alerte trouvée</div>
                        <div className="bs-empty-sub">
                          {filter ? 'Modifiez votre filtre' : 'Aucune alerte sur cette page'}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 16px', borderTop: '1px solid var(--border)',
          }}>
            <button
              className="bs-btn bs-btn-secondary bs-btn-sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              ← Précédent
            </button>
            <span style={{ fontSize: 12, color: 'var(--fg4)' }}>
              Page {page + 1} · {list.length} alerte(s)
            </span>
            <button
              className="bs-btn bs-btn-secondary bs-btn-sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={list.length < limit}
            >
              Suivant →
            </button>
          </div>
        </div>
      )}
    </>
  );
}
