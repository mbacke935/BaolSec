/**
 * Helpers d'affichage partagés (badges de sévérité, états d'incident, formatage).
 * Les classes correspondent au design system de la maquette (.sev / .sev.med / .sev.low).
 */
import type { Severity, IncidentState } from '../types/api';

export function sevBadge(sev: Severity | string): { cls: string; label: string } {
  switch (sev) {
    case 'critique': return { cls: 'sev', label: 'Critique' };
    case 'elevee':   return { cls: 'sev med', label: 'Élevée' };
    case 'moyenne':  return { cls: 'sev med', label: 'Moyenne' };
    case 'faible':   return { cls: 'sev low', label: 'Faible' };
    case 'info':     return { cls: 'sev low', label: 'Info' };  // sévérité d'événement ECS
    default:         return { cls: 'sev low', label: String(sev) };
  }
}

export function incidentState(state: IncidentState | string): { cls: string; label: string } {
  switch (state) {
    case 'ouvert':   return { cls: 'state-pill warn', label: 'Ouvert' };
    case 'en_cours': return { cls: 'state-pill', label: 'En investigation' };
    case 'clos':     return { cls: 'state-pill mute', label: 'Clos' };
    default:         return { cls: 'state-pill mute', label: String(state) };
  }
}

/** Un incident « actif » = ouvert ou en cours d'investigation. */
export function isActiveIncident(state: string): boolean {
  return state === 'ouvert' || state === 'en_cours';
}

/** Formatage d'un entier à la française : 128 459. */
export function fmtInt(n: number): string {
  return new Intl.NumberFormat('fr-FR').format(n);
}

/** Formatage compact : 24,8 M / 1,2 k / 842. */
export function fmtCompact(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toLocaleString('fr-FR', { maximumFractionDigits: 1 }) + ' M';
  if (n >= 1_000) return (n / 1_000).toLocaleString('fr-FR', { maximumFractionDigits: 1 }) + ' k';
  return fmtInt(n);
}

/** Horodatage court fr-FR : 13/11/2026 01:32:14. */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'medium' });
}

/** « il y a 12 s / 3 min / 2 h / 4 j » à partir d'un ISO. */
export function sinceLabel(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return '—';
  const s = Math.max(0, Math.floor((Date.now() - d) / 1000));
  if (s < 60) return `il y a ${s} s`;
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return `il y a ${Math.floor(s / 86400)} j`;
}
