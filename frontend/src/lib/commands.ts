/** Traitement uniforme du résultat d'une commande (incident_command_result/v1, C5 §6). */
import type { CommandResult } from '../types/api';

const REFUSAL: Record<string, string> = {
  transition_interdite: 'Changement impossible depuis l’état actuel',
  cible_introuvable: 'Élément introuvable',
  donnees_invalides: 'Demande refusée',
};

/** Message d'erreur si la commande a été refusée par le service Incidents, sinon null. */
export function refusal(res: CommandResult): string | null {
  if (res.result === 'acceptee') return null;
  const prefix = res.error ? REFUSAL[res.error.code] ?? 'Commande refusée' : 'Commande refusée';
  return res.error?.message ? `${prefix} : ${res.error.message}` : prefix;
}
