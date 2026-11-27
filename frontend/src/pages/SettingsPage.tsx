/**
 * Paramètres de corrélation (C3 3.8, C5 /settings) lus par le service Incidents à chaque décision.
 * Les bornes sont contrôlées par le serveur ; chaque modification est tracée dans le journal d'audit.
 */
import { Fragment, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { admin } from '../api/endpoints';
import { Card, ErrorNotice, Field, Loading, PageHeader, useToast } from '../components/ui';
import { dateTime } from '../lib/format';
import { chainInPlainWords, FAMILY, FAMILY_HELP } from '../lib/readable';
import type { Setting } from '../types/api';

interface Known {
  key: string;
  title: string;
  help: string;
  kind: 'int' | 'list' | 'pairs';
  unit?: string;
  min?: number;
  max?: number;
  fallback: unknown;
}

const KNOWN: Known[] = [
  { key: 'correlation.window_minutes', title: 'Fenêtre de corrélation', unit: 'minutes', kind: 'int', min: 1, max: 1440, fallback: 30,
    help: 'Une alerte est rattachée à un incident ouvert si celui-ci a eu de l’activité dans cette fenêtre et partage des entités avec elle.' },
  { key: 'correlation.max_incident_hours', title: 'Durée maximale d’un incident', unit: 'heures', kind: 'int', min: 1, max: 720, fallback: 24,
    help: 'Au-delà, un incident n’accueille plus de nouvelles alertes : une nouvelle activité ouvre un nouvel incident.' },
  { key: 'correlation.generic_values', title: 'Valeurs génériques ignorées', kind: 'list', fallback: [],
    help: 'Valeurs trop communes pour justifier un regroupement (ex. : administrator, localhost, 127.0.0.1). Une par ligne.' },
  { key: 'correlation.activity_chains', title: 'Enchaînements d’activités', kind: 'pairs', fallback: [],
    help: 'Quand un même utilisateur enchaîne ces deux types d’activité, leurs alertes sont réunies dans un même incident, même sans machine ni adresse IP commune (règle R4). Un enchaînement par ligne, sous la forme « activité > activité suivante ».' },
];

export function SettingsPage() {
  const q = useQuery({ queryKey: ['settings'], queryFn: admin.settings });
  const byKey = new Map((q.data ?? []).map((s) => [s.key, s]));
  const others = (q.data ?? []).filter((s) => !KNOWN.some((k) => k.key === s.key));

  return (
    <>
      <PageHeader title="Paramètres"
        subtitle="Réglages de la corrélation des alertes en incidents. Ils s’appliquent aux alertes suivantes, sans redémarrage ; les incidents existants ne sont pas recalculés." />
      {q.error ? <ErrorNotice error={q.error} retry={() => q.refetch()} /> : q.isLoading ? <Loading /> : (
        <div className="stack">
          <div className="grid grid-2">
            {KNOWN.map((k) => <SettingCard key={k.key} def={k} setting={byKey.get(k.key)} />)}
          </div>
          {others.length > 0 && (
            <Card title="Autres paramètres" hint="Lecture seule">
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Clé</th><th>Valeur</th><th>Modifié le</th></tr></thead>
                  <tbody>{others.map((s) => (
                    <tr key={s.key}><td className="mono small">{s.key}</td><td className="mono small">{JSON.stringify(s.value)}</td><td className="faint small">{dateTime(s.updated_at)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </>
  );
}

function toText(def: Known, value: unknown): string {
  if (def.kind === 'int') return String(value ?? def.fallback);
  if (def.kind === 'list') return (Array.isArray(value) ? value : []).join('\n');
  return (Array.isArray(value) ? value : []).map((p) => (Array.isArray(p) ? p.join(' > ') : String(p))).join('\n');
}

function fromText(def: Known, text: string): unknown {
  if (def.kind === 'int') {
    const n = Number(text);
    if (!Number.isInteger(n)) throw new Error('Saisissez un nombre entier.');
    if (n < (def.min ?? 1) || n > (def.max ?? Infinity)) throw new Error(`Valeur attendue entre ${def.min} et ${def.max}.`);
    return n;
  }
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  if (def.kind === 'list') return lines;
  return lines.map((l) => {
    const parts = l.split('>').map((p) => p.trim());
    if (parts.length !== 2 || !parts[0] || !parts[1]) throw new Error(`Ligne invalide : « ${l} » (format attendu : activité > activité).`);
    const unknown = parts.find((p) => !FAMILY[p]);
    if (unknown) throw new Error(`« ${unknown} » n’est pas une famille d’activité reconnue (${Object.keys(FAMILY).join(', ')}).`);
    return parts;
  });
}

function SettingCard({ def, setting }: { def: Known; setting?: Setting }) {
  const qc = useQueryClient();
  const toast = useToast();
  const initial = toText(def, setting?.value ?? def.fallback);
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setText(initial), [initial]);

  const save = useMutation({
    mutationFn: (value: unknown) => admin.setSetting(def.key, value),
    onSuccess: () => { toast.ok(`« ${def.title} » enregistré.`); qc.invalidateQueries({ queryKey: ['settings'] }); },
    onError: (e) => toast.error(e),
  });
  const submit = () => {
    setError(null);
    try { save.mutate(fromText(def, text)); } catch (e) { setError((e as Error).message); }
  };
  const dirty = text !== initial;

  return (
    <Card title={def.title} hint={setting ? `Modifié le ${dateTime(setting.updated_at)}` : 'Valeur par défaut'}
      footer={<>
        <span className="small faint mono">{def.key}</span>
        <div className="row">
          {dirty && <button className="btn ghost sm" onClick={() => { setText(initial); setError(null); }}>Annuler</button>}
          <button className="btn primary sm" disabled={!dirty || save.isPending} onClick={submit}>Enregistrer</button>
        </div>
      </>}>
      <div className="card-body stack" style={{ gap: 10 }}>
        <p className="small muted">{def.help}</p>
        {def.kind === 'int' ? (
          <Field label={`Valeur (${def.unit})`} help={`Entre ${def.min} et ${def.max}.`} error={error}>
            <input className="input" type="number" min={def.min} max={def.max} value={text} onChange={(e) => setText(e.target.value)} style={{ maxWidth: 200 }} />
          </Field>
        ) : (
          <Field label={def.kind === 'list' ? 'Valeurs' : 'Enchaînements'} error={error}>
            <textarea className="textarea mono" rows={8} style={{ minHeight: 170 }} value={text} onChange={(e) => setText(e.target.value)}
              placeholder={def.kind === 'list' ? 'administrator\nlocalhost' : 'authentication > process\nweb > host'} />
          </Field>
        )}
        {def.kind === 'pairs' && <ChainPreview text={text} />}
      </div>
    </Card>
  );
}

/** Relecture en clair des enchaînements saisis, et rappel des familles d'activité reconnues. */
function ChainPreview({ text }: { text: string }) {
  const pairs = text.split('\n').map((l) => l.split('>').map((x) => x.trim())).filter((p) => p.length === 2 && p[0] && p[1]);
  return (
    <div className="stack" style={{ gap: 8 }}>
      {pairs.length > 0 && (
        <div className="advice">
          <strong>En clair</strong>
          <ul className="plain-list">{pairs.map(([a, b], i) => (
            <li key={i}>{FAMILY[a] && FAMILY[b] ? chainInPlainWords(a, b) : <span style={{ color: 'var(--warn)' }}>« {a} &gt; {b} » : famille inconnue</span>}</li>
          ))}</ul>
        </div>
      )}
      <details className="tech">
        <summary>Familles d’activité reconnues</summary>
        <dl className="kv small">{Object.entries(FAMILY_HELP).map(([k, v]) => (
          <Fragment key={k}><dt className="mono">{k}</dt><dd>{FAMILY[k]} : {v}</dd></Fragment>
        ))}</dl>
      </details>
    </div>
  );
}
