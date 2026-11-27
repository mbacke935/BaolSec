/**
 * Mouvement et fluidité de l'interface : petits hooks sans bibliothèque.
 * Tous respectent le réglage système « réduire les animations » (prefers-reduced-motion).
 */
import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react';

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Compte de la valeur précédente jusqu'à la nouvelle (indicateurs chiffrés), sur `duration` ms. */
export function useCountUp(value: number, duration = 600): number {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current;
    if (start === value || prefersReducedMotion()) { from.current = value; setShown(value); return; }
    let raf = 0;
    const t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - k, 3);
      setShown(Math.round(start + (value - start) * eased));
      if (k < 1) raf = requestAnimationFrame(step); else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => { cancelAnimationFrame(raf); from.current = value; };
  }, [value, duration]);
  return shown;
}

/**
 * Identifiants apparus depuis l'affichage précédent (actualisation automatique) : la ligne
 * correspondante est mise en évidence un instant. Rien n'est signalé au premier chargement ni
 * quand `scope` change (autre filtre, autre page de résultats) : seules les vraies nouveautés comptent.
 */
export function useFreshKeys(keys: string[] | undefined, scope = ''): Set<string> {
  const seen = useRef<Set<string> | null>(null);
  const seenScope = useRef(scope);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const signature = `${scope}#${(keys ?? []).join('|')}`;
  useEffect(() => {
    if (!keys) return;
    if (seen.current === null || seenScope.current !== scope) {
      seen.current = new Set(keys); seenScope.current = scope; setFresh(new Set()); return;
    }
    const added = keys.filter((k) => !seen.current!.has(k));
    keys.forEach((k) => seen.current!.add(k));
    if (added.length) setFresh(new Set(added));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);
  useEffect(() => {
    if (!fresh.size) return undefined;
    const t = setTimeout(() => setFresh(new Set()), 2400);
    return () => clearTimeout(t);
  }, [fresh]);
  return fresh;
}

/** Position de l'élément actif d'un groupe (onglets, filtres) pour faire glisser l'indicateur. */
export function useIndicator(container: RefObject<HTMLElement>, activeSelector: string, deps: unknown[]) {
  const [box, setBox] = useState<{ left: number; width: number; top: number; height: number } | null>(null);
  useLayoutEffect(() => {
    const root = container.current;
    if (!root) return undefined;
    const measure = () => {
      const el = root.querySelector<HTMLElement>(activeSelector);
      setBox(el ? { left: el.offsetLeft, width: el.offsetWidth, top: el.offsetTop, height: el.offsetHeight } : null);
    };
    measure();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    ro?.observe(root);
    return () => ro?.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return box;
}
