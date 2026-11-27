/**
 * Libellés français des énumérations du schéma C4 et formats d'affichage.
 * Une seule source pour toute l'interface : plus de valeurs brutes (« elevee », « en_cours »)
 * ni d'ancien vocabulaire (« ELEVE », « RESOLU », « FAUX_POSITIF ») à l'écran.
 */
import type {
  AlertStatus, CoverageStateName, Environment, IncidentState, Severity, SourceType, UserRole,
} from '../types/api';

export type Tone = 'critical' | 'high' | 'medium' | 'low' | 'info' | 'ok' | 'warn' | 'neutral' | 'accent';

export const SEVERITIES: Severity[] = ['critique', 'elevee', 'moyenne', 'faible'];
export const SEVERITY: Record<Severity, { label: string; tone: Tone; rank: number }> = {
  critique: { label: 'Critique', tone: 'critical', rank: 4 },
  elevee: { label: 'Élevée', tone: 'high', rank: 3 },
  moyenne: { label: 'Moyenne', tone: 'medium', rank: 2 },
  faible: { label: 'Faible', tone: 'low', rank: 1 },
};

/** Ce que signifie chaque gravité pour la personne qui traite (affiché dans les détails). */
export const SEVERITY_HELP: Record<Severity, string> = {
  critique: 'Attaque probablement réussie ou en cours : à traiter immédiatement.',
  elevee: 'Comportement très suspect : à examiner rapidement.',
  moyenne: 'Activité anormale à vérifier dans la journée.',
  faible: 'Signal faible, utile surtout en complément d’autres alertes.',
};

export const INCIDENT_STATES: IncidentState[] = ['ouvert', 'en_cours', 'clos'];
export const INCIDENT_STATE: Record<IncidentState, { label: string; tone: Tone }> = {
  ouvert: { label: 'Ouvert', tone: 'critical' },
  en_cours: { label: 'En cours', tone: 'warn' },
  clos: { label: 'Clos', tone: 'neutral' },
};

export const ALERT_STATUSES: AlertStatus[] = ['nouvelle', 'en_cours', 'cloturee'];
export const ALERT_STATUS: Record<AlertStatus, { label: string; tone: Tone }> = {
  nouvelle: { label: 'Nouvelle', tone: 'accent' },
  en_cours: { label: 'En cours', tone: 'warn' },
  cloturee: { label: 'Clôturée', tone: 'neutral' },
};

export const COVERAGE: Record<CoverageStateName, { label: string; tone: Tone; help: string }> = {
  ACTIVE: { label: 'Active', tone: 'ok', help: 'Événements reçus et traités normalement.' },
  SILENCIEUSE: { label: 'Silencieuse', tone: 'critical', help: "Plus aucun événement reçu depuis plus que le seuil de silence : agent ou équipement à vérifier." },
  FLUX_INCOMPLET: { label: 'Flux incomplet', tone: 'warn', help: 'Des événements arrivent mais ne sont pas tous traités : vérifier la normalisation et la file de rejet.' },
  INCONNUE: { label: 'En attente', tone: 'neutral', help: "Aucun événement reçu depuis la déclaration de la source." },
  DESACTIVEE: { label: 'Désactivée', tone: 'neutral', help: 'Source désactivée par un administrateur.' },
};

export const SOURCE_TYPE: Record<SourceType, string> = {
  linux: 'Serveur Linux', windows: 'Windows', firewall: 'Pare-feu', http: 'Application web',
};
export const ENVIRONMENT: Record<Environment, string> = {
  production: 'Production', staging: 'Préproduction', test: 'Test', developpement: 'Développement',
};
export const ROLE: Record<UserRole, string> = { ADMIN: 'Administrateur', ANALYST: 'Analyste' };

export const CAUSE: Record<string, string> = {
  silence: 'source silencieuse', flux_incomplet: 'flux incomplet', desactivee: 'source désactivée',
};

export const TIMELINE: Record<string, { label: string; tone: Tone }> = {
  correlation: { label: 'Corrélation', tone: 'accent' },
  alert: { label: 'Alerte', tone: 'high' },
  event: { label: 'Événement', tone: 'info' },
  status_change: { label: 'Suivi', tone: 'warn' },
  comment: { label: 'Commentaire', tone: 'ok' },
  conflict: { label: 'Conflit', tone: 'critical' },
};

export const OUTCOME: Record<string, { label: string; tone: Tone }> = {
  succes: { label: 'Succès', tone: 'ok' }, refus: { label: 'Refus', tone: 'warn' }, echec: { label: 'Échec', tone: 'critical' },
  success: { label: 'Succès', tone: 'ok' }, failure: { label: 'Échec', tone: 'critical' }, unknown: { label: 'Inconnu', tone: 'neutral' },
};

const DATE_TIME = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'medium' });
const DATE_SHORT = new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

export function dateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : DATE_TIME.format(d);
}

export function dateShort(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : DATE_SHORT.format(d);
}

/** « il y a 3 min », « il y a 2 h », « il y a 4 j » ; « à l'instant » sous 45 s. */
export function ago(value: string | null | undefined, now: number = Date.now()): string {
  if (!value) return '—';
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return '—';
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 45) return "à l'instant";
  if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  return `il y a ${Math.round(s / 86400)} j`;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  if (seconds % 3600 === 0) return `${seconds / 3600} h`;
  if (seconds % 60 === 0) return `${seconds / 60} min`;
  return `${seconds} s`;
}

export function count(n: number | null | undefined): string {
  return n == null ? '—' : new Intl.NumberFormat('fr-FR').format(n);
}

export function bytes(n: number | null | undefined): string {
  if (n == null) return '—';
  const units = ['o', 'Ko', 'Mo', 'Go'];
  let v = n, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

export function shortId(id: string | null | undefined, size = 8): string {
  return id ? id.slice(0, size) : '—';
}

export function bySeverity<T extends { severity: Severity }>(a: T, b: T): number {
  return SEVERITY[b.severity].rank - SEVERITY[a.severity].rank;
}
