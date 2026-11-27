/**
 * Ajout d'une source, de la déclaration à la réception du premier événement (EF-01, EF-02, C7).
 *
 *   1. Identité        : nom, type, environnement, responsable…
 *   2. Raccordement    : transport (HTTPS par agent, ou Syslog TLS), hôte, seuil de silence
 *   3. Identifiant     : jeton généré (affiché une seule fois) ou empreinte du certificat client
 *   4. Agent et test   : configuration à appliquer sur la source, puis vérification de la réception
 *
 * La source est créée à la fin de l'étape 2 ; si l'assistant est fermé ensuite, elle reste déclarée
 * et l'identifiant peut être généré plus tard depuis « Identifiants ».
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { coverage, sources } from '../api/endpoints';
import { errorMessage } from '../api/client';
import { CopyButton, CoverageBadge, Field, Modal, Notice, useToast } from '../components/ui';
import { IconCheck, IconKey, IconRefresh } from '../components/icons';
import { ago, ENVIRONMENT, SEVERITIES, SEVERITY, SOURCE_TYPE } from '../lib/format';
import type { Environment, Severity, Source, SourceType, Transport } from '../types/api';

const STEPS = ['Identité', 'Raccordement', 'Identifiant', 'Agent et vérification'];

interface Draft {
  name: string; description: string; type: SourceType; environment: '' | Environment; criticality: '' | Severity;
  responsible: string; tags: string; transport: Transport; hostname: string; ip_address: string; silence_min: string; expected: string;
}
const EMPTY: Draft = {
  name: '', description: '', type: 'linux', environment: 'production', criticality: '', responsible: '', tags: '',
  transport: 'https', hostname: '', ip_address: '', silence_min: '15', expected: '',
};

export function SourceWizard({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [step, setStep] = useState(0);
  const [d, setD] = useState<Draft>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [fingerprint, setFingerprint] = useState('');
  const [fpSaved, setFpSaved] = useState(false);
  const set = <K extends keyof Draft>(k: K) => (e: { target: { value: string } }) => setD((x) => ({ ...x, [k]: e.target.value as Draft[K] }));

  const create = useMutation({
    mutationFn: () => sources.create({
      name: d.name.trim(), description: d.description.trim() || null, type: d.type, active: true,
      silence_threshold_s: Math.round(Number(d.silence_min) * 60),
      config: {
        transport: d.transport, hostname: d.hostname.trim() || null, host: d.hostname.trim() || null,
        ip_address: d.ip_address.trim() || null, environment: d.environment || null, criticality: d.criticality || null,
        responsible: d.responsible.trim() || null, tags: d.tags.split(',').map((t) => t.trim()).filter(Boolean),
        expected_min_events_per_h: d.expected.trim() ? Number(d.expected) : null,
      },
    }),
    onSuccess: (s) => { setSource(s); setStep(2); qc.invalidateQueries({ queryKey: ['sources'] }); qc.invalidateQueries({ queryKey: ['coverage'] }); },
    onError: (e) => setError(errorMessage(e)),
  });
  const genToken = useMutation({
    mutationFn: () => sources.newToken(source!.id),
    onSuccess: (t) => setToken(t.token),
    onError: (e) => setError(errorMessage(e)),
  });
  const saveFp = useMutation({
    mutationFn: () => sources.addCertificate(source!.id, fingerprint),
    onSuccess: () => { setFpSaved(true); setError(null); },
    onError: (e) => setError(errorMessage(e)),
  });

  const next = () => {
    setError(null);
    if (step === 0) {
      if (!d.name.trim()) return setError('Le nom est obligatoire.');
      if (!/^[A-Za-z0-9][A-Za-z0-9._-]{1,199}$/.test(d.name.trim())) return setError('Nom : lettres, chiffres, points, tirets et soulignés, sans espace (ex. srv-web-01).');
      return setStep(1);
    }
    if (step === 1) {
      const m = Number(d.silence_min);
      if (!Number.isFinite(m) || m < 1) return setError('Le seuil de silence doit être d’au moins 1 minute.');
      return create.mutate();
    }
    if (step === 2) {
      if (d.transport === 'https' && !token) return setError('Générez le jeton avant de continuer.');
      if (d.transport === 'syslog' && !fpSaved) return setError('Enregistrez l’empreinte du certificat avant de continuer.');
      return setStep(3);
    }
    toast.ok(`Source « ${source?.name} » ajoutée.`);
    onClose();
  };

  return (
    <Modal wide title="Ajouter une source" subtitle="Déclaration, identifiant d’ingestion et raccordement de l’agent, puis vérification de la réception."
      onClose={onClose}
      footer={<>
        {step === 1 && <button className="btn ghost" style={{ marginRight: 'auto' }} onClick={() => { setError(null); setStep(0); }}>Retour</button>}
        {step < 2 && <button className="btn ghost" onClick={onClose}>Annuler</button>}
        <button className="btn primary" onClick={next} disabled={create.isPending}>
          {create.isPending && <span className="spinner" />}
          {step === 1 ? 'Déclarer la source' : step === 3 ? 'Terminer' : 'Continuer'}
        </button>
      </>}>
      <ol className="wizard-steps" aria-label="Étapes">
        {STEPS.map((label, i) => (
          <li key={label} className={i < step ? 'done' : i === step ? 'on' : ''}>
            <span className="n">{i < step ? <IconCheck /> : i + 1}</span><span className="l">{label}</span>
          </li>
        ))}
      </ol>
      {error && <div className="mb-16"><Notice kind="error">{error}</Notice></div>}

      <div key={step} className="wizard-pane">
      {step === 0 && (
        <div className="form-grid">
          <Field label="Nom de la source" help="Identifiant unique et définitif, repris dans chaque événement.">
            <input className="input mono" value={d.name} onChange={set('name')} placeholder="srv-web-01" autoFocus maxLength={200} />
          </Field>
          <Field label="Type">
            <select className="select" value={d.type} onChange={set('type')}>
              {(Object.keys(SOURCE_TYPE) as SourceType[]).map((t) => <option key={t} value={t}>{SOURCE_TYPE[t]}</option>)}
            </select>
          </Field>
          <Field label="Description" className="full"><input className="input" value={d.description} onChange={set('description')} placeholder="Rôle de l’équipement, emplacement…" /></Field>
          <Field label="Environnement">
            <select className="select" value={d.environment} onChange={set('environment')}>
              <option value="">Non précisé</option>
              {(Object.keys(ENVIRONMENT) as Environment[]).map((e) => <option key={e} value={e}>{ENVIRONMENT[e]}</option>)}
            </select>
          </Field>
          <Field label="Criticité de l’actif">
            <select className="select" value={d.criticality} onChange={set('criticality')}>
              <option value="">Non précisée</option>
              {SEVERITIES.map((s) => <option key={s} value={s}>{SEVERITY[s].label}</option>)}
            </select>
          </Field>
          <Field label="Responsable"><input className="input" value={d.responsible} onChange={set('responsible')} placeholder="Équipe ou personne à contacter" /></Field>
          <Field label="Étiquettes" help="Séparées par des virgules."><input className="input" value={d.tags} onChange={set('tags')} placeholder="dmz, web" /></Field>
        </div>
      )}

      {step === 1 && (
        <div className="stack">
          <div className="choice-grid">
            <button type="button" className={`choice ${d.transport === 'https' ? 'on' : ''}`} onClick={() => setD((x) => ({ ...x, transport: 'https' }))}>
              <strong>HTTPS par agent ou collecteur</strong>
              <span>Fluent Bit sur la machine (Linux, Windows, serveur web) ou collecteur Syslog pour un pare-feu qui n’émet qu’en UDP. Authentification par jeton. Recommandé.</span>
            </button>
            <button type="button" className={`choice ${d.transport === 'syslog' ? 'on' : ''}`} onClick={() => setD((x) => ({ ...x, transport: 'syslog' }))}>
              <strong>Syslog sur TLS (port 6514)</strong>
              <span>Équipement capable d’émettre directement en Syslog TLS avec un certificat client. Authentification par l’empreinte du certificat.</span>
            </button>
          </div>
          <div className="form-grid">
            <Field label="Nom d’hôte"><input className="input mono" value={d.hostname} onChange={set('hostname')} placeholder="srv-web-01.interne" /></Field>
            <Field label="Adresse IP"><input className="input mono" value={d.ip_address} onChange={set('ip_address')} placeholder="10.0.4.23" /></Field>
            <Field label="Seuil de silence (minutes)" help="Sans événement au-delà, la source passe « silencieuse » et les règles qui en dépendent sont signalées.">
              <input className="input" type="number" min={1} value={d.silence_min} onChange={set('silence_min')} />
            </Field>
            <Field label="Volume minimal attendu (événements / heure)" help="Facultatif.">
              <input className="input" type="number" min={0} value={d.expected} onChange={set('expected')} />
            </Field>
          </div>
        </div>
      )}

      {step === 2 && source && (
        d.transport === 'https' ? (
          <div className="stack">
            <p className="muted">La source « <strong>{source.name}</strong> » est déclarée. Générez son jeton : l’agent le présentera à chaque envoi.</p>
            {!token ? (
              <div><button className="btn primary" onClick={() => genToken.mutate()} disabled={genToken.isPending}><IconKey />Générer le jeton</button></div>
            ) : (
              <Notice kind="warn">
                <div className="stack" style={{ gap: 10 }}>
                  <strong>Copiez ce jeton maintenant : il ne sera plus jamais affiché.</strong>
                  <div className="secret" style={{ wordBreak: 'break-all' }}>{token}</div>
                  <div className="row"><CopyButton text={token} label="Copier le jeton" /></div>
                  <span className="small">Seule son empreinte SHA-256 est conservée par BaolSec. En cas de perte, générez-en un nouveau.</span>
                </div>
              </Notice>
            )}
          </div>
        ) : (
          <div className="stack">
            <p className="muted">La source « <strong>{source.name}</strong> » est déclarée. Enregistrez l’empreinte SHA-256 du certificat client que l’équipement présentera.</p>
            <Field label="Empreinte SHA-256 du certificat client"
              help={<>Sur la machine qui détient le certificat : <span className="mono">openssl x509 -noout -fingerprint -sha256 -in client.crt</span>. BaolSec ne génère ni ne conserve de clé privée.</>}>
              <input className="input mono" value={fingerprint} onChange={(e) => { setFingerprint(e.target.value); setFpSaved(false); }} placeholder="AB:CD:EF:…" disabled={fpSaved} />
            </Field>
            {fpSaved ? <Notice kind="ok">Empreinte enregistrée.</Notice> : (
              <div><button className="btn primary" disabled={!fingerprint.trim() || saveFp.isPending} onClick={() => saveFp.mutate()}>Enregistrer l’empreinte</button></div>
            )}
            <Notice kind="info">Le certificat doit aussi être signé par l’autorité que la passerelle accepte pour le Syslog TLS (fichier <span className="mono">GATEWAY_SYSLOG_CLIENT_CA</span>), sinon la connexion TLS est refusée avant toute identification.</Notice>
          </div>
        )
      )}

      {step === 3 && source && <AgentGuide source={source} token={token} />}
      </div>
    </Modal>
  );
}

/** Instructions de raccordement de l'agent, puis contrôle de la réception (état de couverture). */
export function AgentGuide({ source, token }: { source: Source; token?: string | null }) {
  const [host, setHost] = useState(() => window.location.hostname || 'baolsec.example.local');
  const cov = useQuery({ queryKey: ['coverage'], queryFn: coverage.list, refetchInterval: 10_000 });
  const c = cov.data?.items.find((x) => x.source_id === source.id);
  const received = !!c?.last_received_at;
  const tok = token ?? '<jeton de la source>';
  const syslog = source.config.transport === 'syslog';

  const env = `BAOLSEC_GATEWAY_HOST=${host}
BAOLSEC_GATEWAY_PORT=8443
BAOLSEC_SOURCE_TOKEN=${tok}
BAOLSEC_CA_FILE=/etc/baolsec-agent/sources-ca.crt
BAOLSEC_STATE_DIR=/var/lib/baolsec-agent
BAOLSEC_BUFFER_LIMIT=1G`;

  const guide = (() => {
    if (syslog) return {
      title: 'Équipement en Syslog TLS',
      steps: [
        `Configurer l’envoi Syslog en TCP + TLS vers ${host}, port 6514 (format RFC 5424 ou RFC 3164).`,
        'Installer sur l’équipement le certificat client dont l’empreinte vient d’être enregistrée, et sa clé.',
        'Faire confiance à l’autorité qui a signé le certificat de la passerelle (sources-ca.crt).',
      ],
      code: null as string | null,
    };
    if (source.type === 'firewall') return {
      title: 'Pare-feu via le collecteur Syslog (pfSense…)',
      steps: [
        'Sur une machine du même réseau que le pare-feu : créer /etc/baolsec-agent/agent.env avec le contenu ci-dessous (droits 600) et y copier sources-ca.crt.',
        'Lancer le collecteur Fluent Bit (commande ci-dessous, dépôt BaolSec : agents/fluent-bit).',
        'Dans pfSense : Statut › Journaux système › Paramètres › Journalisation à distance, adresse du collecteur, port 514 ; ne cocher que les événements du pare-feu.',
      ],
      code: `docker run -d --name baolsec-syslog-collector -p 514:514/udp -p 514:514/tcp \\
  --env-file /etc/baolsec-agent/agent.env -e BAOLSEC_LISTEN_PORT=514 \\
  -v $PWD/agents/fluent-bit:/agents:ro -v /etc/baolsec-agent:/etc/baolsec-agent:ro \\
  -v baolsec-collector-state:/var/lib/baolsec-agent \\
  fluent/fluent-bit:5.1.5 /fluent-bit/bin/fluent-bit -c /agents/syslog-collector/fluent-bit.yaml`,
    };
    if (source.type === 'windows') return {
      title: 'Agent Fluent Bit pour Windows',
      steps: [
        'Installer Fluent Bit 5.1.5 pour Windows (paquet officiel) et l’enregistrer comme service.',
        'Copier common\\ et windows\\ (dépôt BaolSec : agents/fluent-bit) dans C:\\ProgramData\\BaolSec\\agent\\, avec sources-ca.crt.',
        'Définir les variables BAOLSEC_* ci-dessous comme variables système (chemins Windows).',
        'Commande du service : fluent-bit.exe -c C:\\ProgramData\\BaolSec\\agent\\windows\\fluent-bit.yaml',
        'Activer l’audit des ouvertures de session (succès et échecs : 4624, 4625) et de la création de processus (4688).',
      ],
      code: null,
    };
    const dir = source.type === 'http' ? 'webapp' : 'linux';
    return {
      title: source.type === 'http' ? 'Agent Fluent Bit sur le serveur de l’application' : 'Agent Fluent Bit pour Linux',
      steps: [
        'Installer Fluent Bit 5.1.5 depuis le dépôt officiel.',
        `Copier les fichiers de l’agent et l’autorité de la passerelle, puis créer agent.env (contenu ci-dessous).`,
        `Faire lancer Fluent Bit par systemd avec EnvironmentFile=/etc/baolsec-agent/agent.env et -c /etc/baolsec-agent/${dir}/fluent-bit.yaml.`,
        ...(source.type === 'http' ? ['Renseigner aussi BAOLSEC_WEBAPP_ACCESS_LOG et BAOLSEC_WEBAPP_APP_LOG (chemins des journaux).'] : []),
      ],
      code: `sudo mkdir -p /etc/baolsec-agent /var/lib/baolsec-agent
sudo cp -r agents/fluent-bit/{common,${dir}} /etc/baolsec-agent/
sudo cp sources-ca.crt /etc/baolsec-agent/
sudoedit /etc/baolsec-agent/agent.env        # contenu ci-dessous
sudo chmod 600 /etc/baolsec-agent/agent.env
sudo systemctl edit fluent-bit               # EnvironmentFile + ExecStart (voir agents/README.md)
sudo systemctl restart fluent-bit`,
    };
  })();

  return (
    <div className="stack">
      <div className={`verify ${received ? 'ok' : ''}`}>
        <div className="row between">
          <div className="row">
            {received ? <IconCheck style={{ color: 'var(--ok)' }} /> : <span className="radar" aria-hidden />}
            <div>
              <strong>{received ? 'Événements reçus' : 'En attente du premier événement…'}</strong>
              <div className="small muted">
                {received ? `Dernier événement ${ago(c!.last_received_at)} · ${c!.received_count} reçu(s), ${c!.normalized_count} normalisé(s).`
                  : 'Vérification automatique toutes les 10 secondes. La source passe « Active » dès que ses événements sont reçus et traités.'}
              </div>
            </div>
          </div>
          <div className="row">{c && <CoverageBadge value={c.state} />}<button className="btn sm" onClick={() => cov.refetch()}><IconRefresh />Vérifier</button></div>
        </div>
      </div>
      <Field label="Adresse de la passerelle vue depuis la source" help="Nom présent dans le certificat de la passerelle.">
        <input className="input mono" value={host} onChange={(e) => setHost(e.target.value)} style={{ maxWidth: 360 }} />
      </Field>
      <div>
        <div className="section-title"><h2>{guide.title}</h2></div>
        <ol className="guide-steps">{guide.steps.map((s) => <li key={s}>{s}</li>)}</ol>
      </div>
      {guide.code && (
        <div>
          <div className="section-title"><h2>Commandes</h2><CopyButton text={guide.code} /></div>
          <pre className="secret code-block">{guide.code}</pre>
        </div>
      )}
      {!syslog && (
        <div>
          <div className="section-title"><h2>agent.env</h2><CopyButton text={env} /></div>
          <pre className="secret code-block">{env}</pre>
          {!token && <p className="small faint mt-8">Le jeton n’est affiché qu’à sa génération : remplacez &lt;jeton de la source&gt; par celui que vous avez copié.</p>}
        </div>
      )}
    </div>
  );
}
