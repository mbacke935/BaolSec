/**
 * Règles de détection (EF-05, C12/C13) : définitions YAML au contrat rule/v1, versionnées.
 * Chaque modification de la définition crée une nouvelle version ; le code (AUTH-001…) est définitif.
 * Écriture réservée à l'Administrateur ; l'Analyste consulte.
 */
import { useDeferredValue, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { rules } from '../api/endpoints';
import { errorMessage } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import {
  Badge, Card, Drawer, Empty, ErrorNotice, Field, LoadingRows, Modal, Notice, PageHeader, Segmented,
  SeverityBadge, Tabs, useToast,
} from '../components/ui';
import { IconEdit, IconPlus, IconRule } from '../components/icons';
import { ago, dateTime, SEVERITIES, SEVERITY, SEVERITY_HELP } from '../lib/format';
import { CATEGORY, ruleInPlainWords } from '../lib/readable';

const categories = (c: string[]) => c.map((x) => CATEGORY[x] ?? x).join(', ');
import type { Rule, Severity } from '../types/api';

const TEMPLATE = `# Contrat rule/v1 — voir rules/README.md
id: AUTH-010
name: Nom court de la règle
description: >
  Ce que la règle détecte et pourquoi c'est suspect.
severity: moyenne          # faible | moyenne | elevee | critique
type: window               # simple (un événement suffit) | window (seuil sur une fenêtre)
category: [authentication]
match:
  event.category: authentication
  event.outcome: failure
group_by: [user.name, source.ip]
window: 10m                # 24h au maximum
threshold: 5
message: "{count} échecs pour {user.name} depuis {source.ip} en {window}"
requires:
  - source_type: linux
    fields: [user.name, source.ip]
`;

type View = 'all' | 'enabled' | 'disabled';

export function RulesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const [view, setView] = useState<View>('all');
  const [severity, setSeverity] = useState<'' | Severity>('');
  const [text, setText] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<Rule | 'new' | null>(null);
  const q = useQuery({ queryKey: ['rules'], queryFn: () => rules.list() });

  const all = q.data?.items ?? [];
  const needle = useDeferredValue(text).trim().toLowerCase();
  const rows = all
    .filter((r) => view === 'all' || (view === 'enabled' ? r.enabled : !r.enabled))
    .filter((r) => !severity || r.severity === severity)
    .filter((r) => !needle || `${r.code ?? ''} ${r.name} ${r.description ?? ''} ${r.category.join(' ')} ${categories(r.category)}`.toLowerCase().includes(needle))
    .sort((a, b) => (a.code ?? a.name).localeCompare(b.code ?? b.name));

  return (
    <>
      <PageHeader title="Règles de détection"
        subtitle={isAdmin
          ? 'Chaque règle est un fichier YAML au contrat rule/v1. Toute modification crée une nouvelle version ; les versions précédentes restent consultables.'
          : 'Règles appliquées par le moteur de détection (consultation). Ouvrez une règle pour lire sa définition et son historique.'}
        actions={isAdmin && <button className="btn primary" onClick={() => setEditing('new')}><IconPlus />Nouvelle règle</button>} />

      <Card>
        <div className="card-body">
          <div className="filters">
            <Segmented<View> value={view} onChange={setView} options={[
              { value: 'all', label: 'Toutes', count: all.length },
              { value: 'enabled', label: 'Actives', count: all.filter((r) => r.enabled).length },
              { value: 'disabled', label: 'Désactivées', count: all.filter((r) => !r.enabled).length },
            ]} />
            <Field label="Gravité">
              <select className="select" value={severity} onChange={(e) => setSeverity(e.target.value as Severity | '')}>
                <option value="">Toutes</option>
                {SEVERITIES.map((s) => <option key={s} value={s}>{SEVERITY[s].label}</option>)}
              </select>
            </Field>
            <Field label="Filtrer" className="grow"><input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Code, nom, catégorie…" /></Field>
          </div>
        </div>
        {q.error ? <div className="card-body"><ErrorNotice error={q.error} retry={() => q.refetch()} /></div> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Code</th><th>Règle</th><th>Type</th><th>Gravité</th><th className="num">Version</th><th>Modifiée</th><th>État</th></tr></thead>
              {q.isLoading ? <LoadingRows cols={7} /> : (
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className={`clickable ${r.enabled ? '' : 'dim'}`} onClick={() => setSelected(r.id)}>
                      <td className="mono nowrap">{r.code ?? '—'}</td>
                      <td className="title-cell" style={{ maxWidth: 440 }}><strong className="truncate">{r.name}</strong><span className="truncate">{categories(r.category)}</span></td>
                      <td className="small">{r.rule_type === 'window' ? 'Seuil sur fenêtre' : 'Simple'}</td>
                      <td><SeverityBadge value={r.severity} /></td>
                      <td className="num">v{r.version}</td>
                      <td className="faint nowrap" title={dateTime(r.updated_at)}>{ago(r.updated_at)}</td>
                      <td>{r.enabled ? <Badge tone="ok" dot>Active</Badge> : <Badge>Désactivée</Badge>}</td>
                    </tr>
                  ))}
                </tbody>
              )}
            </table>
            {!q.isLoading && rows.length === 0 && <Empty title="Aucune règle" icon={<IconRule />}>Aucune règle ne correspond à ces filtres.</Empty>}
          </div>
        )}
      </Card>

      {selected && <RuleDrawer id={selected} isAdmin={isAdmin} onClose={() => setSelected(null)}
        onEdit={(r) => { setSelected(null); setEditing(r); }} />}
      {editing && <RuleEditor rule={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function RuleDrawer({ id, isAdmin, onClose, onEdit }: { id: string; isAdmin: boolean; onClose: () => void; onEdit: (r: Rule) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<'def' | 'versions'>('def');
  const [openVersion, setOpenVersion] = useState<number | null>(null);
  const r = useQuery({ queryKey: ['rule', id], queryFn: () => rules.get(id) });
  const v = useQuery({ queryKey: ['rule', id, 'versions'], queryFn: () => rules.versions(id), enabled: tab === 'versions' });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => rules.setEnabled(id, enabled),
    onSuccess: (_d, enabled) => { toast.ok(enabled ? 'Règle activée.' : 'Règle désactivée.'); qc.invalidateQueries({ queryKey: ['rules'] }); qc.invalidateQueries({ queryKey: ['rule', id] }); },
    onError: (e) => toast.error(e),
  });
  const rule = r.data;

  return (
    <Drawer title={rule ? rule.name : 'Règle'} subtitle={rule ? <span className="mono">{rule.code} · version {rule.version}</span> : null} onClose={onClose}
      footer={isAdmin && rule ? (
        <div className="row" style={{ width: '100%', justifyContent: 'space-between' }}>
          <button className={`btn ${rule.enabled ? 'danger' : ''}`} disabled={toggle.isPending} onClick={() => toggle.mutate(!rule.enabled)}>{rule.enabled ? 'Désactiver' : 'Activer'}</button>
          <button className="btn primary" onClick={() => onEdit(rule)}><IconEdit />Modifier la définition</button>
        </div>
      ) : undefined}>
      {r.error ? <ErrorNotice error={r.error} /> : !rule ? <div className="skeleton" /> : (
        <div className="stack">
          <div className="row"><SeverityBadge value={rule.severity} />{rule.enabled ? <Badge tone="ok" dot>Active</Badge> : <Badge>Désactivée</Badge>}
            <span className="tag">{rule.rule_type === 'window' ? 'Seuil sur fenêtre' : 'Simple'}</span></div>
          {rule.description && <p className="muted">{rule.description}</p>}
          <PlainRule rule={rule} />
          <dl className="kv">
            <dt>Gravité</dt><dd>{SEVERITY_HELP[rule.severity]}</dd>
            <dt>Catégories</dt><dd>{categories(rule.category) || '—'}</dd>
            <dt>Créée</dt><dd>{dateTime(rule.created_at)}</dd>
            <dt>Dernière modification</dt><dd>{dateTime(rule.updated_at)}</dd>
          </dl>
          <Tabs value={tab} onChange={setTab} tabs={[{ value: 'def', label: 'Définition' }, { value: 'versions', label: 'Historique des versions' }]} />
          {tab === 'def' ? (
            <pre className="secret code-block">{rule.definition_yaml ?? JSON.stringify(rule.logic, null, 2)}</pre>
          ) : v.error ? <ErrorNotice error={v.error} /> : v.isLoading ? <div className="skeleton" /> : (
            <div className="stack" style={{ gap: 8 }}>
              {(v.data ?? []).map((ver) => (
                <div key={ver.version} className="card">
                  <button className="row between" style={{ width: '100%', padding: '12px 16px', background: 'none', border: 0, color: 'inherit', cursor: 'pointer', textAlign: 'left' }}
                    onClick={() => setOpenVersion(openVersion === ver.version ? null : ver.version)}>
                    <span><strong>Version {ver.version}</strong>{ver.version === rule.version && <Badge tone="accent">en vigueur</Badge>}</span>
                    <span className="small faint">{dateTime(ver.created_at)}{ver.created_by_name ? ` · ${ver.created_by_name}` : ''}</span>
                  </button>
                  {openVersion === ver.version && <pre className="secret code-block" style={{ margin: '0 16px 14px' }}>{ver.definition_yaml}</pre>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}

function RuleEditor({ rule, onClose }: { rule: Rule | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [yaml, setYaml] = useState(rule?.definition_yaml ?? TEMPLATE);
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => (rule ? rules.update(rule.id, { definition_yaml: yaml }) : rules.create(yaml, enabled)),
    onSuccess: (saved) => {
      toast.ok(rule ? (saved.version > rule.version ? `Version ${saved.version} enregistrée.` : 'Aucun changement : la définition est identique.') : `Règle ${saved.code ?? ''} créée.`);
      qc.invalidateQueries({ queryKey: ['rules'] });
      qc.invalidateQueries({ queryKey: ['rule', saved.id] });
      onClose();
    },
    onError: (err) => setError(errorMessage(err)),
  });

  return (
    <Modal wide title={rule ? `Modifier ${rule.code ?? rule.name}` : 'Nouvelle règle'}
      subtitle={rule ? `Version actuelle : ${rule.version}. L’enregistrement crée la version ${rule.version + 1} si la définition change. Le champ id ne peut pas changer.` : 'La définition est validée par le serveur (schéma rule/v1, expressions régulières, fenêtre de 24 h au plus).'}
      onClose={onClose}
      footer={<>
        {!rule && <label className="check" style={{ marginRight: 'auto' }}><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />Activer dès l’enregistrement</label>}
        <button className="btn ghost" onClick={onClose}>Annuler</button>
        <button className="btn primary" disabled={save.isPending || yaml.trim().length < 10} onClick={() => { setError(null); save.mutate(); }}>{save.isPending && <span className="spinner" />}Enregistrer</button>
      </>}>
      <div className="stack">
        {error && <Notice kind="error"><span style={{ whiteSpace: 'pre-wrap' }}>{error}</span></Notice>}
        <textarea className="textarea code" spellCheck={false} value={yaml} onChange={(e) => setYaml(e.target.value)} aria-label="Définition YAML" />
        <p className="small faint">Champs obligatoires : id (ex. AUTH-010), name, severity, type, match, message. Pour une règle à fenêtre : group_by, window, threshold.</p>
      </div>
    </Modal>
  );
}

/** La règle racontée en clair : quand elle se déclenche et sur quels événements. */
function PlainRule({ rule }: { rule: Rule }) {
  const p = ruleInPlainWords(rule);
  return (
    <section className="advice">
      <strong>En clair</strong>
      <p>{p.trigger}</p>
      {p.conditions.length > 0 && (<>
        <p className="small muted">Événements pris en compte :</p>
        <ul className="plain-list">{p.conditions.map((c) => <li key={c}>{c}</li>)}</ul>
      </>)}
    </section>
  );
}
