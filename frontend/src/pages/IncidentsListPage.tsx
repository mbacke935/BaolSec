/**
 * Liste des incidents avec filtres (C23) — design aligné sur la maquette BaolSec.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { incidents as incidentsApi } from '../api/analyst';
import type { Incident, IncidentState } from '../api/analyst';

const SEV_STYLE: Record<string, { bg: string; color: string }> = {
  CRITIQUE: { bg: '#5b202a', color: '#ff9ba4' },
  ELEVE:    { bg: '#59451e', color: '#f4cd7a' },
  MOYEN:    { bg: '#3a3010', color: '#f4cd7a' },
  FAIBLE:   { bg: '#123d35', color: '#6fe0b4' },
  INFO:     { bg: '#0c2340', color: '#7bbef0' },
};

const STATE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'Tous' },
  { value: 'OUVERT', label: 'Ouverts' },
  { value: 'EN_COURS', label: 'En cours' },
  { value: 'RESOLU', label: 'Résolus' },
  { value: 'CLOS', label: 'Clos' },
  { value: 'FAUX_POSITIF', label: 'Faux positif' },
];

export function IncidentsListPage() {
  const [stateFilter, setStateFilter] = useState('');

  const { data = [], isLoading } = useQuery({
    queryKey: ['incidents', stateFilter],
    queryFn: () => incidentsApi.list(stateFilter ? { state: stateFilter as IncidentState, limit: 100 } : { limit: 100 }),
  });

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', margin: 0 }}>Incidents</h2>
          <p style={{ color: 'var(--muted)', margin: '4px 0 0', fontSize: '0.8rem' }}>{data.length} résultat(s)</p>
        </div>
        {/* Filtre état */}
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {STATE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStateFilter(opt.value)}
              style={{
                padding: '0.3rem 0.75rem', borderRadius: '20px', border: '1px solid',
                borderColor: stateFilter === opt.value ? 'var(--green2)' : 'var(--line)',
                background: stateFilter === opt.value ? '#16a36b20' : 'transparent',
                color: stateFilter === opt.value ? 'var(--green2)' : 'var(--muted)',
                fontSize: '0.78rem', cursor: 'pointer',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <p style={{ color: 'var(--muted)' }}>Chargement…</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
          <thead>
            <tr>
              {['Titre', 'Sévérité', 'État', 'Ouvert le', ''].map((h) => (
                <th key={h} style={{ textAlign: 'left', padding: '0.75rem 0.5rem', color: '#7f96ab', fontWeight: 600, borderBottom: '1px solid var(--line)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((inc: Incident) => {
              const sev = SEV_STYLE[inc.severity] || SEV_STYLE.INFO;
              return (
                <tr key={inc.id} style={{ borderBottom: '1px solid #1a3044' }}>
                  <td style={{ padding: '0.85rem 0.5rem', color: '#cbd7e2' }}>{inc.title}</td>
                  <td style={{ padding: '0.85rem 0.5rem' }}>
                    <span style={{ padding: '3px 8px', borderRadius: '20px', fontSize: '0.7rem', background: sev.bg, color: sev.color }}>
                      {inc.severity}
                    </span>
                  </td>
                  <td style={{ padding: '0.85rem 0.5rem', color: 'var(--muted)' }}>{inc.state}</td>
                  <td style={{ padding: '0.85rem 0.5rem', color: 'var(--muted)' }}>
                    {new Date(inc.opened_at).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })}
                  </td>
                  <td style={{ padding: '0.85rem 0.5rem' }}>
                    <Link
                      to={`/incidents/${inc.id}`}
                      style={{ color: 'var(--green2)', textDecoration: 'none', fontSize: '0.78rem' }}
                    >
                      Voir →
                    </Link>
                  </td>
                </tr>
              );
            })}
            {data.length === 0 && (
              <tr><td colSpan={5} style={{ padding: '1.5rem 0.5rem', color: 'var(--muted)' }}>Aucun incident</td></tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
