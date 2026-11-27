/**
 * File de rejet (C11, C5 GET /dlq) : messages refusés (illisibles, non conformes au contrat) ou
 * abandonnés après leurs tentatives. Lecture seule : un message est corrigé à la source puis renvoyé.
 */
import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { admin, sources } from '../api/endpoints';
import { Badge, Card, CopyButton, Drawer, Empty, ErrorNotice, Field, LoadingRows, PageHeader, Pager } from '../components/ui';
import { IconCheck } from '../components/icons';
import { ago, count, dateTime } from '../lib/format';
import { DLQ_REASON } from '../lib/readable';

const PAGE = 50;
const SERVICE: Record<string, string> = {
  'ingestion-gateway': 'Réception', 'normalization-worker': 'Normalisation', 'detection-worker': 'Détection',
  'incident-builder': 'Incidents', 'indexing-worker': 'Indexation (recherche)', 'coverage-worker': 'Couverture',
};
const REASON: Record<string, string> = Object.fromEntries(Object.entries(DLQ_REASON).map(([k, v]) => [k, v.label]));

export function DlqPage() {
  const [service, setService] = useState('');
  const [offset, setOffset] = useState(0);
  const [seq, setSeq] = useState<number | null>(null);
  const q = useQuery({ queryKey: ['dlq', service, offset], placeholderData: keepPreviousData, queryFn: () => admin.dlq({ limit: PAGE, offset, service: service || undefined }), refetchInterval: 30_000, retry: false });
  const items = q.data?.items ?? [];
  const src = useQuery({ queryKey: ['sources', 'all'], queryFn: () => sources.list(), staleTime: 60_000 });
  const names: Record<string, string> = Object.fromEntries((src.data?.items ?? []).map((x) => [x.id, x.name]));
  const subjects = Object.entries(q.data?.by_subject ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <>
      <PageHeader title="File de rejet"
        subtitle="Messages qu’un service n’a pas pu traiter. Ils sont conservés ici au lieu d’être perdus : identifiez la cause, corrigez la source ou l’analyseur, puis renvoyez les journaux." />

      {q.error ? <ErrorNotice error={q.error} retry={() => q.refetch()} /> : (
        <>
          {subjects.length > 0 && (
            <div className="row mb-16" style={{ gap: 8 }}>
              {subjects.map(([subject, n]) => <span key={subject} className="tag mono">{subject} · {count(n)}</span>)}
            </div>
          )}
          <Card title="Messages" hint={q.data ? `${count(q.data.total)} au total` : undefined}
            actions={
              <Field label="Service">
                <select className="select" value={service} onChange={(e) => { setService(e.target.value); setOffset(0); }}>
                  <option value="">Tous</option>
                  {Object.entries(SERVICE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>}
            footer={items.length > 0 ? <Pager offset={offset} limit={PAGE} count={items.length} onChange={setOffset} /> : undefined}>
            <div className={`table-wrap ${q.isPlaceholderData ? 'is-stale' : ''}`}>
              <table className="table">
                <thead><tr><th>Rejeté</th><th>Motif</th><th>Étape</th><th>Source</th><th>Contenu reçu</th></tr></thead>
                {q.isLoading ? <LoadingRows cols={5} /> : (
                  <tbody>
                    {items.map((m) => (
                      <tr key={m.seq} className="clickable" onClick={() => setSeq(m.seq)}>
                        <td className="nowrap" title={dateTime(m.failed_at)}>{m.failed_at ? ago(m.failed_at) : `#${m.seq}`}</td>
                        <td><Badge tone="warn">{m.reason_code ? REASON[m.reason_code] ?? m.reason_code : 'Non précisé'}</Badge></td>
                        <td>{SERVICE[m.service] ?? m.service}</td>
                        <td>{m.source_id ? names[m.source_id] ?? <span className="mono small faint">{m.source_id.slice(0, 8)}</span> : <span className="faint">—</span>}</td>
                        <td className="truncate small muted mono" style={{ maxWidth: 380 }}>{m.payload_preview ?? m.reason ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                )}
              </table>
              {!q.isLoading && items.length === 0 && <Empty title="File de rejet vide" icon={<IconCheck />}>Tous les messages reçus ont été traités.</Empty>}
            </div>
          </Card>
        </>
      )}

      {seq != null && <DlqDrawer seq={seq} names={names} onClose={() => setSeq(null)} />}
    </>
  );
}

function DlqDrawer({ seq, names, onClose }: { seq: number; names: Record<string, string>; onClose: () => void }) {
  const q = useQuery({ queryKey: ['dlq', 'entry', seq], queryFn: () => admin.dlqEntry(seq) });
  const m = q.data;
  const payload = m?.payload ?? '';
  return (
    <Drawer title={`Message #${seq}`} subtitle={m ? <span className="mono">{m.subject}</span> : null} onClose={onClose}>
      {q.error ? <ErrorNotice error={q.error} /> : !m ? <div className="skeleton" /> : (
        <div className="stack">
          {m.reason_code && DLQ_REASON[m.reason_code] && (
            <>
              <p>{DLQ_REASON[m.reason_code].explain}</p>
              <div className="advice"><strong>Que faire ?</strong>{DLQ_REASON[m.reason_code].todo}</div>
            </>
          )}
          <dl className="kv">
            <dt>Motif</dt><dd>{m.reason_code ? REASON[m.reason_code] ?? m.reason_code : '—'}</dd>
            <dt>Rejeté le</dt><dd>{dateTime(m.failed_at)}</dd>
            <dt>Étape</dt><dd>{SERVICE[m.service] ?? m.service}</dd>
            <dt>Source</dt><dd>{m.source_id ? names[m.source_id] ?? m.source_id : '—'}</dd>
            <dt>Tentatives</dt><dd>{m.attempts ?? '—'}</dd>
          </dl>
          {m.reason && <details className="tech"><summary>Message d’erreur du service</summary><pre className="secret mt-8" style={{ whiteSpace: 'pre-wrap' }}>{m.reason}</pre></details>}
          {payload && (
            <div>
              <div className="section-title"><h2>Contenu reçu, tel quel{m.payload_encoding === 'base64' ? ` (${m.payload_encoding})` : ''}</h2><CopyButton text={payload} /></div>
              <pre className="secret" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 460, overflow: 'auto', fontSize: 12 }}>{payload}</pre>
            </div>
          )}
          <details className="tech"><summary>Détails techniques</summary>
            <dl className="kv mt-8">
              <dt>Sujet</dt><dd className="mono small">{m.subject}</dd>
              <dt>Flux d’origine</dt><dd className="mono small">{m.original_stream ?? '—'}</dd>
              <dt>Code du motif</dt><dd className="mono small">{m.reason_code ?? '—'}</dd>
              <dt>Identifiant du message</dt><dd className="mono small">{m.message_id ?? '—'}</dd>
              <dt>N° dans la file</dt><dd className="mono small">{m.seq}</dd>
            </dl>
          </details>
          <p className="small faint">Les messages rejetés sont conservés 30 jours, puis supprimés automatiquement.</p>
        </div>
      )}
    </Drawer>
  );
}
