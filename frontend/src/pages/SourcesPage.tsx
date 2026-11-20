/**
 * Gestion des sources de données BaolSec.
 *
 * Le champ type correspond à config.sources.source_type :
 * linux | windows | firewall | http.
 * Il ne représente pas le transport d'ingestion (HTTPS ou Syslog).
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { sources } from '../api/resources';
import { coverage } from '../api/analyst';
import { useAuth } from '../hooks/useAuth';
import { useSearch } from '../components/AppShell';
import { Modal } from '../components/Modal';
import type {
  SourceCreate,
  SourceCredentialRotation,
} from '../types/api';

const SOURCE_TYPES = [
  { value: 'linux', label: 'Linux' },
  { value: 'windows', label: 'Windows' },
  { value: 'firewall', label: 'Pare-feu' },
  { value: 'http', label: 'Application / HTTP' },
] as const;

const INITIAL_FORM: SourceCreate = {
  name: '',
  type: 'linux',
  description: '',
  active: true,
  silence_threshold_s: 300,
  config: {
    transport: 'https',
    ingestion_mode: 'direct',
    host: '',
    criticality: 'moyenne',
    expected_min_events_per_h: null,
  },
};

function etat(state: string | undefined): { cls: string; label: string } {
  switch (state) {
    case 'ACTIVE':
      return { cls: 'up', label: '● Active' };
    case 'SILENCIEUSE':
      return { cls: 'down', label: '● Silencieuse' };
    case 'FLUX_INCOMPLET':
      return { cls: 'down', label: '● Flux incomplet' };
    case 'DESACTIVEE':
      return { cls: 'down', label: '● Désactivée' };
    default:
      return { cls: 'down', label: '● Inconnue' };
  }
}

function typeLabel(type: string): string {
  return SOURCE_TYPES.find((item) => item.value === type)?.label ?? type;
}

function erreurMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return 'Une erreur inattendue est survenue.';
}

function dateLabel(value: string | null): string {
  if (!value) return 'Non définie';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Date invalide'
    : date.toLocaleString('fr-FR');
}

export function SourcesPage() {
  const search = useSearch().toLowerCase();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const qc = useQueryClient();

  const srcQ = useQuery({
    queryKey: ['sources'],
    queryFn: () => sources.list({ limit: 200 }),
  });

  const covQ = useQuery({
    queryKey: ['coverage'],
    queryFn: () => coverage.list(),
  });

  const covById = new Map(
    (covQ.data ?? []).map((item) => [item.source_id, item.state]),
  );

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<SourceCreate>({ ...INITIAL_FORM });
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [generatedCredential, setGeneratedCredential] =
    useState<SourceCredentialRotation | null>(null);
  const [copyMessage, setCopyMessage] = useState('');

  const credentialsQ = useQuery({
    queryKey: ['source-credentials', selectedSourceId],
    queryFn: () => sources.credentials(selectedSourceId!),
    enabled: isAdmin && selectedSourceId !== null,
  });

  const createMut = useMutation({
    mutationFn: (body: SourceCreate) => sources.create(body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['sources'] });
      await qc.invalidateQueries({ queryKey: ['coverage'] });
      setOpen(false);
      setForm({ ...INITIAL_FORM });
    },
  });

  const disableMut = useMutation({
    mutationFn: (id: string) => sources.disable(id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['sources'] });
      await qc.invalidateQueries({ queryKey: ['coverage'] });
    },
  });

  const rotateMut = useMutation({
    mutationFn: (id: string) => sources.rotateCredential(id),
    onSuccess: async (result) => {
      setGeneratedCredential(result);
      setCopyMessage('');
      await qc.invalidateQueries({
        queryKey: ['source-credentials', selectedSourceId],
      });
    },
  });

  const rows = (srcQ.data ?? []).filter((source) =>
    !search ||
    `${source.name} ${source.type} ${source.description ?? ''}`
      .toLowerCase()
      .includes(search),
  );

  const selectedSource = rows.find(
    (source) => source.id === selectedSourceId,
  );

  function openCreateModal() {
    createMut.reset();
    setForm({ ...INITIAL_FORM });
    setOpen(true);
  }

  function closeCreateModal() {
    if (createMut.isPending) return;
    setOpen(false);
    createMut.reset();
  }

  function selectSource(id: string) {
    setGeneratedCredential(null);
    setCopyMessage('');
    setSelectedSourceId((current) => current === id ? null : id);
  }

  function closeCredentials() {
    if (rotateMut.isPending) return;
    setSelectedSourceId(null);
    setGeneratedCredential(null);
    setCopyMessage('');
    rotateMut.reset();
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const name = form.name.trim();
    const description = form.description?.trim() || '';
    const silenceThreshold = form.silence_threshold_s ?? 300;

    if (!name) return;
    if (!Number.isInteger(silenceThreshold) || silenceThreshold <= 0) {
      return;
    }

    createMut.mutate({
      ...form,
      name,
      description,
      active: true,
      silence_threshold_s: silenceThreshold,
      config: form.config ?? INITIAL_FORM.config,
    });
  }

  async function copyGeneratedToken() {
    if (!generatedCredential?.token) return;

    try {
      await navigator.clipboard.writeText(generatedCredential.token);
      setCopyMessage('Token copié dans le presse-papiers.');
    } catch {
      setCopyMessage(
        'Copie impossible. Sélectionne et copie le token manuellement.',
      );
    }
  }

  function rotateToken() {
    if (!selectedSource) return;

    const confirmed = confirm(
      `Générer un nouveau token pour « ${selectedSource.name} » ?\n\n` +
      'Cette opération révoquera les anciens tokens actifs de cette source. ' +
      'Les collecteurs utilisant ces anciens tokens ne pourront plus s’authentifier.',
    );

    if (confirmed) {
      setGeneratedCredential(null);
      setCopyMessage('');
      rotateMut.mutate(selectedSource.id);
    }
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Sources de données</h3>

        {isAdmin && (
          <button
            type="button"
            className="btn primary"
            style={{ padding: '8px 14px' }}
            onClick={openCreateModal}
          >
            + Nouvelle source
          </button>
        )}
      </div>

      <p className="empty-note" style={{ padding: '0 0 12px' }}>
        Sources supervisées par BaolSec. Leur état de couverture est calculé
        côté serveur à partir des événements reçus et normalisés.
      </p>

      {srcQ.isError && (
        <p className="auth-err">
          Impossible de charger les sources : {erreurMessage(srcQ.error)}
        </p>
      )}

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>SOURCE</th>
              <th>TYPE</th>
              <th>SEUIL DE SILENCE</th>
              <th>ÉTAT</th>
              {isAdmin && <th>ACTIONS</th>}
            </tr>
          </thead>

          <tbody>
            {rows.map((source) => {
              const status = etat(covById.get(source.id));
              const isSelected = selectedSourceId === source.id;

              return (
                <tr
                  key={source.id}
                  style={{ opacity: source.active ? 1 : 0.5 }}
                >
                  <td style={{ fontWeight: 600, color: '#dbe6f0' }}>
                    <div>{source.name}</div>
                    {source.description && (
                      <small className="empty-note">{source.description}</small>
                    )}
                  </td>

                  <td>{typeLabel(source.type)}</td>

                  <td>
                    {source.silence_threshold_s >= 60
                      ? `${Math.floor(source.silence_threshold_s / 60)} min`
                      : `${source.silence_threshold_s} s`}
                  </td>

                  <td>
                    <span className={status.cls}>{status.label}</span>
                  </td>

                  {isAdmin && (
                    <td>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          className="rowbtn"
                          onClick={() => selectSource(source.id)}
                        >
                          {isSelected ? 'Fermer' : 'Identifiants'}
                        </button>

                        {source.active && (
                          <button
                            type="button"
                            className="rowbtn danger"
                            disabled={disableMut.isPending}
                            onClick={() => {
                              if (
                                confirm(
                                  `Désactiver la source « ${source.name} » ?`,
                                )
                              ) {
                                disableMut.mutate(source.id);
                              }
                            }}
                          >
                            Désactiver
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              );
            })}

            {srcQ.isLoading && (
              <tr>
                <td colSpan={isAdmin ? 5 : 4} className="empty-note">
                  Chargement des sources…
                </td>
              </tr>
            )}

            {!srcQ.isLoading && !srcQ.isError && rows.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 5 : 4} className="empty-note">
                  Aucune source ne correspond à la recherche.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {disableMut.isError && (
        <p className="auth-err">
          Échec de la désactivation : {erreurMessage(disableMut.error)}
        </p>
      )}

      {selectedSource && isAdmin && (
        <section
          style={{
            marginTop: 20,
            padding: 16,
            border: '1px solid #334155',
            borderRadius: 8,
          }}
        >
          <div className="panel-head">
            <h3>Identifiants — {selectedSource.name}</h3>
            <button
              type="button"
              className="rowbtn"
              onClick={closeCredentials}
              disabled={rotateMut.isPending}
            >
              Fermer
            </button>
          </div>

          <p className="empty-note">
            Les secrets existants ne sont jamais consultables. Seul un nouveau
            token peut être affiché, au moment de sa génération.
          </p>

          {credentialsQ.isLoading && (
            <p className="empty-note">Chargement des identifiants…</p>
          )}

          {credentialsQ.isError && (
            <p className="auth-err">
              Impossible de charger les identifiants :{' '}
              {erreurMessage(credentialsQ.error)}
            </p>
          )}

          {credentialsQ.data && credentialsQ.data.length === 0 && (
            <p className="empty-note">
              Aucun identifiant enregistré pour cette source.
            </p>
          )}

          {credentialsQ.data && credentialsQ.data.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>TYPE</th>
                    <th>CRÉATION</th>
                    <th>EXPIRATION</th>
                    <th>STATUT</th>
                    <th>EMPREINTE CERTIFICAT</th>
                  </tr>
                </thead>
                <tbody>
                  {credentialsQ.data.map((credential) => (
                    <tr key={credential.id}>
                      <td>
                        {credential.credential_type === 'token'
                          ? 'Token HTTPS'
                          : 'Certificat client'}
                      </td>
                      <td>{dateLabel(credential.created_at)}</td>
                      <td>{dateLabel(credential.expires_at)}</td>
                      <td>
                        {credential.revoked_at ? (
                          <span className="down">Révoqué</span>
                        ) : credential.expires_at &&
                          new Date(credential.expires_at).getTime() <= Date.now() ? (
                          <span className="down">Expiré</span>
                        ) : (
                          <span className="up">Actif</span>
                        )}
                      </td>
                      <td>
                        {credential.cert_fingerprint ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ marginTop: 16 }}>
            <button
              type="button"
              className="btn primary"
              disabled={
                rotateMut.isPending ||
                !selectedSource.active ||
                selectedSource.config.transport !== 'https'
              }
              onClick={rotateToken}
            >
              {rotateMut.isPending
                ? 'Génération…'
                : 'Générer / renouveler le token HTTPS'}
            </button>

            {!selectedSource.active ? (
              <p className="empty-note">
                Cette source est désactivée. Réactive-la avant de générer un token.
              </p>
            ) : selectedSource.config.transport === 'syslog' ? (
              <p className="empty-note">
                Cette source utilise Syslog TLS. La gestion du certificat client
                doit être effectuée par le mécanisme dédié ; aucun token HTTPS
                ne sera généré ici.
              </p>
            ) : null}
          </div>

          {rotateMut.isError && (
            <p className="auth-err">
              Échec de la génération du token : {erreurMessage(rotateMut.error)}
            </p>
          )}

          {generatedCredential && (
            <div
              style={{
                marginTop: 16,
                padding: 14,
                border: '1px solid #b45309',
                borderRadius: 8,
                background: '#422006',
              }}
            >
              <strong style={{ color: '#fbbf24' }}>
                Nouveau token généré
              </strong>

              <p style={{ color: '#fde68a', fontSize: 13 }}>
                Copie et configure ce token sur le collecteur maintenant.
                Il ne sera plus récupérable après fermeture de ce panneau ou
                actualisation de la page.
              </p>

              <code
                style={{
                  display: 'block',
                  padding: 10,
                  borderRadius: 5,
                  background: '#1e293b',
                  color: '#f8fafc',
                  overflowWrap: 'anywhere',
                  userSelect: 'all',
                }}
              >
                {generatedCredential.token}
              </code>

              <button
                type="button"
                className="btn"
                style={{ marginTop: 10 }}
                onClick={copyGeneratedToken}
              >
                Copier le token
              </button>

              {copyMessage && (
                <p className="empty-note" role="status">
                  {copyMessage}
                </p>
              )}

              <p className="empty-note">
                Généré le : {dateLabel(generatedCredential.created_at)}
              </p>
            </div>
          )}
        </section>
      )}

      {open && (
        <Modal title="Nouvelle source" onClose={closeCreateModal}>
          <form onSubmit={submit}>
            <div className="field">
              <label className="lbl" htmlFor="source-name">
                Nom de la source *
              </label>
              <input
                id="source-name"
                className="input"
                style={{ width: '100%' }}
                value={form.name}
                minLength={1}
                maxLength={200}
                required
                autoFocus
                placeholder="Ex. : serveur-web-production"
                onChange={(event) =>
                  setForm({ ...form, name: event.target.value })
                }
              />
            </div>

            <div className="field">
              <label className="lbl" htmlFor="source-type">
                Type de source *
              </label>
              <select
                id="source-type"
                className="input"
                style={{ width: '100%' }}
                value={form.type}
                required
                onChange={(event) =>
                  setForm({ ...form, type: event.target.value })
                }
              >
                {SOURCE_TYPES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
              <small className="empty-note">
                Le type décrit la nature de la source, pas son protocole de
                transport.
              </small>
            </div>

            <div className="field">
              <label className="lbl" htmlFor="source-description">
                Description
              </label>
              <textarea
                id="source-description"
                className="input"
                style={{ width: '100%', minHeight: 76, resize: 'vertical' }}
                value={form.description ?? ''}
                maxLength={2000}
                placeholder="Rôle ou emplacement de cet équipement"
                onChange={(event) =>
                  setForm({ ...form, description: event.target.value })
                }
              />
            </div>

            <div className="field">
              <label className="lbl" htmlFor="source-transport">
                Transport d'ingestion *
              </label>
              <select
                id="source-transport"
                className="input"
                style={{ width: '100%' }}
                value={form.config?.transport ?? 'https'}
                onChange={(event) =>
                  setForm({
                    ...form,
                    config: {
                      ...form.config!,
                      transport: event.target.value as 'https' | 'syslog',
                    },
                  })
                }
              >
                <option value="https">HTTPS — token Bearer</option>
                <option value="syslog">Syslog TLS — certificat client</option>
              </select>
              <small className="empty-note">
                Le mode Syslog nécessite un certificat client. La génération
                de token HTTPS ne s'applique pas à ce transport.
              </small>
            </div>

            <div className="field">
              <label className="lbl" htmlFor="source-ingestion">
                Mode d'ingestion *
              </label>
              <select
                id="source-ingestion"
                className="input"
                style={{ width: '100%' }}
                value={form.config?.ingestion_mode ?? 'direct'}
                onChange={(event) =>
                  setForm({
                    ...form,
                    config: {
                      ...form.config!,
                      ingestion_mode: event.target.value as 'direct' | 'rejeu',
                    },
                  })
                }
              >
                <option value="direct">Direct</option>
                <option value="rejeu">Rejeu</option>
              </select>
            </div>

            <div className="field">
              <label className="lbl" htmlFor="source-host">
                Hôte de la source
              </label>
              <input
                id="source-host"
                className="input"
                style={{ width: '100%' }}
                value={form.config?.host ?? ''}
                maxLength={253}
                placeholder="Ex. : srv-web-01 ou 192.0.2.10"
                onChange={(event) =>
                  setForm({
                    ...form,
                    config: { ...form.config!, host: event.target.value },
                  })
                }
              />
            </div>

            <div className="field">
              <label className="lbl" htmlFor="source-criticality">
                Criticité
              </label>
              <select
                id="source-criticality"
                className="input"
                style={{ width: '100%' }}
                value={form.config?.criticality ?? 'moyenne'}
                onChange={(event) =>
                  setForm({
                    ...form,
                    config: {
                      ...form.config!,
                      criticality: event.target.value as
                        | 'faible'
                        | 'moyenne'
                        | 'elevee'
                        | 'critique',
                    },
                  })
                }
              >
                <option value="faible">Faible</option>
                <option value="moyenne">Moyenne</option>
                <option value="elevee">Élevée</option>
                <option value="critique">Critique</option>
              </select>
            </div>

            <div className="field">
              <label className="lbl" htmlFor="source-volume">
                Volume minimal attendu (événements/heure)
              </label>
              <input
                id="source-volume"
                className="input"
                style={{ width: '100%' }}
                type="number"
                min={0}
                step={1}
                value={form.config?.expected_min_events_per_h ?? ''}
                placeholder="Facultatif"
                onChange={(event) =>
                  setForm({
                    ...form,
                    config: {
                      ...form.config!,
                      expected_min_events_per_h:
                        event.target.value === ''
                          ? null
                          : Number(event.target.value),
                    },
                  })
                }
              />
              <small className="empty-note">
                Valeur indicative enregistrée pour la supervision. Elle ne
                constitue pas encore un seuil de détection automatique.
              </small>
            </div>

            <div className="field">
              <label className="lbl" htmlFor="source-silence">
                Seuil de silence (secondes) *
              </label>
              <input
                id="source-silence"
                className="input"
                style={{ width: '100%' }}
                type="number"
                min={1}
                step={1}
                required
                value={form.silence_threshold_s}
                onChange={(event) =>
                  setForm({
                    ...form,
                    silence_threshold_s: Number(event.target.value),
                  })
                }
              />
              <small className="empty-note">
                La source sera considérée comme silencieuse si aucun événement
                n'est reçu au-delà de ce délai.
              </small>
            </div>

            {createMut.isError && (
              <p className="auth-err">
                Échec de la création : {erreurMessage(createMut.error)}
              </p>
            )}

            <div className="actions">
              <button
                type="button"
                className="btn"
                onClick={closeCreateModal}
                disabled={createMut.isPending}
              >
                Annuler
              </button>

              <button
                type="submit"
                className="btn primary"
                disabled={
                  createMut.isPending ||
                  !form.name.trim() ||
                  !Number.isInteger(form.silence_threshold_s ?? 0) ||
                  (form.silence_threshold_s ?? 0) <= 0
                }
              >
                {createMut.isPending ? 'Création…' : 'Créer la source'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
