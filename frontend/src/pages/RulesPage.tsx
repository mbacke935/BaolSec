import type { CSSProperties } from 'react';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rules as rulesApi, toList } from '../api/resources';
import type { Rule, RuleCreate, Severity } from '../types/api';
import '../styles/design-system.css';

const SEVERITIES: Severity[] = ['INFO', 'FAIBLE', 'MOYEN', 'ELEVE', 'CRITIQUE'];

export function RulesPage() {
  const qc = useQueryClient();
  const { data: dataRaw, isLoading } = useQuery({
    queryKey: ['rules'],
    queryFn: () => rulesApi.list(),
  });

  const data = toList<Rule>(dataRaw);

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => rulesApi.update(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  });
  const disableMut = useMutation({
    mutationFn: (id: string) => rulesApi.disable(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  });
  const createMut = useMutation({
    mutationFn: (body: RuleCreate) => rulesApi.create(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rules'] }); setShowForm(false); resetForm(); },
  });

  const [showForm, setShowForm]     = useState(false);
  const [name, setName]             = useState('');
  const [severity, setSeverity]     = useState<Severity>('MOYEN');
  const [logicJson, setLogicJson]   = useState('{\n  \n}');
  const [logicError, setLogicError] = useState('');

  function resetForm() { setName(''); setSeverity('MOYEN'); setLogicJson('{\n  \n}'); setLogicError(''); }

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const logic = JSON.parse(logicJson);
      setLogicError('');
      createMut.mutate({ name, severity, logic });
    } catch {
      setLogicError('JSON invalide — vérifiez la syntaxe');
    }
  }

  const activeCount   = data.filter((r) => r.enabled).length;
  const critiqueCount = data.filter((r) => r.severity === 'CRITIQUE' || r.severity === 'ELEVE').length;

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title">Règles de <span>détection</span></h1>
          <p className="bs-page-sub">Gestion des règles de corrélation et d'alerte SIEM</p>
        </div>
        <button className="bs-btn bs-btn-primary bs-btn-sm" onClick={() => { setShowForm((v) => !v); resetForm(); }}>
          {showForm ? 'Fermer' : '+ Nouvelle règle'}
        </button>
      </div>

      {/* KPIs */}
      <div className="bs-kpi-grid">
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--success)' } as CSSProperties}>
          <div className="bs-kpi-label">Règles actives</div>
          <div className="bs-kpi-value bs-glow-accent">{isLoading ? '…' : activeCount}</div>
          <div className="bs-kpi-sub">En cours d'évaluation</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--danger)' } as CSSProperties}>
          <div className="bs-kpi-label">Critique / Élevé</div>
          <div className={`bs-kpi-value ${critiqueCount > 0 ? 'bs-glow-danger' : ''}`}>
            {isLoading ? '…' : critiqueCount}
          </div>
          <div className="bs-kpi-sub">Règles haute sévérité</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent2)' } as CSSProperties}>
          <div className="bs-kpi-label">Total</div>
          <div className="bs-kpi-value">{isLoading ? '…' : data.length}</div>
          <div className="bs-kpi-sub">Règles enregistrées</div>
        </div>
      </div>

      {/* Formulaire de création */}
      {showForm && (
        <div className="bs-card bs-mb-16">
          <div className="bs-section-header">
            <span className="bs-section-title">Nouvelle règle de détection</span>
          </div>
          <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 580 }}>
            <div>
              <label className="bs-label">Nom de la règle *</label>
              <input
                className="bs-input"
                placeholder="ex: Brute Force SSH détecté"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="bs-label">Sévérité</label>
              <select
                className="bs-select"
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity)}
              >
                {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="bs-label">Logique de détection (JSON)</label>
              <textarea
                className="bs-input"
                value={logicJson}
                onChange={(e) => setLogicJson(e.target.value)}
                rows={6}
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12, resize: 'vertical' }}
              />
              {logicError && (
                <div className="bs-error" style={{ marginTop: 6, fontSize: 12 }}>{logicError}</div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', alignItems: 'center' }}>
              {createMut.isError && (
                <span style={{ fontSize: 12, color: 'var(--danger)' }}>Erreur lors de la création</span>
              )}
              <button
                type="button"
                className="bs-btn bs-btn-secondary bs-btn-sm"
                onClick={() => { setShowForm(false); resetForm(); }}
              >
                Annuler
              </button>
              <button type="submit" className="bs-btn bs-btn-primary bs-btn-sm" disabled={createMut.isPending}>
                {createMut.isPending ? '…' : 'Créer la règle'}
              </button>
            </div>
          </form>
        </div>
      )}

      {isLoading ? (
        <div className="bs-loading"><div className="bs-spinner" /> Chargement des règles…</div>
      ) : (
        <div className="bs-card" style={{ padding: 0 }}>
          <div className="bs-table-wrap" style={{ border: 'none', borderRadius: 'var(--radius)' }}>
            <table className="bs-table">
              <thead>
                <tr>
                  <th>Nom</th>
                  <th>Sévérité</th>
                  <th>Statut</th>
                  <th>Version</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r: Rule) => (
                  <tr key={r.id} style={{ opacity: r.enabled ? 1 : 0.5 }}>
                    <td style={{ color: 'var(--fg)', fontWeight: 600, fontSize: 13 }}>
                      {r.name}
                    </td>
                    <td>
                      <span className={`bs-badge ${r.severity.toLowerCase()}`}>{r.severity}</span>
                    </td>
                    <td>
                      <span className={`bs-badge ${r.enabled ? 'active' : 'neutral'}`}>
                        {r.enabled ? 'Active' : 'Désactivée'}
                      </span>
                    </td>
                    <td>
                      <span className="bs-mono bs-code" style={{ fontSize: 11 }}>v{r.version}</span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <button
                          className="bs-btn bs-btn-secondary bs-btn-xs"
                          style={r.enabled
                            ? { color: 'var(--warn)', borderColor: 'rgba(245,158,11,0.3)' }
                            : { color: 'var(--success)', borderColor: 'rgba(16,185,129,0.3)' }
                          }
                          onClick={() => toggleMut.mutate({ id: r.id, enabled: !r.enabled })}
                          disabled={toggleMut.isPending}
                        >
                          {r.enabled ? 'Désactiver' : 'Activer'}
                        </button>
                        <button
                          className="bs-btn bs-btn-danger bs-btn-xs"
                          disabled={disableMut.isPending}
                          onClick={() => {
                            if (window.confirm(`Supprimer la règle « ${r.name} » ? Cette action est irréversible.`)) {
                              disableMut.mutate(r.id);
                            }
                          }}
                        >
                          Supprimer
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {data.length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <div className="bs-empty">
                        <div className="bs-empty-icon">⚡</div>
                        <div className="bs-empty-text">Aucune règle configurée</div>
                        <div className="bs-empty-sub">Créez votre première règle de détection ci-dessus</div>
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
