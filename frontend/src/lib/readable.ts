/**
 * Traductions « en clair » pour les personnes qui ne lisent pas le vocabulaire technique :
 * journal d'audit, événements ECS, file de rejet, corrélation, règles, supervision.
 * Chaque fonction garde une sortie de secours lisible pour une valeur inconnue.
 */
import type { AuditEntry, EcsDocument, Rule } from '../types/api';

// ── Événements (ECS) ─────────────────────────────────────────────────────────

export const CATEGORY: Record<string, string> = {
  authentication: 'Authentification', session: 'Session', iam: 'Comptes et droits', process: 'Processus',
  network: 'Réseau', web: 'Web', file: 'Fichier', configuration: 'Configuration', host: 'Système',
  intrusion_detection: 'Détection d’intrusion', api: 'API', database: 'Base de données', malware: 'Logiciel malveillant',
};
export const EVENT_TYPE: Record<string, string> = {
  start: 'début', end: 'fin', info: 'information', connection: 'connexion', access: 'accès', allowed: 'autorisé',
  denied: 'refusé', creation: 'création', deletion: 'suppression', change: 'modification', error: 'erreur',
};
export const ACTION: Record<string, string> = {
  ssh_login: 'Connexion SSH', sudo_command: 'Commande sudo', sudo_auth: 'Authentification sudo',
  pam_auth: 'Authentification système', logon: 'Ouverture de session Windows', logoff: 'Fermeture de session Windows',
  process_start: 'Lancement de programme', connection_allowed: 'Connexion autorisée par le pare-feu',
  connection_denied: 'Connexion bloquée par le pare-feu', http_request: 'Requête web', api_login: 'Connexion à l’application',
};
export const OUTCOME_TEXT: Record<string, string> = { success: 'réussi', failure: 'échoué', unknown: 'résultat inconnu' };

/** Libellé d'une action d'événement ; une action inconnue est rendue lisible (« cron_job » → « Cron job »). */
export function actionLabel(action?: string | null): string {
  if (!action) return '—';
  if (ACTION[action]) return ACTION[action];
  const t = action.replace(/[_-]+/g, ' ').trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function categoryLabel(cats?: string[] | null): string {
  return (cats ?? []).map((c) => CATEGORY[c] ?? c).join(', ') || '—';
}

/** Phrase de résumé d'un événement : le message normalisé s'il existe, sinon une phrase composée. */
export function eventSummary(e: EcsDocument): string {
  if (e.message) return e.message;
  const what = actionLabel(e.event?.action) ;
  const who = e.user?.name ? ` du compte ${e.user.name}` : '';
  const from = e.source?.ip ? ` depuis ${e.source.ip}` : '';
  const on = e.host?.name ? ` sur ${e.host.name}` : '';
  const res = e.event?.outcome && e.event.outcome !== 'unknown' ? ` : ${OUTCOME_TEXT[e.event.outcome]}` : '';
  return `${what}${who}${from}${on}${res}`;
}

// ── Champs ECS utilisés par les règles ───────────────────────────────────────

export const FIELD: Record<string, string> = {
  'user.name': 'utilisateur', 'source.ip': 'adresse IP source', 'source.port': 'port source',
  'destination.ip': 'adresse IP de destination', 'destination.port': 'port de destination', 'host.name': 'machine',
  'event.category': 'catégorie', 'event.outcome': 'résultat', 'event.action': 'action', 'event.code': 'code d’événement Windows',
  'event.type': 'type', 'process.command_line': 'ligne de commande', 'process.name': 'programme',
  'url.path': 'adresse web demandée', 'http.response.status_code': 'code de réponse web', 'http.request.method': 'méthode web',
  'network.transport': 'protocole', 'user_agent.original': 'navigateur ou outil',
};
const fieldLabel = (f: string) => FIELD[f] ?? f;

function valueLabel(field: string, v: unknown): string {
  if (field === 'event.category' && typeof v === 'string') return CATEGORY[v]?.toLowerCase() ?? v;
  if (field === 'event.outcome' && typeof v === 'string') return OUTCOME_TEXT[v] ?? v;
  if (field === 'event.action' && typeof v === 'string') return actionLabel(v).toLowerCase();
  if (Array.isArray(v)) return v.map((x) => valueLabel(field, x)).join(' ou ');
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>;
    if ('regex' in o) return `correspond au motif ${String(o.regex)}`;
    if ('in' in o) return valueLabel(field, o.in);
    if ('gte' in o) return `au moins ${o.gte}`;
    if ('contains' in o) return `contient « ${String(o.contains)} »`;
    return JSON.stringify(v);
  }
  return String(v);
}

function windowLabel(w: unknown): string {
  const m = /^(\d+)\s*([smhd])$/.exec(String(w ?? ''));
  if (!m) return String(w ?? '');
  return `${m[1]} ${{ s: 'secondes', m: 'minutes', h: 'heures', d: 'jours' }[m[2] as 's' | 'm' | 'h' | 'd']}`;
}

/** Description en clair du fonctionnement d'une règle à partir de sa logique (rule/v1). */
export function ruleInPlainWords(rule: Pick<Rule, 'rule_type' | 'logic'>): { trigger: string; conditions: string[] } {
  const l = rule.logic as Record<string, unknown>;
  const match = (l.match ?? {}) as Record<string, unknown>;
  const conditions = Object.entries(match).map(([f, v]) => `${fieldLabel(f)} : ${valueLabel(f, v)}`);
  const group = Array.isArray(l.group_by) ? (l.group_by as string[]).map(fieldLabel) : [];
  const by = group.join(' et par ');
  const trigger = rule.rule_type === 'window'
    ? `Se déclenche quand au moins ${l.threshold ?? '?'} événements correspondants surviennent en ${windowLabel(l.window)}${by ? `, comptés séparément par ${by}` : ''}.`
    : `Se déclenche dès qu’un seul événement correspond${by ? ` (une alerte par ${by})` : ''}.`;
  return { trigger, conditions };
}

// ── Corrélation des alertes en incidents ─────────────────────────────────────

export const CORRELATION_RULE: Record<string, string> = {
  R1: 'même utilisateur et même adresse IP source',
  R2: 'même utilisateur sur la même machine',
  R3: 'même adresse IP source et même machine',
  R4: 'même utilisateur, avec des activités qui s’enchaînent',
};
export const FAMILY: Record<string, string> = {
  authentication: 'authentification', process: 'lancement de programmes', host: 'système', network: 'réseau', web: 'web',
};
/** Ce que recouvre chaque famille d'activité (catégories ECS regroupées par le service Incidents). */
export const FAMILY_HELP: Record<string, string> = {
  authentication: 'connexions, sessions, comptes et droits',
  process: 'programmes lancés sur une machine',
  host: 'système, fichiers et configuration',
  network: 'flux réseau et détection d’intrusion',
  web: 'requêtes web et appels d’API',
};
/** « authentication > process » → « authentification, puis lancement de programmes ». */
export function chainInPlainWords(from: string, to: string): string {
  const f = FAMILY[from] ?? from;
  const t = FAMILY[to] ?? to;
  return from === to ? `${f}, à plusieurs reprises` : `${f}, puis ${t}`;
}
const ENTITY: Record<string, string> = {
  user: 'utilisateur', source_ip: 'adresse IP', host: 'machine', activity_chain: 'enchaînement',
};

/** Raison du rattachement d'une alerte à un incident, en clair. */
export function attachmentReason(detail: Record<string, unknown> | null | undefined): string {
  if (!detail) return '—';
  const rule = typeof detail.rule === 'string' ? detail.rule : null;
  const common = (detail.common_entities ?? {}) as Record<string, unknown>;
  if (rule) {
    const values = Object.entries(common).filter(([k]) => k !== 'activity_chain')
      .map(([k, v]) => `${ENTITY[k] ?? k} ${String(v)}`).join(', ');
    return `Rattachée : ${CORRELATION_RULE[rule] ?? rule}${values ? ` (${values})` : ''}`;
  }
  if (typeof detail.reason === 'string') {
    return detail.reason === 'aucun incident ouvert compatible' || detail.reason.startsWith('candidats écartés')
      ? 'À l’origine de l’incident : aucun incident en cours ne la concernait'
      : detail.reason;
  }
  return '—';
}

/** Résumé d'une entrée de chronologie d'incident, en clair. */
export function timelineSummary(summary: string, detail: Record<string, unknown> | null | undefined, alertTitle?: string): string {
  const created = /^Incident créé à partir de l'alerte (\S+)/.exec(summary);
  if (created) return `Incident ouvert par l’alerte « ${alertTitle ?? created[1]} »`;
  const attached = /^Alerte (\S+) rattachée par (R\d)/.exec(summary);
  if (attached) return `Alerte « ${alertTitle ?? attached[1]} » ajoutée à l’incident : ${CORRELATION_RULE[attached[2]] ?? attached[2]}`;
  const conflict = /^Conflit : alerte déjà rattachée/.exec(summary);
  if (conflict) return 'Alerte déjà rattachée à un autre incident : non ajoutée';
  void detail;
  return summary.replace(/\ben_cours\b/g, 'en cours').replace(/^Assigné à personne$/, 'Attribution retirée');
}

// ── File de rejet ────────────────────────────────────────────────────────────

export const DLQ_REASON: Record<string, { label: string; explain: string; todo: string }> = {
  parse_error: {
    label: 'Message illisible',
    explain: 'Le message reçu n’a pas pu être lu : ce n’est pas du texte ou du JSON valide, ou il est tronqué.',
    todo: 'Vérifier la configuration de l’agent de la source (format de sortie JSON, encodage UTF-8), puis renvoyer les journaux.',
  },
  validation_error: {
    label: 'Format non conforme',
    explain: 'Le message a été lu mais il ne respecte pas le format attendu entre les services (champ manquant ou de mauvais type).',
    todo: 'Le plus souvent, une source mal déclarée (type ou transport). Vérifier la fiche de la source ; si le problème persiste, le signaler à l’équipe technique.',
  },
  mapping_error: {
    label: 'Ligne non reconnue',
    explain: 'La ligne de journal ne correspond à aucun format connu pour ce type de source : elle ne peut pas être normalisée.',
    todo: 'Vérifier que la source envoie bien les journaux attendus (ex. pour un pare-feu pfSense, uniquement les événements du pare-feu) et que son type est le bon.',
  },
  index_rejected: {
    label: 'Refusé par la recherche',
    explain: 'OpenSearch a refusé d’enregistrer ce document (valeur incompatible avec l’index).',
    todo: 'Signaler à l’équipe technique : le document reste consultable ici en attendant.',
  },
  processing_error: {
    label: 'Échec après plusieurs essais',
    explain: 'Le service a essayé plusieurs fois de traiter ce message sans y parvenir (erreur interne ou dépendance indisponible).',
    todo: 'Consulter la page Supervision pour vérifier l’état des services, puis relancer le traitement (make dlq-replay).',
  },
};

export const SERVICE_NAME: Record<string, string> = {
  'ingestion-gateway': 'Passerelle de réception', 'normalization-worker': 'Normalisation', 'detection-worker': 'Détection',
  'incident-builder': 'Incidents', 'indexing-worker': 'Indexation (recherche)', 'coverage-worker': 'Couverture des sources',
  'baolsec-api': 'API et interface', postgresql: 'Base de données', opensearch: 'Moteur de recherche', 'nats-jetstream': 'Transport des messages',
};

// ── Supervision : flux et consommateurs JetStream ────────────────────────────

export const STREAM: Record<string, string> = {
  RAW_EVENTS: 'Événements reçus', NORMALIZED_EVENTS: 'Événements normalisés', ALERTS: 'Alertes',
  INCIDENTS: 'Incidents', DLQ: 'File de rejet',
};
export const CONSUMER: Record<string, string> = {
  normalization: 'Normalisation', detection: 'Détection', 'incident-builder': 'Incidents',
  'coverage-raw': 'Couverture (réception)', 'coverage-normalized': 'Couverture (traitement)',
  'indexing-events': 'Indexation des événements', 'indexing-alerts': 'Indexation des alertes', 'indexing-incidents': 'Indexation des incidents',
};

// ── Couverture : motifs de changement d'état ─────────────────────────────────

/** Motifs anciens (« aucun événement depuis 602s (seuil 600s) ») convertis en durées lisibles. */
export function coverageReason(reason: string): string {
  const human = (s: number) => (s < 60 ? `${s} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${Math.floor(s / 3600)} h${Math.round((s % 3600) / 60) ? ` ${Math.round((s % 3600) / 60)} min` : ''}`);
  return reason
    .replace(/(\d+)s\b/g, (_m, n) => human(Number(n)))
    .replace('source active et flux complet', 'événements reçus et traités normalement')
    .replace('source désactivée dans config', 'source désactivée par un administrateur')
    .replace(/\(seuil (\d[^)]*)\)/, '(seuil de silence : $1)');
}

// ── Journal d'audit ──────────────────────────────────────────────────────────

export type AuditDomain = 'connexion' | 'compte' | 'source' | 'regle' | 'incident' | 'parametre' | 'autre';
export const AUDIT_DOMAIN: Record<AuditDomain, string> = {
  connexion: 'Connexions', compte: 'Comptes', source: 'Sources', regle: 'Règles', incident: 'Incidents et alertes',
  parametre: 'Paramètres', autre: 'Autres',
};

const STATE_FR: Record<string, string> = {
  ouvert: 'ouvert', en_cours: 'en cours', clos: 'clos', nouvelle: 'nouvelle', cloturee: 'clôturée',
};
const ROLE_FR: Record<string, string> = { ADMIN: 'administrateur', ANALYST: 'analyste' };
const SETTING_FR: Record<string, string> = {
  'correlation.window_minutes': 'fenêtre de corrélation', 'correlation.max_incident_hours': 'durée maximale d’un incident',
  'correlation.generic_values': 'valeurs génériques ignorées', 'correlation.activity_chains': 'enchaînements d’activités',
};

export interface AuditView { domain: AuditDomain; sentence: string; outcome: string; reason?: string }

/** Phrase lisible pour une entrée du journal d'audit, construite à partir de l'action et des détails. */
const ROLE_NAME: Record<string, string> = { ADMIN: 'Administrateur', ANALYSTE: 'Analyste' };
/** Motifs enregistrés avant l'enrichissement du journal : retire le jargon de validation. */
function cleanReason(r: string): string {
  const role = /^Rôle requis\s*:\s*(\w+)/.exec(r);
  if (role) return `action réservée au rôle ${ROLE_NAME[role[1]] ?? role[1]}`;
  return r.replace(/^Value error,\s*/i, '').replace(/\s*\([a-z_]+(?:\.[a-z0-9_]+)*\)\s*$/, '');
}

export function describeAudit(e: AuditEntry, names: Record<string, string> = {}): AuditView {
  const d = (e.details ?? {}) as Record<string, any>;
  const who = e.actor_username || 'anonyme';
  const ch = (d.changes ?? {}) as Record<string, any>;
  const label = (d.label as string | undefined) ?? names[e.target_id];
  const q = (x?: string) => (x ? ` « ${x} »` : '');
  const reason = typeof d.reason === 'string' && d.reason ? cleanReason(d.reason) : undefined;
  const failed = e.outcome !== 'succes';
  // « désactiver la source » → « a désactivé la source » (effectuée) ou « a tenté de désactiver… »
  const tried = (s: string) => (failed ? `a tenté de ${s}` : `a ${pastTense(s)}`);

  if (e.action === 'auth.login') {
    return failed
      ? { domain: 'connexion', sentence: `Connexion refusée pour ${who}`, outcome: e.outcome, reason: reason ?? humanLoginReason(d) }
      : { domain: 'connexion', sentence: `${who} s’est connecté${d.role ? ` (${ROLE_FR[d.role] ?? d.role})` : ''}`, outcome: e.outcome };
  }
  const m = /^(POST|PUT|PATCH|DELETE) \/api\/v1\/([^/]+)(?:\/([^/]+))?(?:\/([^/]+))?(?:\/([^/]+))?(?:\/([^/]+))?$/.exec(e.action);
  if (!m) return { domain: 'autre', sentence: `${who} : ${e.action}`, outcome: e.outcome, reason };
  const [, method, res, , sub, , sub3] = m;
  const s = (txt: string, domain: AuditDomain): AuditView => ({ domain, sentence: `${who} ${tried(txt)}`, outcome: e.outcome, reason });

  switch (res) {
    case 'auth':
      return { domain: 'connexion', sentence: `${who} s’est déconnecté`, outcome: e.outcome, reason };
    case 'users':
      if (method === 'POST' && !sub && !m[3]) return s(`créer le compte${q(label ?? ch.username ?? ch.email)}${ch.role ? ` (${ROLE_FR[ch.role] ?? ch.role})` : ''}`, 'compte');
      if (sub === 'deactivate') return s(`désactiver le compte${q(label)}`, 'compte');
      if (sub === 'reactivate') return s(`réactiver le compte${q(label)}`, 'compte');
      return s(`modifier le compte${q(label)}${[ch.role && `rôle : ${ROLE_FR[ch.role] ?? ch.role}`, ch.password_changed && 'nouveau mot de passe', ch.email && `e-mail : ${ch.email}`].filter(Boolean).map((x) => ` — ${x}`).join('')}`, 'compte');
    case 'sources':
      if (method === 'POST' && !m[3]) return s(`déclarer la source${q(label ?? ch.name)}`, 'source');
      if (sub === 'credentials' && sub3 === 'revoke') return s(`révoquer un identifiant de la source${q(label)}`, 'source');
      if (sub === 'credentials' && method === 'DELETE') return s(`révoquer un identifiant de la source${q(label)}`, 'source');
      if (sub === 'credentials' && m[5] === 'cert') return s(`enregistrer un certificat pour la source${q(label)}`, 'source');
      if (sub === 'credentials') return s(`générer un nouveau jeton pour la source${q(label)}`, 'source');
      if (method === 'DELETE') return s(`désactiver la source${q(label)}`, 'source');
      return s(`modifier la source${q(label)}${ch.active === true ? ' — réactivée' : ''}`, 'source');
    case 'rules':
      if (method === 'POST' && !m[3]) return s(`créer la règle${q(label)}`, 'regle');
      if (sub === 'enable') return s(`activer la règle${q(label)}`, 'regle');
      if (sub === 'disable' || method === 'DELETE') return s(`désactiver la règle${q(label)}`, 'regle');
      return s(`modifier la règle${q(label)}${ch.definition_changed ? ' (nouvelle version)' : ''}`, 'regle');
    case 'settings': {
      const name = SETTING_FR[label ?? m[3] ?? ''] ?? label ?? m[3];
      const val = ch.value !== undefined ? ` à ${typeof ch.value === 'object' ? JSON.stringify(ch.value) : ch.value}` : '';
      return s(`régler le paramètre « ${name} »${val}`, 'parametre');
    }
    case 'incidents': {
      const t = q(label);
      if (sub === 'close') return s(`clore l’incident${t}${ch.reason ? ` (raison : « ${ch.reason} »)` : ''}`, 'incident');
      if (sub === 'reopen') return s(`rouvrir l’incident${t}`, 'incident');
      if (sub === 'comments' || sub === 'comment') return s(`commenter l’incident${t}`, 'incident');
      if (sub === 'assign') return s(ch.assignee_id ? `attribuer l’incident${t} à ${ch.assignee_name ?? 'un analyste'}` : `retirer l’attribution de l’incident${t}`, 'incident');
      if (sub === 'status') return s(`passer l’incident${t} à l’état « ${STATE_FR[ch.state ?? ch.status] ?? ch.state ?? ch.status ?? '?'} »`, 'incident');
      return s(`agir sur l’incident${t}`, 'incident');
    }
    case 'alerts': {
      const t = q(label);
      if (sub === 'assign') return s(ch.assignee_id ? `attribuer l’alerte${t} à ${ch.assignee_name ?? 'un analyste'}` : `retirer l’attribution de l’alerte${t}`, 'incident');
      if (sub === 'status') return s(`passer l’alerte${t} au statut « ${STATE_FR[ch.status] ?? ch.status ?? '?'} »`, 'incident');
      return s(`agir sur l’alerte${t}`, 'incident');
    }
    default:
      return { domain: 'autre', sentence: `${who} : ${e.action.replace('/api/v1', '')}`, outcome: e.outcome, reason };
  }
}

const PAST: Record<string, string> = {
  créer: 'créé', désactiver: 'désactivé', réactiver: 'réactivé', modifier: 'modifié', déclarer: 'déclaré',
  révoquer: 'révoqué', générer: 'généré', enregistrer: 'enregistré', activer: 'activé', régler: 'réglé',
  clore: 'clos', rouvrir: 'rouvert', commenter: 'commenté', attribuer: 'attribué', retirer: 'retiré',
  passer: 'passé', agir: 'agi',
};
function pastTense(phrase: string): string {
  const [verb, ...rest] = phrase.split(' ');
  return [PAST[verb] ?? verb, ...rest].join(' ');
}

function humanLoginReason(d: Record<string, any>): string | undefined {
  return typeof d.reason === 'string' ? d.reason : undefined;
}

/** Explication d'un code HTTP pour les détails techniques. */
export function httpStatusText(code?: number): string {
  if (!code) return '—';
  const t: Record<number, string> = {
    200: 'réussie', 201: 'créé', 204: 'réussie', 400: 'requête invalide', 401: 'non authentifiée', 403: 'droits insuffisants',
    404: 'élément introuvable', 409: 'conflit avec l’état actuel', 413: 'trop volumineuse', 422: 'données invalides',
    423: 'compte verrouillé', 429: 'trop de requêtes', 500: 'erreur du serveur', 502: 'service en aval en erreur', 503: 'service indisponible',
  };
  return `${code} — ${t[code] ?? (code >= 500 ? 'erreur du serveur' : 'autre')}`;
}
