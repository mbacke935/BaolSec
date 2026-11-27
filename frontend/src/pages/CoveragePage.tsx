/**
 * Couverture des sources (EF-09, C14) : état de chaque source, volumes reçus et traités,
 * règles de détection privées de données et historique des changements d'état.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { coverage } from '../api/endpoints';
import {
  Badge, Card, CoverageBadge, Empty, ErrorNotice, LoadingRows, PageHeader, Segmented, Stat,
} from '../components/ui';
import { IconRadar } from '../components/icons';
import { ago, CAUSE, count, COVERAGE, dateTime, duration, SOURCE_TYPE } from '../lib/format';
import { coverageReason } from '../lib/readable';
import type { Coverage, CoverageStateName } from '../types/api';

type View = 'all' | 'problems';
const ORDER: CoverageStateName[] = ['SILENCIEUSE', 'FLUX_INCOMPLET', 'INCONNUE', 'ACTIVE', 'DESACTIVEE'];

export function CoveragePage() {
  const [view, setView] = useState<View>('all');
  const q = useQuery({ queryKey: ['coverage'], queryFn: coverage.list, refetchInterval: 30_000 });
  const hist = useQuery({ queryKey: ['coverage', 'history'], queryFn: () => coverage.history(), refetchInterval: 60_000 });

  const items = [...(q.data?.items ?? [])].sort((a, b) => ORDER.indexOf(a.state) - ORDER.indexOf(b.state) || a.source_name.localeCompare(b.source_name));
  const n = (s: CoverageStateName) => items.filter((c) => c.state === s).length;
  const problems = items.filter((c) => c.state === 'SILENCIEUSE' || c.state === 'FLUX_INCOMPLET');
  const affected = new Set(items.flatMap((c) => c.affected_rules.map((r) => r.rule_id))).size;
  const shown = view === 'problems' ? problems : items;

  return (
    <>
      <PageHeader title="Couverture des sources"
        subtitle="Une source silencieuse ou au flux incomplet crée un angle mort : les règles qui en dépendent ne peuvent plus rien détecter. Cette page indique lesquelles." />

      <div className="grid grid-4 mb-16">
        <Stat label="Sources actives" value={q.isLoading ? '…' : n('ACTIVE')} tone={n('ACTIVE') ? 'ok' : undefined} sub={`sur ${items.length - n('DESACTIVEE')} source(s) en service`} />
        <Stat label="Silencieuses" value={q.isLoading ? '…' : n('SILENCIEUSE')} tone={n('SILENCIEUSE') ? 'critical' : 'ok'} sub="Aucun événement au-delà du seuil" />
        <Stat label="Flux incomplet" value={q.isLoading ? '…' : n('FLUX_INCOMPLET')} tone={n('FLUX_INCOMPLET') ? 'warn' : 'ok'} sub="Reçus mais non traités" />
        <Stat label="Règles privées de données" value={q.isLoading ? '…' : affected} tone={affected ? 'warn' : 'ok'} sub="Détection dégradée" />
      </div>

      {q.error ? <ErrorNotice error={q.error} retry={() => q.refetch()} /> : (
        <>
          <div className="section-title">
            <h2>Sources</h2>
            <Segmented<View> value={view} onChange={setView} options={[
              { value: 'all', label: 'Toutes', count: items.length }, { value: 'problems', label: 'À surveiller', count: problems.length },
            ]} />
          </div>
          {q.isLoading ? <div className="card card-body"><div className="skeleton" /></div> : shown.length === 0 ? (
            <Card><Empty title={view === 'problems' ? 'Aucune source à surveiller' : 'Aucune source déclarée'} icon={<IconRadar />}>
              {view === 'problems' ? 'Toutes les sources en service remontent leurs événements.' : 'Un administrateur déclare les sources dans Référentiel › Sources.'}
            </Empty></Card>
          ) : (
            <div className="grid grid-3 mb-16">{shown.map((c) => <SourceCard key={c.source_id} c={c} />)}</div>
          )}
        </>
      )}

      <Card title="Historique des changements d’état" hint="100 derniers changements">
        {hist.error ? <div className="card-body"><ErrorNotice error={hist.error} /></div> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Date</th><th>Source</th><th>Changement</th><th>Motif</th></tr></thead>
              {hist.isLoading ? <LoadingRows cols={4} rows={4} /> : (
                <tbody>
                  {(hist.data ?? []).map((h) => (
                    <tr key={h.id}>
                      <td className="mono small nowrap">{dateTime(h.changed_at)}</td>
                      <td>{h.source_name}</td>
                      <td className="nowrap">{h.from_state === h.to_state
                        ? <><span className="small faint">Premier état :</span> <CoverageBadge value={h.to_state} /></>
                        : <><CoverageBadge value={h.from_state} /> <span className="faint">→</span> <CoverageBadge value={h.to_state} /></>}</td>
                      <td className="small muted">{coverageReason(h.reason)}</td>
                    </tr>
                  ))}
                </tbody>
              )}
            </table>
            {!hist.isLoading && !hist.data?.length && <Empty title="Aucun changement enregistré" />}
          </div>
        )}
      </Card>
    </>
  );
}

function SourceCard({ c }: { c: Coverage }) {
  const ratio = c.received_count ? Math.min(100, Math.round((c.normalized_count / c.received_count) * 100)) : null;
  const tone = c.state === 'SILENCIEUSE' ? 'critical' : c.state === 'FLUX_INCOMPLET' ? 'warn' : '';
  return (
    <section className="card card-pad" style={tone ? { borderColor: `var(--${tone === 'critical' ? 'critical' : 'warn'})` } : undefined}>
      <div className="row between" style={{ alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <h3 className="truncate" style={{ fontSize: 15, fontWeight: 600 }}>{c.source_name}</h3>
          <div className="small faint">{c.source_type ? SOURCE_TYPE[c.source_type] : 'Type inconnu'}</div>
        </div>
        <CoverageBadge value={c.state} />
      </div>
      <p className="small muted mt-8">{COVERAGE[c.state].help}</p>
      <dl className="kv mt-16" style={{ fontSize: 13 }}>
        <dt>Dernier événement</dt><dd title={dateTime(c.last_received_at)}>{ago(c.last_received_at)}</dd>
        <dt>Dans cet état</dt><dd title={dateTime(c.state_since)}>{c.state_since ? ago(c.state_since).replace('il y a ', 'depuis ') : '—'}</dd>
        <dt>Seuil de silence</dt><dd>{duration(c.silence_threshold_s)}</dd>
        <dt>Reçus / traités</dt><dd>{count(c.received_count)} / {count(c.normalized_count)}</dd>
      </dl>
      {ratio != null && (
        <div className="mt-8">
          <div className={`bar ${ratio < 90 ? 'warn' : ''}`}><i style={{ width: `${ratio}%` }} /></div>
          <div className="small faint mt-8">{ratio} % des événements reçus ont été normalisés</div>
        </div>
      )}
      {c.affected_rules.length > 0 && (
        <div className="mt-16">
          <div className="small" style={{ fontWeight: 600, marginBottom: 6 }}>{c.affected_rules.length} règle(s) privée(s) de données</div>
          <div className="row" style={{ gap: 6 }}>
            {c.affected_rules.slice(0, 6).map((r) => <Badge key={r.rule_id} tone="warn" title={`Cause : ${CAUSE[r.cause] ?? r.cause} depuis ${dateTime(r.since)}`}>{r.name}</Badge>)}
            {c.affected_rules.length > 6 && <span className="small faint">+{c.affected_rules.length - 6}</span>}
          </div>
        </div>
      )}
    </section>
  );
}
