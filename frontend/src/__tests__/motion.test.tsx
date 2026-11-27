import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useFreshKeys } from '../lib/motion';

describe('mise en évidence des nouveautés', () => {
  it('ne signale rien au premier affichage ni après un changement de filtre', () => {
    const { result, rerender } = renderHook(({ keys, scope }) => useFreshKeys(keys, scope), {
      initialProps: { keys: ['a', 'b'] as string[] | undefined, scope: 'nouvelle' },
    });
    expect(result.current.size).toBe(0);
    rerender({ keys: ['c', 'd'], scope: 'toutes' });
    expect(result.current.size).toBe(0);
  });

  it('signale les seuls éléments arrivés lors d’une actualisation', () => {
    const { result, rerender } = renderHook(({ keys }) => useFreshKeys(keys, 's'), { initialProps: { keys: ['a', 'b'] } });
    rerender({ keys: ['z', 'a', 'b'] });
    expect([...result.current]).toEqual(['z']);
  });
});
