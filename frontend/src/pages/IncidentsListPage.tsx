import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { incidents as incidentsApi, toList } from '../api/analyst';
import type { Incident, IncidentState } from '../api/analyst';
import '../styles/design-system.css';

const STATE_OPTIONS = [
  { value: '', label: 'Tous' },
  { value: 'OUVERT',       label: 'Ouverts' },
  { value: 'EN_COURS',     label: 'En cours' },
  { value: 'RESOLU',       label: 'Résolus' },
  { value: 'CLOS',         label: 'Clos' },
  { value: 'FAUX_POSITIF', label: 'Faux positif' },
];

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return '< 1 h';
  if (h < 24) return `${h} h`;
  return `${Math.floor(h / 24)} j`;
}

export function IncidentsListPage() {
  const navigate = useNavigate();
  const [stateFilter, setStateFilter] = useState('');
  const [search, setSearch] = useState('');

  const { data: raw, isLoading } = useQuery({
    queryKey: ['incidents', stateFilter],
    queryFn: () =>
      incidentsApi.list(
        stateFilter ? { state: stateFilter as IncidentState, limit: 200 } : { limit: 200 },
      ),
  });

  const data     = toList<Incident>(raw);
  const filtered = data.filter(
    (i) => !search || i.title.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title"><span>Incidents</span></h1>
          <p className="bs-page-sub">
            {isLoading ? 'Chargement…' : `${filtered.length} incident(s) trouvé(s)`}
          </p>
        </div>
      </div>

      {/* Barre de filtres */}
      <div className="bs-filter-bar">
        <div className="bs-input-wrap" style={{ flex: 1, minWidth: 220 }}>
          <span className="bs-input-icon">⌕</span>
          <input
            className="bs-input"
            type="search"
            placeholder="Rechercher un incident…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="bs-pill-group">
          {STATE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStateFilter(opt.value)}
              className={`bs-pill${stateFilter === opt.value ? ' active' : ''}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="bs-loading"><div className="bs-spinner" /> Chargement des incidents…</div>
      ) : (
        <div className="bs-card" style={{ padding: 0 }}>
          <div className="bs-table-wrap" style={{ border: 'none', borderRadius: 'var(--radius)' }}>
            <table className="bs-table">
              <thead>
                <tr>
                  <th>Sévérité</th>
                  <th>Titre de l'incident</th>
                  <th>État</th>
                  <th>Responsable</th>
                  <th>Ouvert</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((inc) => (
                  <tr
                    key={inc.id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/incidents/${inc.id}`)}
                  >
                    <td>
                      <span className={`bs-badge ${inc.severity.toLowerCase()}`}>
                        {inc.severity}
                      </span>
                    </td>
                    <td style={{ color: 'var(--fg)', fontWeight: 500, maxWidth: 320 }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
                        {inc.title}
                      </span>
                    </td>
                    <td>
                      <span className={`bs-badge ${inc.state.toLowerCase()}`}>
                        {inc.state.replace('_', ' ')}
                      </span>
                    </td>
                    <td style={{ color: 'var(--fg3)', fontSize: 12 }}>
                      {inc.assigned_to ?? <span className="bs-text-muted">—</span>}
                    </td>
                    <td className="bs-mono" style={{ fontSize: 11, color: 'var(--fg3)' }}>
                      {relTime(inc.opened_at)}
                    </td>
                    <td>
                      <Link
                        to={`/incidents/${inc.id}`}
                        className="bs-btn bs-btn-secondary bs-btn-xs"
                        onClick={(e) => e.stopPropagation()}
                      >
                        Détails →
                      </Link>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <div className="bs-empty">
                        <div className="bs-empty-icon">⚡</div>
                        <div className="bs-empty-text">Aucun incident trouvé</div>
                        <div className="bs-empty-sub">Modifiez vos critères de recherche</div>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
