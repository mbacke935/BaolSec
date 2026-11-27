/** Composants d'interface partagés par toutes les pages. */
import {
  createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { useIsFetching, useIsMutating } from '@tanstack/react-query';
import { errorMessage } from '../api/client';
import { useCountUp, useIndicator } from '../lib/motion';
import {
  ALERT_STATUS, COVERAGE, INCIDENT_STATE, SEVERITY, type Tone,
} from '../lib/format';
import type { AlertStatus, CoverageStateName, IncidentState, Severity } from '../types/api';
import { IconAlert, IconCheck, IconCopy, IconInfo, IconInbox, IconX } from './icons';

// ── Mise en page ─────────────────────────────────────────────────────────────

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  );
}

export function Card({ title, hint, actions, children, footer, pad = false, className = '' }: {
  title?: ReactNode; hint?: ReactNode; actions?: ReactNode; children: ReactNode; footer?: ReactNode; pad?: boolean; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div className="row">{title && <h2>{title}</h2>}{hint && <span className="hint">{hint}</span>}</div>
          {actions}
        </div>
      )}
      <div className={pad ? 'card-body' : ''}>{children}</div>
      {footer && <div className="card-foot">{footer}</div>}
    </section>
  );
}

function CountUp({ value }: { value: number }) {
  return <>{new Intl.NumberFormat('fr-FR').format(useCountUp(value))}</>;
}

export function Stat({ label, value, sub, tone, href }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; href?: string }) {
  const cls = `card stat ${tone ? `tone-${tone}` : ''} ${href ? 'is-link' : ''}`;
  const shown = typeof value === 'number' ? <CountUp value={value} /> : value;
  const body = (<><div className="label">{label}</div><div className="value">{shown}</div>{sub && <div className="sub">{sub}</div>}</>);
  // Lien interne (pas de rechargement : les jetons sont en mémoire, un rechargement déconnecte).
  return href ? <Link className={cls} to={href}>{body}</Link> : <div className={cls}>{body}</div>;
}

// ── Badges métier ────────────────────────────────────────────────────────────

export function Badge({ tone = 'neutral', children, dot = false, title }: { tone?: Tone; children: ReactNode; dot?: boolean; title?: string }) {
  return <span className={`badge tone-${tone}`} title={title}>{dot && <span className="dot" />}{children}</span>;
}
export const SeverityBadge = ({ value }: { value: Severity }) =>
  <Badge tone={SEVERITY[value]?.tone ?? 'neutral'} dot>{SEVERITY[value]?.label ?? value}</Badge>;
export const IncidentStateBadge = ({ value }: { value: IncidentState }) =>
  <Badge tone={INCIDENT_STATE[value]?.tone ?? 'neutral'}>{INCIDENT_STATE[value]?.label ?? value}</Badge>;
export const AlertStatusBadge = ({ value }: { value: AlertStatus }) =>
  <Badge tone={ALERT_STATUS[value]?.tone ?? 'neutral'}>{ALERT_STATUS[value]?.label ?? value}</Badge>;
export const CoverageBadge = ({ value }: { value: CoverageStateName }) =>
  <Badge tone={COVERAGE[value]?.tone ?? 'neutral'} dot title={COVERAGE[value]?.help}>{COVERAGE[value]?.label ?? value}</Badge>;

// ── États ────────────────────────────────────────────────────────────────────

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty">
      <div className="ico">{icon ?? <IconInbox />}</div>
      <h3>{title}</h3>
      {children && <div className="small">{children}</div>}
    </div>
  );
}

export function Notice({ kind = 'info', children }: { kind?: 'info' | 'warn' | 'error' | 'ok'; children: ReactNode }) {
  const Ico = kind === 'ok' ? IconCheck : kind === 'info' ? IconInfo : IconAlert;
  return <div className={`notice ${kind}`} role={kind === 'error' ? 'alert' : 'status'}><Ico /><div>{children}</div></div>;
}

export function ErrorNotice({ error, retry }: { error: unknown; retry?: () => void }) {
  return (
    <Notice kind="error">
      {errorMessage(error)}
      {retry && <> {' '}<button className="btn link" onClick={retry}>Réessayer</button></>}
    </Notice>
  );
}

export function LoadingRows({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <tbody aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i}>{Array.from({ length: cols }).map((__, j) => <td key={j}><div className="skeleton" style={{ width: `${55 + ((i * 7 + j * 13) % 40)}%` }} /></td>)}</tr>
      ))}
    </tbody>
  );
}

export function Loading({ label = 'Chargement…' }: { label?: string }) {
  return <div className="empty"><div className="row" style={{ justifyContent: 'center' }}><span className="spinner" /> {label}</div></div>;
}

// ── Formulaires ──────────────────────────────────────────────────────────────

export function Field({ label, help, error, children, className = '' }: { label: string; help?: ReactNode; error?: string | null; children: ReactNode; className?: string }) {
  return (
    <label className={`field ${className}`}>
      <span>{label}</span>
      {children}
      {error ? <span className="err">{error}</span> : help ? <span className="help">{help}</span> : null}
    </label>
  );
}

export function Segmented<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string; count?: number }[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const box = useIndicator(ref, 'button.on', [value, options.map((o) => `${o.label}${o.count ?? ''}`).join()]);
  return (
    <div className="segmented" role="tablist" ref={ref}>
      {box && <span className="seg-ind" aria-hidden style={{ transform: `translate(${box.left}px, ${box.top}px)`, width: box.width, height: box.height }} />}
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" aria-selected={value === o.value}
          className={value === o.value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.label}{o.count != null && <span className="n">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, tabs }: { value: T; onChange: (v: T) => void; tabs: { value: T; label: ReactNode }[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const box = useIndicator(ref, 'button.on', [value]);
  return (
    <div className="tabs" role="tablist" ref={ref}>
      {box && <span className="tab-ind" aria-hidden style={{ transform: `translateX(${box.left}px)`, width: box.width }} />}
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value} className={value === t.value ? 'on' : ''} onClick={() => onChange(t.value)}>{t.label}</button>
      ))}
    </div>
  );
}

export function Pager({ offset, limit, total, count, onChange }: { offset: number; limit: number; total?: number; count: number; onChange: (offset: number) => void }) {
  const from = count ? offset + 1 : 0;
  const to = offset + count;
  return (
    <div className="row between" style={{ width: '100%' }}>
      <span className="small faint">{count ? `${from}–${to}${total != null ? ` sur ${total}` : ''}` : 'Aucun résultat'}</span>
      <div className="row">
        <button className="btn sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Précédent</button>
        <button className="btn sm" disabled={total != null ? to >= total : count < limit} onClick={() => onChange(offset + limit)}>Suivant</button>
      </div>
    </div>
  );
}

export function CopyButton({ text, label = 'Copier' }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className="btn sm" onClick={async () => {
      try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1800); } catch { /* sélection manuelle */ }
    }}>{done ? <IconCheck /> : <IconCopy />}{done ? 'Copié' : label}</button>
  );
}

// ── Fenêtres ─────────────────────────────────────────────────────────────────

function useEscape(onClose: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
}

export function Modal({ title, subtitle, onClose, children, footer, wide = false }: {
  title: ReactNode; subtitle?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  useEscape(onClose);
  // Rendu dans <body> : les animations d'entrée de page (transform) piègeraient sinon le
  // positionnement fixe de la fenêtre dans le bloc animé.
  return createPortal(
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined}>
        <div className="modal-head">
          <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button className="btn ghost icon" onClick={onClose} aria-label="Fermer"><IconX /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

export function Drawer({ title, subtitle, onClose, children, footer }: { title: ReactNode; subtitle?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEscape(onClose);
  return createPortal(
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <div className="modal-head">
          <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button className="btn ghost icon" onClick={onClose} aria-label="Fermer"><IconX /></button>
        </div>
        <div className="modal-body" style={{ flex: 1 }}>{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </aside>
    </>,
    document.body,
  );
}

export function Confirm({ title, children, confirmLabel = 'Confirmer', danger = false, busy = false, onConfirm, onCancel }: {
  title: string; children: ReactNode; confirmLabel?: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Modal title={title} onClose={onCancel} footer={<>
      <button className="btn ghost" onClick={onCancel}>Annuler</button>
      <button className={`btn ${danger ? 'danger' : 'primary'}`} disabled={busy} onClick={onConfirm}>{busy && <span className="spinner" />}{confirmLabel}</button>
    </>}>
      <div className="muted">{children}</div>
    </Modal>
  );
}

// ── Notifications ────────────────────────────────────────────────────────────

interface Toast { id: number; kind: 'ok' | 'error' | 'info'; text: string; leaving?: boolean }
const ToastCtx = createContext<(kind: Toast['kind'], text: string) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const push = useCallback((kind: Toast['kind'], text: string) => {
    const id = next.current++;
    setToasts((t) => [...t, { id, kind, text }]);
    const life = kind === 'error' ? 7000 : 4000;
    setTimeout(() => setToasts((t) => t.map((x) => (x.id === id ? { ...x, leaving: true } : x))), life - 250);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), life);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind} ${t.leaving ? 'leaving' : ''}`}>
            {t.kind === 'ok' ? <IconCheck style={{ color: 'var(--ok)' }} /> : t.kind === 'error' ? <IconAlert style={{ color: 'var(--critical)' }} /> : <IconInfo />}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastCtx);
  return {
    ok: (text: string) => push('ok', text),
    error: (err: unknown, fallback?: string) => push('error', typeof err === 'string' ? err : errorMessage(err, fallback)),
    info: (text: string) => push('info', text),
  };
}

// ── Activité réseau ──────────────────────────────────────────────────────────

/**
 * Fine barre animée en haut de l'écran pendant un chargement ou une action. Affichée après
 * 200 ms seulement : une réponse rapide ne provoque aucun clignotement.
 */
export function ActivityBar() {
  const busy = useIsFetching() + useIsMutating() > 0;
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!busy) { setShow(false); return undefined; }
    const t = setTimeout(() => setShow(true), 200);
    return () => clearTimeout(t);
  }, [busy]);
  return <div className={`activity-bar ${show ? 'on' : ''}`} role="progressbar" aria-hidden={!show} aria-label="Chargement en cours" />;
}
