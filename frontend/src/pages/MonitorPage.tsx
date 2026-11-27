/**
 * Supervision de la plateforme (EF-12) : disponibilité de chaque service et des stockages,
 * volumes et retards des flux JetStream. L'historique et les alertes de supervision sont dans
 * Prometheus et Grafana (accès réservé à l'exploitation, ports liés à 127.0.0.1).
 */
import { useQuery } from '@tanstack/react-query';
import { system } from '../api/endpoints';
import { Badge, Card, Empty, ErrorNotice, LoadingRows, PageHeader, Stat } from '../components/ui';
import { IconRefresh } from '../components/icons';
import { ago, bytes, count, dateTime } from '../lib/format';
import { CONSUMER, SERVICE_NAME, STREAM } from '../lib/readable';
import type { HealthComponent } from '../types/api';

const STATUS = {
  up: { label: 'Opérationnel', tone: 'ok' as const },
  degraded: { label: 'Dégradé', tone: 'warn' as const },
  down: { label: 'Indisponible', tone: 'critical' as const },
};

const ROLE: Record<string, string> = {
  'baolsec-api': 'API et interface d’administration',
  'ingestion-gateway': 'Réception des journaux (HTTPS, Syslog TLS)',
  'normalization-worker': 'Normalisation au format ECS',
  'detection-worker': 'Évaluation des règles de détection',
  'incident-builder': 'Corrélation et cycle de vie des incidents',
  'coverage-worker': 'Suivi de la couverture des sources',
  'indexing-worker': 'Indexation dans OpenSearch',
  postgresql: 'Base de référence (C4)',
  opensearch: 'Recherche et conservation des événements',
  'nats-jetstream': 'Transport des messages entre services',
};

export function MonitorPage() {
  const q = useQuery({ queryKey: ['system', 'health'], queryFn: system.health, refetchInterval: 15_000 });
  const h = q.data;
  const comps = h?.components ?? [];
  const up = comps.filter((c) => c.status === 'up').length;
  const lag = (h?.streams ?? []).flatMap((s) => s.consumers ?? []).reduce((n, c) => n + c.pending + c.ack_pending, 0);
  const st = h ? STATUS[h.status] : null;

  return (
    <>
      <PageHeader title="Supervision"
        subtitle="État de la chaîne de traitement, vérifié à la demande par l’API auprès de chaque composant. Actualisation toutes les 15 secondes."
        actions={<button className="btn" onClick={() => q.refetch()} disabled={q.isFetching}><IconRefresh className={q.isFetching ? 'spin' : ''} />{q.isFetching ? 'Vérification…' : 'Vérifier maintenant'}</button>} />

      {q.error ? <ErrorNotice error={q.error} retry={() => q.refetch()} /> : (
        <>
          <div className="grid grid-4 mb-16">
            <Stat label="État global" value={st?.label ?? '…'} tone={st?.tone} sub={h ? `Vérifié ${ago(h.checked_at)}` : undefined} />
            <Stat label="Composants opérationnels" value={h ? `${up}/${comps.length}` : '…'} tone={h && up === comps.length ? 'ok' : 'warn'} />
            <Stat label="Messages non traités" value={h ? count(lag) : '…'} tone={lag > 1000 ? 'warn' : lag ? 'info' : 'ok'} sub="En attente ou en cours, tous consommateurs" />
            <Stat label="Flux disponibles" value={h ? `${h.streams.filter((s) => s.available).length}/${h.streams.length}` : '…'}
              tone={h && h.streams.every((s) => s.available) ? 'ok' : 'warn'} />
          </div>

          <div className="grid grid-2 mb-16">
            <ComponentTable title="Services" rows={comps.filter((c) => c.kind === 'service')} loading={q.isLoading} />
            <ComponentTable title="Stockage et transport" rows={comps.filter((c) => c.kind === 'donnees')} loading={q.isLoading} />
          </div>

          <Card title="Files de messages" hint="Entre chaque étape, les messages attendent dans une file : un nombre « en attente » qui grandit signale une étape trop lente ou arrêtée">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>File de messages</th><th className="num">Conservés</th><th className="num">Taille</th><th>Étape qui les traite</th>
                  <th className="num" title="Messages pas encore distribués à l’étape">En attente</th>
                  <th className="num" title="Messages distribués, en cours de traitement ou en attente de confirmation">En cours</th>
                  <th className="num" title="Messages renvoyés après un échec ou un délai dépassé">Renvoyés</th></tr></thead>
                {q.isLoading ? <LoadingRows cols={7} rows={4} /> : (
                  <tbody>
                    {(h?.streams ?? []).flatMap((s) => {
                      const consumers = s.consumers?.length ? s.consumers : [null];
                      return consumers.map((c, i) => (
                        <tr key={`${s.stream}-${c?.name ?? i}`}>
                          {i === 0 && <td rowSpan={consumers.length} className="mono" style={{ verticalAlign: 'top' }}>
                            <span style={{ fontFamily: 'var(--font)', fontWeight: 600 }}>{STREAM[s.stream] ?? s.stream}</span>{' '}
                            {!s.available && <Badge tone="critical">absente</Badge>}<div className="small faint">{s.stream}</div></td>}
                          {i === 0 && <td rowSpan={consumers.length} className="num" style={{ verticalAlign: 'top' }}>{count(s.messages)}</td>}
                          {i === 0 && <td rowSpan={consumers.length} className="num" style={{ verticalAlign: 'top' }}>{bytes(s.bytes)}</td>}
                          <td className="small">{c ? <>{CONSUMER[c.name] ?? c.name}<div className="faint mono" style={{ fontSize: 11 }}>{c.name}</div></> : <span className="faint">aucune</span>}</td>
                          <td className={`num ${c && c.pending > 1000 ? '' : 'faint'}`} style={c && c.pending > 1000 ? { color: 'var(--warn)' } : undefined}>{c ? count(c.pending) : '—'}</td>
                          <td className="num faint">{c ? count(c.ack_pending) : '—'}</td>
                          <td className="num faint">{c ? count(c.redelivered) : '—'}</td>
                        </tr>
                      ));
                    })}
                  </tbody>
                )}
              </table>
              {!q.isLoading && !h?.streams.length && <Empty title="Broker injoignable">Les flux ne peuvent pas être lus pour l’instant.</Empty>}
            </div>
          </Card>
          {h && <p className="small faint mt-16">Dernière vérification : {dateTime(h.checked_at)}. Historique détaillé et alertes de supervision : Grafana (tableau « BaolSec — Supervision de la plateforme ») et Prometheus.</p>}
        </>
      )}
    </>
  );
}

function ComponentTable({ title, rows, loading }: { title: string; rows: HealthComponent[]; loading: boolean }) {
  return (
    <Card title={title}>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Composant</th><th>État</th><th className="num">Latence</th></tr></thead>
          {loading ? <LoadingRows cols={3} rows={4} /> : (
            <tbody>
              {rows.map((c) => (
                <tr key={c.name}>
                  <td className="title-cell">
                    <strong className="row" style={{ display: 'flex', gap: 8 }}><span className={`pulse ${c.status === 'up' ? '' : c.status}`} />{SERVICE_NAME[c.name] ?? c.name}</strong>
                    <span>{ROLE[c.name] ?? detailText(c.detail)} <span className="mono" style={{ fontSize: 11 }}>· {c.name}</span></span>
                    {c.status !== 'up' && <span style={{ color: 'var(--warn)' }}>{detailText(c.detail)}</span>}
                  </td>
                  <td><Badge tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Badge></td>
                  <td className="num faint">{c.latency_ms != null ? `${c.latency_ms} ms` : '—'}</td>
                </tr>
              ))}
            </tbody>
          )}
        </table>
      </div>
    </Card>
  );
}

const WORD: Record<string, string> = {
  unreachable: 'injoignable', disconnected: 'déconnecté', down: 'arrêté', degraded: 'dégradé', error: 'en erreur',
  timeout: 'ne répond pas à temps', missing: 'absent', unknown: 'état inconnu',
};
/** Message de santé lisible : mots anglais traduits, nom d'exception Python retiré. */
const plain = (t: string) => t.replace(/\s*\((?:[A-Z]\w*(?:Error|Exception|Timeout))\)/g, '').replace(/\b[a-z]+\b/g, (w) => WORD[w] ?? w);

function detailText(d: unknown): string {
  return plain(rawDetail(d));
}

function rawDetail(d: unknown): string {
  if (d == null) return '';
  if (typeof d === 'string') return d;
  if (typeof d === 'object') {
    const o = d as Record<string, unknown>;
    if (typeof o.detail === 'string') return o.detail;
    // Signale les dépendances en défaut rapportées par le /health du service (ex. opensearch : unreachable).
    const bad = Object.entries(o).filter(([k, v]) => k !== 'status' && typeof v === 'string' && !['ok', 'connected', 'reachable', 'up'].includes(v));
    if (bad.length) return bad.map(([k, v]) => `${SERVICE_NAME[k] ?? k} : ${v}`).join(' · ');
    if (typeof o.status === 'string') return `statut ${o.status}`;
  }
  return JSON.stringify(d).slice(0, 120);
}
