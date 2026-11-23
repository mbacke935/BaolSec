import { useParams, Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { incidents as incidentsApi, toList } from '../api/analyst';
import type { Alert, IncidentState, TimelineEntry } from '../api/analyst';
import '../styles/design-system.css';

const STATE_OPTIONS: IncidentState[] = ['OUVERT', 'EN_COURS', 'RESOLU', 'CLOS', 'FAUX_POSITIF'];

const ENTRY_ICONS: Record<string, string> = {
  ALERTE:          '⚡',
  CHANGEMENT_ETAT: '↻',
  COMMENTAIRE:     '💬',
  ASSIGNATION:     '◎',
  FERMETURE:       '✓',
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const { data: incident, isLoading } = useQuery({
    queryKey: ['incident', id],
    queryFn: () => incidentsApi.get(id!),
    enabled: !!id,
  });
  const { data: timelineRaw = [] } = useQuery({
    queryKey: ['timeline', id],
    queryFn: () => incidentsApi.timeline(id!),
    enabled: !!id,
  });
  const { data: incAlertsRaw = [] } = useQuery({
    queryKey: ['incident-alerts', id],
    queryFn: () => incidentsApi.alerts(id!),
    enabled: !!id,
  });

  const timeline  = toList<TimelineEntry>(timelineRaw);
  const incAlerts = toList<Alert>(incAlertsRaw);

  const updateMut = useMutation({
    mutationFn: (state: IncidentState) => incidentsApi.updateState(id!, state),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['incident', id] });
      qc.invalidateQueries({ queryKey: ['timeline', id] });
    },
  });

  if (isLoading) {
    return <div className="bs-loading"><div className="bs-spinner" /> Chargement de l'incident…</div>;
  }
  if (!incident) {
    return (
      <div className="bs-card">
        <div className="bs-empty">
          <div className="bs-empty-icon">⚡</div>
          <div className="bs-empty-text">Incident introuvable</div>
          <Link to="/incidents" className="bs-btn bs-btn-secondary bs-btn-sm" style={{ marginTop: 12 }}>
            ← Retour aux incidents
          </Link>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Breadcrumb + badges */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <Link to="/incidents" className="bs-btn bs-btn-secondary bs-btn-xs">← Incidents</Link>
        <span className={`bs-badge ${incident.severity.toLowerCase()}`}>{incident.severity}</span>
        <span className={`bs-badge ${incident.state.toLowerCase()}`}>{incident.state.replace('_', ' ')}</span>
        <span className="bs-mono" style={{ fontSize: 11, color: 'var(--fg4)' }}>
          #{incident.id.slice(0, 8)}
        </span>
      </div>

      {/* Titre + contrôle d'état */}
      <div className="bs-page-header" style={{ marginBottom: 24 }}>
        <div style={{ flex: 1 }}>
          <h1 className="bs-page-title" style={{ fontSize: 22 }}>{incident.title}</h1>
          {incident.description && (
            <p className="bs-page-sub" style={{ marginTop: 6 }}>{incident.description}</p>
          )}
        </div>
        <div>
          <label className="bs-label bs-mb-4">Modifier l'état</label>
          <select
            className="bs-select"
            value={incident.state}
            onChange={(e) => updateMut.mutate(e.target.value as IncidentState)}
            style={{ width: 'auto' }}
          >
            {STATE_OPTIONS.map((s) => (
              <option key={s} value={s}>{s.replace('_', ' ')}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Métadonnées */}
      <div className="bs-card bs-mb-16">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 0 }}>
          <div style={{ padding: '0 20px 0 0', borderRight: '1px solid var(--border)' }}>
            <div className="bs-label bs-mb-4">Ouvert le</div>
            <div className="bs-mono" style={{ fontSize: 13, color: 'var(--fg)' }}>{formatDate(incident.opened_at)}</div>
          </div>
          <div style={{ padding: '0 20px', borderRight: '1px solid var(--border)' }}>
            <div className="bs-label bs-mb-4">Responsable</div>
            <div style={{ fontSize: 13, color: incident.assigned_to ? 'var(--fg)' : 'var(--fg4)' }}>
              {incident.assigned_to ?? 'Non assigné'}
            </div>
          </div>
          <div style={{ padding: '0 0 0 20px' }}>
            <div className="bs-label bs-mb-4">Fermé le</div>
            <div className="bs-mono" style={{ fontSize: 13, color: incident.closed_at ? 'var(--fg)' : 'var(--fg4)' }}>
              {incident.closed_at ? formatDate(incident.closed_at) : '—'}
            </div>
          </div>
        </div>
      </div>

      <div className="bs-grid-2">
        {/* Chronologie */}
        <div className="bs-card">
          <div className="bs-section-header">
            <span className="bs-section-title">Chronologie</span>
            <span className="bs-section-count">{timeline.length}</span>
          </div>

          {timeline.length === 0 ? (
            <div className="bs-empty">
              <div className="bs-empty-text">Aucune entrée de chronologie</div>
            </div>
          ) : (
            <div className="bs-timeline">
              {timeline.map((entry) => (
                <div key={entry.id} className="bs-timeline-entry">
                  <div className="bs-timeline-time">{formatDate(entry.occurred_at)}</div>
                  <div className="bs-timeline-content">
                    {ENTRY_ICONS[entry.entry_type] ?? '·'}{' '}
                    {entry.entry_type.replace(/_/g, ' ')}
                  </div>
                  {entry.detail && Object.keys(entry.detail).length > 0 && (
                    <div className="bs-timeline-detail">
                      {JSON.stringify(entry.detail, null, 2)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Alertes associées */}
        <div className="bs-card">
          <div className="bs-section-header">
            <span className="bs-section-title">Alertes déclenchantes</span>
            <span className="bs-section-count">{incAlerts.length}</span>
          </div>

          {incAlerts.length === 0 ? (
            <div className="bs-empty">
              <div className="bs-empty-text">Aucune alerte associée</div>
            </div>
          ) : (
            <div className="bs-list">
              {incAlerts.map((a) => (
                <div
                  key={a.id}
                  className="bs-list-item"
                  style={{ cursor: 'default', flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}
                >
                  <div className="bs-flex-between" style={{ width: '100%' }}>
                    <span className="bs-list-item-title">{a.title}</span>
                    <span className={`bs-badge ${a.severity.toLowerCase()}`}>{a.severity}</span>
                  </div>
                  <div className="bs-mono" style={{ fontSize: 10, color: 'var(--fg4)' }}>
                    {formatDate(a.fired_at)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
