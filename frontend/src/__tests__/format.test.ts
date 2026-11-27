import { describe, expect, it } from 'vitest';
import { ago, bySeverity, duration, SEVERITY } from '../lib/format';
import { attachmentReason, chainInPlainWords, coverageReason, describeAudit, eventSummary, ruleInPlainWords } from '../lib/readable';
import type { AuditEntry } from '../types/api';
import { refusal } from '../lib/commands';

describe('libellés et formats', () => {
  it('traduit les énumérations du schéma C4', () => {
    expect(SEVERITY.elevee.label).toBe('Élevée');
    expect(SEVERITY.critique.tone).toBe('critical');
  });

  it('affiche les durées relatives et absolues', () => {
    const now = Date.parse('2026-11-27T10:00:00Z');
    expect(ago('2026-11-27T09:59:50Z', now)).toBe("à l'instant");
    expect(ago('2026-11-27T09:30:00Z', now)).toBe('il y a 30 min');
    expect(ago('2026-11-27T07:00:00Z', now)).toBe('il y a 3 h');
    expect(ago(null)).toBe('—');
    expect(duration(600)).toBe('10 min');
    expect(duration(7200)).toBe('2 h');
  });

  it('trie du plus grave au moins grave', () => {
    const rows = [{ severity: 'faible' as const }, { severity: 'critique' as const }, { severity: 'moyenne' as const }];
    expect([...rows].sort(bySeverity).map((r) => r.severity)).toEqual(['critique', 'moyenne', 'faible']);
  });

  it('rédige le journal d’audit en phrases', () => {
    const base: AuditEntry = { id: 1, occurred_at: '', actor_id: null, actor_username: 'admin', action: '', target_type: '', target_id: '', outcome: 'succes', details: null, client_ip: null };
    expect(describeAudit({ ...base, action: 'DELETE /api/v1/sources/b9e9f3e2-c5c3-4b99-972c-6c49d4d94043', target_type: 'sources', details: { label: 'web-01' } }).sentence)
      .toBe('admin a désactivé la source « web-01 »');
    const closed = describeAudit({ ...base, action: 'POST /api/v1/incidents/x/close', target_type: 'incidents', details: { label: 'Force brute — bob', changes: { reason: 'faux positif' } } });
    expect(closed.sentence).toBe('admin a clos l’incident « Force brute — bob » (raison : « faux positif »)');
    const refused = describeAudit({ ...base, actor_username: 'xc7', action: 'auth.login', outcome: 'refus', details: { reason: 'mot de passe incorrect (2/5)' } });
    expect(refused).toMatchObject({ domain: 'connexion', sentence: 'Connexion refusée pour xc7', reason: 'mot de passe incorrect (2/5)' });
    const denied = describeAudit({ ...base, actor_username: 'analyste', action: 'POST /api/v1/users', target_type: 'users', outcome: 'refus', details: { reason: 'Action réservée au rôle Administrateur', changes: { email: 'z@z.sn' } } });
    expect(denied.sentence).toBe('analyste a tenté de créer le compte « z@z.sn »');
  });

  it('explique corrélation, règles, événements et couverture en clair', () => {
    expect(attachmentReason({ rule: 'R1', common_entities: { user: 'bob', source_ip: '198.51.100.23' } }))
      .toBe('Rattachée : même utilisateur et même adresse IP source (utilisateur bob, adresse IP 198.51.100.23)');
    const r = ruleInPlainWords({ rule_type: 'window', logic: { match: { 'event.category': 'authentication', 'event.outcome': 'failure' }, group_by: ['user.name', 'source.ip'], window: '10m', threshold: 5 } });
    expect(r.trigger).toBe('Se déclenche quand au moins 5 événements correspondants surviennent en 10 minutes, comptés séparément par utilisateur et par adresse IP source.');
    expect(r.conditions).toEqual(['catégorie : authentification', 'résultat : échoué']);
    expect(eventSummary({ event: { action: 'connection_denied', outcome: 'failure' }, source: { ip: '10.0.0.1' } }))
      .toBe('Connexion bloquée par le pare-feu depuis 10.0.0.1 : échoué');
    expect(coverageReason('aucun événement depuis 602s (seuil 600s)')).toBe('aucun événement depuis 10 min (seuil de silence : 10 min)');
  });
});

describe('résultat des commandes (incident_command_result/v1)', () => {
  const base = { contract: 'incident_command_result/v1', command_id: 'c', completed_at: '', replayed: false };
  it('ne signale rien pour une commande acceptée', () => {
    expect(refusal({ ...base, result: 'acceptee' })).toBeNull();
  });
  it('explique un refus', () => {
    expect(refusal({ ...base, result: 'refusee', error: { code: 'transition_interdite', message: 'incident déjà clos' } }))
      .toBe('Changement impossible depuis l’état actuel : incident déjà clos');
  });

  it('raconte les enchaînements d’activités en clair', () => {
    expect(chainInPlainWords('authentication', 'process')).toBe('authentification, puis lancement de programmes');
    expect(chainInPlainWords('authentication', 'authentication')).toBe('authentification, à plusieurs reprises');
  });
});
