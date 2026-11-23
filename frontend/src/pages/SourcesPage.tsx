import { useState, useEffect, useCallback } from 'react';
import { apiClient as api } from '../api/client';

// ─── Types ───────────────────────────────────────────────────────────────────

type SourceType    = 'linux' | 'windows' | 'firewall' | 'http';
type Transport     = 'https' | 'syslog';
type IngestionMode = 'direct' | 'rejeu';
type Criticality   = 'faible' | 'moyenne' | 'elevee' | 'critique';
type Environment   = 'production' | 'staging' | 'test' | 'developpement';

interface SourceConfig {
  transport: Transport;
  ingestion_mode: IngestionMode;
  host: string | null;
  criticality: Criticality | null;
  expected_min_events_per_h: number | null;
  hostname: string | null;
  ip_address: string | null;
  environment: Environment | null;
  tags: string[];
  responsible: string | null;
}

interface Source {
  id: string;
  name: string;
  description: string | null;
  type: SourceType;
  active: boolean;
  silence_threshold_s: number;
  config: SourceConfig;
  created_at: string;
  updated_at: string;
}

function toList<T>(raw: unknown): T[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw as T[];
  const r = raw as Record<string, unknown>;
  if (Array.isArray(r.items)) return r.items as T[];
  return [];
}

// ─── Stepper Modal ───────────────────────────────────────────────────────────

const STEPS = ['Identification', 'Collecte', 'Supervision', 'Confirmation'];

interface FormState {
  // Step 1
  name: string;
  type: SourceType;
  hostname: string;
  ip_address: string;
  environment: Environment | '';
  criticality: Criticality | '';
  description: string;
  // Step 2
  transport: Transport;
  ingestion_mode: IngestionMode;
  host: string;
  expected_min_events_per_h: string;
  // Step 3
  silence_threshold_s: string;
  tags: string;
  responsible: string;
  active: boolean;
}

const INITIAL: FormState = {
  name: '', type: 'linux', hostname: '', ip_address: '',
  environment: '', criticality: '', description: '',
  transport: 'https', ingestion_mode: 'direct', host: '',
  expected_min_events_per_h: '',
  silence_threshold_s: '600', tags: '', responsible: '', active: true,
};

function SourceModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [step, setStep]     = useState(0);
  const [form, setForm]     = useState<FormState>(INITIAL);
  const [error, setError]   = useState('');
  const [saving, setSaving] = useState(false);

  const set = (k: keyof FormState, v: string | boolean) =>
    setForm(f => ({ ...f, [k]: v }));

  // ── Validation par étape ──
  function validateStep(s: number): string {
    if (s === 0 && !form.name.trim()) return 'Le nom est obligatoire.';
    return '';
  }

  function next() {
    const err = validateStep(step);
    if (err) { setError(err); return; }
    setError('');
    setStep(s => Math.min(s + 1, 3));
  }
  function prev() { setError(''); setStep(s => Math.max(s - 1, 0)); }

  async function submit() {
    setSaving(true);
    setError('');
    try {
      const tagList = form.tags.split(',').map(t => t.trim()).filter(Boolean);
      const body = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        type: form.type,
        active: form.active,
        silence_threshold_s: parseInt(form.silence_threshold_s, 10),
        config: {
          transport: form.transport,
          ingestion_mode: form.ingestion_mode,
          host: form.host.trim() || null,
          criticality: form.criticality || null,
          expected_min_events_per_h: form.expected_min_events_per_h
            ? parseInt(form.expected_min_events_per_h, 10) : null,
          hostname:   form.hostname.trim() || null,
          ip_address: form.ip_address.trim() || null,
          environment: form.environment || null,
          tags: tagList,
          responsible: form.responsible.trim() || null,
        },
      };
      await api.post('/sources', body);
      onCreated();
      onClose();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err?.response?.data?.detail ?? err?.message ?? 'Erreur inattendue');
    } finally {
      setSaving(false);
    }
  }

  // ── Rendu des étapes ──
  function renderStep() {
    switch (step) {
      case 0: return (
        <div className="bs-form-grid">
          <label className="bs-label">Nom <span className="bs-required">*</span></label>
          <input className="bs-input" placeholder="ex. firewall-paris-01"
            value={form.name} onChange={e => set('name', e.target.value)} autoFocus />

          <label className="bs-label">Type de source</label>
          <select className="bs-select" value={form.type}
            onChange={e => set('type', e.target.value as SourceType)}>
            <option value="linux">Linux</option>
            <option value="windows">Windows</option>
            <option value="firewall">Firewall</option>
            <option value="http">HTTP</option>
          </select>

          <label className="bs-label">Hostname</label>
          <input className="bs-input" placeholder="ex. srv-prod-01.internal"
            value={form.hostname} onChange={e => set('hostname', e.target.value)} />

          <label className="bs-label">Adresse IP</label>
          <input className="bs-input" placeholder="ex. 192.168.1.10"
            value={form.ip_address} onChange={e => set('ip_address', e.target.value)} />

          <label className="bs-label">Environnement</label>
          <select className="bs-select" value={form.environment}
            onChange={e => set('environment', e.target.value as Environment | '')}>
            <option value="">— Non défini —</option>
            <option value="production">Production</option>
            <option value="staging">Staging</option>
            <option value="test">Test</option>
            <option value="developpement">Développement</option>
          </select>

          <label className="bs-label">Criticité</label>
          <select className="bs-select" value={form.criticality}
            onChange={e => set('criticality', e.target.value as Criticality | '')}>
            <option value="">— Non définie —</option>
            <option value="faible">Faible</option>
            <option value="moyenne">Moyenne</option>
            <option value="elevee">Élevée</option>
            <option value="critique">Critique</option>
          </select>

          <label className="bs-label">Description</label>
          <textarea className="bs-input" rows={3} placeholder="Description optionnelle…"
            value={form.description} onChange={e => set('description', e.target.value)} />
        </div>
      );

      case 1: return (
        <div className="bs-form-grid">
          <label className="bs-label">Transport</label>
          <select className="bs-select" value={form.transport}
            onChange={e => set('transport', e.target.value as Transport)}>
            <option value="https">HTTPS</option>
            <option value="syslog">Syslog</option>
          </select>

          <label className="bs-label">Mode d'ingestion</label>
          <select className="bs-select" value={form.ingestion_mode}
            onChange={e => set('ingestion_mode', e.target.value as IngestionMode)}>
            <option value="direct">Direct</option>
            <option value="rejeu">Rejeu</option>
          </select>

          <label className="bs-label">Host / gateway de collecte</label>
          <input className="bs-input" placeholder="ex. collector.baolsec.local"
            value={form.host} onChange={e => set('host', e.target.value)} />

          <label className="bs-label">Événements minimum / heure</label>
          <input className="bs-input" type="number" min="0"
            placeholder="ex. 100 (laisser vide = pas de seuil)"
            value={form.expected_min_events_per_h}
            onChange={e => set('expected_min_events_per_h', e.target.value)} />
        </div>
      );

      case 2: return (
        <div className="bs-form-grid">
          <label className="bs-label">Seuil de silence</label>
          <select className="bs-select" value={form.silence_threshold_s}
            onChange={e => set('silence_threshold_s', e.target.value)}>
            <option value="300">5 minutes</option>
            <option value="600">10 minutes</option>
            <option value="900">15 minutes</option>
            <option value="1800">30 minutes</option>
            <option value="3600">1 heure</option>
          </select>

          <label className="bs-label">Tags <span className="bs-hint">(séparés par des virgules)</span></label>
          <input className="bs-input" placeholder="ex. dmz, paris, critique"
            value={form.tags} onChange={e => set('tags', e.target.value)} />

          <label className="bs-label">Responsable</label>
          <input className="bs-input" placeholder="ex. Jean Dupont ou equipe-soc"
            value={form.responsible} onChange={e => set('responsible', e.target.value)} />

          <label className="bs-label">Statut initial</label>
          <div className="bs-toggle-row">
            <label className="bs-toggle">
              <input type="checkbox" checked={form.active}
                onChange={e => set('active', e.target.checked)} />
              <span className="bs-toggle-slider" />
            </label>
            <span>{form.active ? 'Active' : 'Désactivée'}</span>
          </div>
        </div>
      );

      case 3: {
        const tagList = form.tags.split(',').map(t => t.trim()).filter(Boolean);
        return (
          <div className="bs-summary">
            <Row label="Nom"          value={form.name} />
            <Row label="Type"         value={form.type} />
            {form.hostname   && <Row label="Hostname"      value={form.hostname} />}
            {form.ip_address && <Row label="Adresse IP"    value={form.ip_address} />}
            {form.environment && <Row label="Environnement" value={form.environment} />}
            {form.criticality && <Row label="Criticité"    value={form.criticality} />}
            <hr className="bs-divider" />
            <Row label="Transport"      value={form.transport} />
            <Row label="Ingestion"      value={form.ingestion_mode} />
            {form.host && <Row label="Gateway" value={form.host} />}
            <hr className="bs-divider" />
            <Row label="Silence"
              value={SILENCE_LABELS[form.silence_threshold_s] ?? form.silence_threshold_s + 's'} />
            {tagList.length > 0 && (
              <div className="bs-summary-row">
                <span className="bs-summary-label">Tags</span>
                <div className="bs-tag-list">
                  {tagList.map(t => <span key={t} className="bs-badge">{t}</span>)}
                </div>
              </div>
            )}
            {form.responsible && <Row label="Responsable" value={form.responsible} />}
            <Row label="Statut" value={form.active ? '✓ Active' : '✗ Désactivée'} />
            {form.description && <Row label="Description" value={form.description} />}
          </div>
        );
      }
    }
  }

  return (
    <div className="bs-modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bs-modal">
        {/* Header */}
        <div className="bs-modal-header">
          <h2 className="bs-modal-title">Nouvelle source</h2>
          <button className="bs-btn-icon" onClick={onClose} aria-label="Fermer">✕</button>
        </div>

        {/* Stepper */}
        <div className="bs-stepper">
          {STEPS.map((label, i) => (
            <div key={i} className={`bs-step ${i === step ? 'bs-step--active' : ''} ${i < step ? 'bs-step--done' : ''}`}>
              <div className="bs-step-dot">{i < step ? '✓' : i + 1}</div>
              <span className="bs-step-label">{label}</span>
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="bs-modal-body">
          {error && <div className="bs-alert bs-alert--error">{error}</div>}
          {renderStep()}
        </div>

        {/* Footer */}
        <div className="bs-modal-footer">
          {step > 0
            ? <button className="bs-btn bs-btn--secondary" onClick={prev}>Précédent</button>
            : <button className="bs-btn bs-btn--ghost" onClick={onClose}>Annuler</button>
          }
          {step < 3
            ? <button className="bs-btn bs-btn--primary" onClick={next}>Suivant</button>
            : <button className="bs-btn bs-btn--primary" onClick={submit} disabled={saving}>
                {saving ? 'Enregistrement…' : 'Enregistrer'}
              </button>
          }
        </div>
      </div>
    </div>
  );
}

const SILENCE_LABELS: Record<string, string> = {
  '300': '5 min', '600': '10 min', '900': '15 min', '1800': '30 min', '3600': '1 h',
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="bs-summary-row">
      <span className="bs-summary-label">{label}</span>
      <span className="bs-summary-value">{value}</span>
    </div>
  );
}

// ─── Badges helpers ───────────────────────────────────────────────────────────

const CRIT_CLASS: Record<string, string> = {
  faible: 'bs-badge--success', moyenne: 'bs-badge--warning',
  elevee: 'bs-badge--danger',  critique: 'bs-badge--critical',
};

const ENV_CLASS: Record<string, string> = {
  production: 'bs-badge--danger', staging: 'bs-badge--warning',
  test: 'bs-badge--info', developpement: 'bs-badge--neutral',
};

// ─── Page principale ──────────────────────────────────────────────────────────

export function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [search, setSearch] = useState('');

  const fetchSources = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get<unknown>('/sources', { params: { page: 1, size: 50 } });
      setSources(toList<Source>(data));
    } catch {
      setSources([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSources(); }, [fetchSources]);

  const filtered = sources.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    (s.config.hostname ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (s.config.ip_address ?? '').includes(search)
  );

  async function toggleSource(id: string, active: boolean) {
    try {
      await api.patch(`/sources/${id}`, { active: !active });
      fetchSources();
    } catch { /* silencieux */ }
  }

  return (
    <div className="bs-page">
      {/* Toolbar */}
      <div className="bs-toolbar">
        <div className="bs-toolbar-left">
          <h1 className="bs-page-title">Sources</h1>
          <span className="bs-badge bs-badge--neutral">{sources.length}</span>
        </div>
        <div className="bs-toolbar-right">
          <input
            className="bs-input bs-search"
            placeholder="Rechercher…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <button className="bs-btn bs-btn--primary" onClick={() => setShowModal(true)}>
            + Nouvelle source
          </button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="bs-loader">Chargement…</div>
      ) : filtered.length === 0 ? (
        <div className="bs-empty">
          <p>Aucune source{search ? ' correspondant à votre recherche' : ' configurée'}.</p>
          {!search && (
            <button className="bs-btn bs-btn--primary" onClick={() => setShowModal(true)}>
              Ajouter une source
            </button>
          )}
        </div>
      ) : (
        <div className="bs-table-wrapper">
          <table className="bs-table">
            <thead>
              <tr>
                <th>Nom</th>
                <th>Type</th>
                <th>Hostname / IP</th>
                <th>Env</th>
                <th>Criticité</th>
                <th>Transport</th>
                <th>Statut</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(s => (
                <tr key={s.id}>
                  <td>
                    <div className="bs-cell-primary">{s.name}</div>
                    {s.description && <div className="bs-cell-secondary">{s.description}</div>}
                  </td>
                  <td>
                    <span className="bs-badge bs-badge--type">{s.type}</span>
                  </td>
                  <td>
                    {s.config.hostname && <div className="bs-cell-primary">{s.config.hostname}</div>}
                    {s.config.ip_address && <div className="bs-cell-secondary bs-mono">{s.config.ip_address}</div>}
                    {!s.config.hostname && !s.config.ip_address && <span className="bs-muted">—</span>}
                  </td>
                  <td>
                    {s.config.environment
                      ? <span className={`bs-badge ${ENV_CLASS[s.config.environment] ?? ''}`}>{s.config.environment}</span>
                      : <span className="bs-muted">—</span>}
                  </td>
                  <td>
                    {s.config.criticality
                      ? <span className={`bs-badge ${CRIT_CLASS[s.config.criticality] ?? ''}`}>{s.config.criticality}</span>
                      : <span className="bs-muted">—</span>}
                  </td>
                  <td>
                    <span className="bs-badge bs-badge--neutral">{s.config.transport}</span>
                  </td>
                  <td>
                    <label className="bs-toggle bs-toggle--sm" title={s.active ? 'Désactiver' : 'Activer'}>
                      <input type="checkbox" checked={s.active}
                        onChange={() => toggleSource(s.id, s.active)} />
                      <span className="bs-toggle-slider" />
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <SourceModal
          onClose={() => setShowModal(false)}
          onCreated={fetchSources}
        />
      )}
    </div>
  );
}
