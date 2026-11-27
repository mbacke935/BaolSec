/**
 * Référentiel des sources (EF-01/EF-02, C5 /sources) : déclaration, configuration et identifiants
 * d'ingestion. Écriture réservée à l'Administrateur ; l'Analyste consulte.
 */
import { useDeferredValue, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { sources } from '../api/endpoints';
import { errorMessage } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import {
  Badge, Card, Confirm, CopyButton, Empty, ErrorNotice, Field, LoadingRows, Modal, Notice, PageHeader, Tabs, useToast,
} from '../components/ui';
import { IconEdit, IconKey, IconPlus, IconServer } from '../components/icons';
import { SourceWizard, AgentGuide } from './SourceWizard';
import { dateTime, duration, ENVIRONMENT, SEVERITIES, SEVERITY, SOURCE_TYPE } from '../lib/format';
import type { Environment, Severity, Source, SourceConfig, SourceType, TokenCredential, Transport } from '../types/api';

export function SourcesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const [text, setText] = useState('');
  const [editing, setEditing] = useState<Source | 'new' | null>(null);
  const [creds, setCreds] = useState<Source | null>(null);
  const q = useQuery({ queryKey: ['sources', 'all'], queryFn: () => sources.list() });

  const needle = useDeferredValue(text).trim().toLowerCase();
  const rows = (q.data?.items ?? [])
    .filter((s) => !needle || `${s.name} ${s.description ?? ''} ${s.config.hostname ?? ''} ${s.config.ip_address ?? ''} ${(s.config.tags ?? []).join(' ')} ${s.config.responsible ?? ''}`.toLowerCase().includes(needle))
    .sort((a, b) => Number(b.active) - Number(a.active) || a.name.localeCompare(b.name));

  return (
    <>
      <PageHeader title="Sources"
        subtitle={isAdmin
          ? 'Chaque équipement qui envoie des journaux est déclaré ici. « Ajouter une source » guide la déclaration, la création de l’identifiant d’ingestion, la configuration de l’agent et la vérification de la réception.'
          : 'Équipements et applications qui envoient leurs journaux à BaolSec (consultation).'}
        actions={isAdmin && <button className="btn primary" onClick={() => setEditing('new')}><IconPlus />Ajouter une source</button>} />

      <Card>
        <div className="card-body">
          <div className="filters">
            <Field label="Filtrer" className="grow">
              <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Nom, hôte, adresse IP, étiquette, responsable…" />
            </Field>
          </div>
        </div>
        {q.error ? <div className="card-body"><ErrorNotice error={q.error} retry={() => q.refetch()} /></div> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Source</th><th>Type</th><th>Transport</th><th>Hôte</th><th>Environnement</th><th>Seuil de silence</th><th>État</th>{isAdmin && <th />}</tr></thead>
              {q.isLoading ? <LoadingRows cols={isAdmin ? 8 : 7} /> : (
                <tbody>
                  {rows.map((s) => (
                    <tr key={s.id} className={s.active ? '' : 'dim'}>
                      <td className="title-cell" style={{ maxWidth: 320 }}>
                        <strong className="truncate">{s.name}</strong>
                        {(s.description || s.config.tags?.length) ? <span className="truncate">{s.description || s.config.tags.map((t) => `#${t}`).join(' ')}</span> : null}
                      </td>
                      <td className="small nowrap">{SOURCE_TYPE[s.type] ?? s.type}</td>
                      <td><span className="tag nowrap">{s.config.transport === 'syslog' ? 'Syslog TLS' : 'HTTPS'}</span></td>
                      <td className="mono small">{s.config.hostname ?? s.config.host ?? <span className="faint">—</span>}{s.config.ip_address && <div className="faint">{s.config.ip_address}</div>}</td>
                      <td className="small">{s.config.environment ? ENVIRONMENT[s.config.environment] : <span className="faint">—</span>}</td>
                      <td className="small">{duration(s.silence_threshold_s)}</td>
                      <td>{s.active ? <Badge tone="ok" dot>Active</Badge> : <Badge>Désactivée</Badge>}</td>
                      {isAdmin && (
                        <td className="actions">
                          <button className="btn sm" onClick={() => setCreds(s)}><IconKey />Identifiants</button>{' '}
                          <button className="btn sm ghost" onClick={() => setEditing(s)} aria-label={`Modifier ${s.name}`}><IconEdit /></button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              )}
            </table>
            {!q.isLoading && rows.length === 0 && (
              <Empty title={needle ? 'Aucune source ne correspond' : 'Aucune source déclarée'} icon={<IconServer />}>
                {isAdmin && !needle ? 'Commencez par « Ajouter une source » : l’assistant vous guide jusqu’à la réception du premier événement.' : null}
              </Empty>
            )}
          </div>
        )}
      </Card>

      {editing === 'new' && <SourceWizard onClose={() => setEditing(null)} />}
      {editing && editing !== 'new' && <SourceForm source={editing} onClose={() => setEditing(null)} />}
      {creds && <CredentialsModal source={creds} onClose={() => setCreds(null)} />}
    </>
  );
}

// ── Formulaire de source ─────────────────────────────────────────────────────

interface FormState {
  name: string; description: string; type: SourceType; transport: Transport; active: boolean; silence_min: string;
  hostname: string; ip_address: string; environment: '' | Environment; criticality: '' | Severity; responsible: string;
  tags: string; expected: string;
}

function initial(s: Source | null): FormState {
  const c: Partial<SourceConfig> = s?.config ?? {};
  return {
    name: s?.name ?? '', description: s?.description ?? '', type: (s?.type ?? 'linux') as SourceType,
    transport: (c.transport ?? 'https') as Transport, active: s?.active ?? true,
    silence_min: String(Math.round((s?.silence_threshold_s ?? 900) / 60)),
    hostname: c.hostname ?? c.host ?? '', ip_address: c.ip_address ?? '', environment: c.environment ?? '',
    criticality: c.criticality ?? '', responsible: c.responsible ?? '', tags: (c.tags ?? []).join(', '),
    expected: c.expected_min_events_per_h != null ? String(c.expected_min_events_per_h) : '',
  };
}

function SourceForm({ source, onClose }: { source: Source | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState<FormState>(() => initial(source));
  const [error, setError] = useState<string | null>(null);
  const [confirmOff, setConfirmOff] = useState(false);
  const set = <K extends keyof FormState>(k: K) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value as FormState[K] }));

  const save = useMutation({
    mutationFn: async () => {
      const minutes = Number(f.silence_min);
      if (!Number.isFinite(minutes) || minutes < 1) throw new Error('Le seuil de silence doit être d’au moins 1 minute.');
      const config: Partial<SourceConfig> = {
        transport: f.transport, hostname: f.hostname.trim() || null, host: f.hostname.trim() || null,
        ip_address: f.ip_address.trim() || null, environment: f.environment || null, criticality: f.criticality || null,
        responsible: f.responsible.trim() || null, tags: f.tags.split(',').map((t) => t.trim()).filter(Boolean),
        expected_min_events_per_h: f.expected.trim() ? Number(f.expected) : null,
      };
      const body = { description: f.description.trim() || null, type: f.type, active: f.active, silence_threshold_s: Math.round(minutes * 60), config };
      return source ? sources.update(source.id, body) : sources.create({ name: f.name.trim(), ...body });
    },
    onSuccess: () => {
      toast.ok(source ? 'Source mise à jour.' : 'Source déclarée. Générez maintenant son identifiant d’ingestion.');
      qc.invalidateQueries({ queryKey: ['sources'] });
      qc.invalidateQueries({ queryKey: ['coverage'] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error && !('isAxiosError' in err) ? err.message : errorMessage(err)),
  });

  const submit = (e: FormEvent) => { e.preventDefault(); setError(null); if (!source && !f.name.trim()) { setError('Le nom est obligatoire.'); return; } save.mutate(); };

  return (
    <Modal wide title={source ? `Modifier « ${source.name} »` : 'Ajouter une source'}
      subtitle={source ? 'Le nom d’une source est définitif (il identifie la source dans les événements).' : 'Une source correspond à un équipement ou une application qui envoie ses journaux.'}
      onClose={onClose}
      footer={<>
        {source && source.active && <button className="btn danger" style={{ marginRight: 'auto' }} onClick={() => setConfirmOff(true)}>Désactiver</button>}
        <button className="btn ghost" onClick={onClose}>Annuler</button>
        <button className="btn primary" form="source-form" type="submit" disabled={save.isPending}>{save.isPending && <span className="spinner" />}{source ? 'Enregistrer' : 'Déclarer'}</button>
      </>}>
      <form id="source-form" className="stack" onSubmit={submit}>
        {error && <Notice kind="error">{error}</Notice>}
        <div className="form-grid">
          <Field label="Nom" help="Ex. : srv-web-01 ou pare-feu-siege">
            <input className="input" value={f.name} onChange={set('name')} disabled={!!source} maxLength={200} autoFocus={!source} />
          </Field>
          <Field label="Type">
            <select className="select" value={f.type} onChange={set('type')}>
              {(Object.keys(SOURCE_TYPE) as SourceType[]).map((t) => <option key={t} value={t}>{SOURCE_TYPE[t]}</option>)}
            </select>
          </Field>
          <Field label="Description" className="full"><input className="input" value={f.description} onChange={set('description')} placeholder="Rôle de l’équipement, emplacement…" /></Field>
          <Field label="Transport" help={f.transport === 'https' ? 'Agent Fluent Bit en HTTPS, authentifié par jeton.' : 'Syslog sur TLS (port 6514), authentifié par certificat client.'}>
            <select className="select" value={f.transport} onChange={set('transport')}>
              <option value="https">HTTPS (jeton)</option><option value="syslog">Syslog TLS (certificat)</option>
            </select>
          </Field>
          <Field label="Seuil de silence (minutes)" help="Au-delà sans événement, la source passe « silencieuse ».">
            <input className="input" type="number" min={1} value={f.silence_min} onChange={set('silence_min')} />
          </Field>
          <Field label="Nom d’hôte"><input className="input mono" value={f.hostname} onChange={set('hostname')} placeholder="srv-web-01.interne" /></Field>
          <Field label="Adresse IP"><input className="input mono" value={f.ip_address} onChange={set('ip_address')} placeholder="10.0.4.23" /></Field>
          <Field label="Environnement">
            <select className="select" value={f.environment} onChange={set('environment')}>
              <option value="">Non précisé</option>
              {(Object.keys(ENVIRONMENT) as Environment[]).map((e) => <option key={e} value={e}>{ENVIRONMENT[e]}</option>)}
            </select>
          </Field>
          <Field label="Criticité de l’actif">
            <select className="select" value={f.criticality} onChange={set('criticality')}>
              <option value="">Non précisée</option>
              {SEVERITIES.map((s) => <option key={s} value={s}>{SEVERITY[s].label}</option>)}
            </select>
          </Field>
          <Field label="Responsable"><input className="input" value={f.responsible} onChange={set('responsible')} placeholder="Équipe ou personne à contacter" /></Field>
          <Field label="Volume minimal attendu (événements / heure)" help="Facultatif : sert à repérer un flux anormalement faible.">
            <input className="input" type="number" min={0} value={f.expected} onChange={set('expected')} />
          </Field>
          <Field label="Étiquettes" className="full" help="Séparées par des virgules."><input className="input" value={f.tags} onChange={set('tags')} placeholder="dmz, web, paiement" /></Field>
          {source && !source.active && (
            <label className="check full"><input type="checkbox" checked={f.active} onChange={(e) => setF((x) => ({ ...x, active: e.target.checked }))} />Réactiver la source</label>
          )}
        </div>
      </form>
      {confirmOff && source && (
        <Confirm title="Désactiver la source ?" danger confirmLabel="Désactiver" busy={save.isPending}
          onCancel={() => setConfirmOff(false)}
          onConfirm={async () => {
            try { await sources.disable(source.id); toast.ok('Source désactivée : ses événements sont désormais refusés.'); qc.invalidateQueries({ queryKey: ['sources'] }); qc.invalidateQueries({ queryKey: ['coverage'] }); onClose(); }
            catch (err) { toast.error(err); setConfirmOff(false); }
          }}>
          La passerelle refusera les événements de « {source.name} » et les règles qui en dépendent seront signalées comme privées de données. La source et son historique sont conservés ; vous pourrez la réactiver.
        </Confirm>
      )}
    </Modal>
  );
}

// ── Identifiants d'ingestion ─────────────────────────────────────────────────

function CredentialsModal({ source, onClose }: { source: Source; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [token, setToken] = useState<TokenCredential | null>(null);
  const [fp, setFp] = useState('');
  const [revoke, setRevoke] = useState<string | null>(null);
  const [tab, setTab] = useState<'creds' | 'agent'>('creds');
  const q = useQuery({ queryKey: ['credentials', source.id], queryFn: () => sources.credentials(source.id) });
  const refresh = () => qc.invalidateQueries({ queryKey: ['credentials', source.id] });
  const syslog = source.config.transport === 'syslog';
  const active = (q.data ?? []).filter((c) => !c.revoked_at);

  const gen = useMutation({ mutationFn: () => sources.newToken(source.id), onSuccess: (t) => { setToken(t); refresh(); }, onError: (e) => toast.error(e) });
  const cert = useMutation({ mutationFn: () => sources.addCertificate(source.id, fp), onSuccess: () => { setFp(''); toast.ok('Empreinte enregistrée.'); refresh(); }, onError: (e) => toast.error(e) });
  const rev = useMutation({ mutationFn: (cid: string) => sources.revoke(source.id, cid), onSuccess: () => { setRevoke(null); toast.ok('Identifiant révoqué.'); refresh(); }, onError: (e) => toast.error(e) });

  return (
    <Modal wide title={`Identifiants — ${source.name}`}
      subtitle={syslog ? 'Source Syslog TLS : identifiée par l’empreinte SHA-256 de son certificat client.' : 'Source HTTPS : authentifiée par un jeton porté dans l’en-tête Authorization.'}
      onClose={onClose} footer={<button className="btn" onClick={onClose}>Fermer</button>}>
      <Tabs value={tab} onChange={setTab} tabs={[{ value: 'creds', label: 'Identifiants' }, { value: 'agent', label: 'Raccordement de l’agent' }]} />
      {tab === 'agent' ? <AgentGuide source={source} token={token?.token} /> : (
      <div className="stack">
        {token && (
          <Notice kind="warn">
            <div className="stack" style={{ gap: 10 }}>
              <strong>Copiez ce jeton maintenant : il ne sera plus jamais affiché.</strong>
              <div className="secret" style={{ wordBreak: 'break-all' }}>{token.token}</div>
              <div className="row"><CopyButton text={token.token} label="Copier le jeton" /></div>
              <span className="small">Les jetons précédents restent valides : révoquez-les une fois le nouveau jeton en place sur l’agent, pour ne perdre aucun événement.</span>
            </div>
          </Notice>
        )}

        {syslog ? (
          <form className="stack" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (fp.trim()) cert.mutate(); }}>
            <Field label="Empreinte SHA-256 du certificat client"
              help={<>Calculée côté source avec <span className="mono">openssl x509 -noout -fingerprint -sha256 -in client.crt</span>. BaolSec ne génère ni ne conserve de clé privée.</>}>
              <input className="input mono" value={fp} onChange={(e) => setFp(e.target.value)} placeholder="AB:CD:…  (64 caractères hexadécimaux)" />
            </Field>
            <div className="row"><button className="btn primary" disabled={!fp.trim() || cert.isPending}><IconPlus />Enregistrer l’empreinte</button>
              <span className="small faint">Deux identifiants actifs au maximum par source (rotation sans coupure).</span></div>
          </form>
        ) : (
          <div className="row between">
            <span className="small muted">Deux identifiants actifs au maximum par source, pour permettre une rotation sans coupure.</span>
            <button className="btn primary" disabled={gen.isPending || active.length >= 2} onClick={() => gen.mutate()}><IconKey />Générer un jeton</button>
          </div>
        )}

        {q.error ? <ErrorNotice error={q.error} /> : (
          <div className="table-wrap card">
            <table className="table">
              <thead><tr><th>Type</th><th>Identifiant</th><th>Créé le</th><th>État</th><th /></tr></thead>
              <tbody>
                {(q.data ?? []).map((c) => (
                  <tr key={c.id} className={c.revoked_at ? 'dim' : ''}>
                    <td>{c.credential_type === 'token' ? 'Jeton' : 'Certificat'}</td>
                    <td className="mono small">{c.cert_fingerprint ? `${c.cert_fingerprint.slice(0, 16)}…${c.cert_fingerprint.slice(-8)}` : `•••• ${c.id.slice(0, 8)}`}</td>
                    <td className="small nowrap">{dateTime(c.created_at)}</td>
                    <td>{c.revoked_at ? <Badge>Révoqué le {dateTime(c.revoked_at)}</Badge> : <Badge tone="ok" dot>Actif</Badge>}</td>
                    <td className="actions">{!c.revoked_at && <button className="btn sm danger" onClick={() => setRevoke(c.id)}>Révoquer</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!q.isLoading && !q.data?.length && <Empty title="Aucun identifiant" icon={<IconKey />}>Sans identifiant actif, la passerelle refuse les événements de cette source.</Empty>}
          </div>
        )}
      </div>
      )}
      {revoke && (
        <Confirm title="Révoquer cet identifiant ?" danger confirmLabel="Révoquer" busy={rev.isPending} onCancel={() => setRevoke(null)} onConfirm={() => rev.mutate(revoke)}>
          Les envois authentifiés avec cet identifiant seront refusés immédiatement par la passerelle. Vérifiez que l’agent utilise déjà le nouvel identifiant.
        </Confirm>
      )}
    </Modal>
  );
}
