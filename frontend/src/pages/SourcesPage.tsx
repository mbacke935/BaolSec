/**
 * Sources de données — table (maquette) câblée à GET /sources, état dérivé de
 * GET /coverage. Actions d'administration (création, désactivation) pour l'ADMIN.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { sources } from '../api/resources';
import { coverage } from '../api/analyst';
import { useAuth } from '../hooks/useAuth';
import { useSearch } from '../components/AppShell';
import { Modal } from '../components/Modal';
import type { SourceCreate } from '../types/api';

function etat(state: string | undefined): { cls: string; label: string } {
  switch (state) {
    case 'ACTIVE': return { cls: 'up', label: '● Connectée' };
    case 'SILENCIEUSE': return { cls: 'down', label: '● Silencieuse' };
    case 'FLUX_INCOMPLET': return { cls: 'down', label: '● Flux incomplet' };
    case 'DESACTIVEE': return { cls: 'down', label: '● Désactivée' };
    default: return { cls: 'down', label: '● Inconnue' };
  }
}

export function SourcesPage() {
  const q = useSearch().toLowerCase();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const qc = useQueryClient();

  const srcQ = useQuery({ queryKey: ['sources'], queryFn: () => sources.list({ limit: 200 }) });
  const covQ = useQuery({ queryKey: ['coverage'], queryFn: () => coverage.list() });
  const covById = new Map((covQ.data ?? []).map((c) => [c.source_id, c.state]));

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<SourceCreate>({ name: '', type: 'syslog', description: '', silence_threshold_s: 300 });

  const createMut = useMutation({
    mutationFn: (body: SourceCreate) => sources.create(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sources'] }); setOpen(false); },
  });
  const disableMut = useMutation({
    mutationFn: (id: string) => sources.disable(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sources'] }),
  });

  const rows = (srcQ.data ?? []).filter((s) =>
    !q || `${s.name} ${s.type}`.toLowerCase().includes(q),
  );

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Sources de données</h3>
        {isAdmin && <button className="btn primary" style={{ padding: '8px 14px' }} onClick={() => setOpen(true)}>+ Nouvelle source</button>}
      </div>
      <p className="empty-note" style={{ padding: '0 0 12px' }}>État de connectivité des équipements supervisés (couverture calculée côté serveur).</p>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>SOURCE</th><th>TYPE</th><th>SEUIL DE SILENCE</th><th>ÉTAT</th>{isAdmin && <th>ACTIONS</th>}</tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const e = etat(covById.get(s.id));
              return (
                <tr key={s.id} style={{ opacity: s.active ? 1 : 0.5 }}>
                  <td style={{ fontWeight: 600, color: '#dbe6f0' }}>{s.name}</td>
                  <td>{s.type}</td>
                  <td>{Math.round(s.silence_threshold_s / 60)} min</td>
                  <td><span className={e.cls}>{e.label}</span></td>
                  {isAdmin && (
                    <td>
                      {s.active && (
                        <button className="rowbtn danger" onClick={() => { if (confirm(`Désactiver ${s.name} ?`)) disableMut.mutate(s.id); }}>Désactiver</button>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
            {srcQ.isLoading && <tr><td colSpan={isAdmin ? 5 : 4} className="empty-note">Chargement…</td></tr>}
            {!srcQ.isLoading && rows.length === 0 && (
              <tr><td colSpan={isAdmin ? 5 : 4} className="empty-note">Aucune source.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {open && (
        <Modal title="Nouvelle source" onClose={() => setOpen(false)}>
          <form onSubmit={(e) => { e.preventDefault(); createMut.mutate(form); }}>
            <div className="field"><label className="lbl">Nom</label>
              <input className="input" style={{ width: '100%' }} value={form.name} required onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div className="field"><label className="lbl">Type</label>
              <input className="input" style={{ width: '100%' }} value={form.type} required onChange={(e) => setForm({ ...form, type: e.target.value })} /></div>
            <div className="field"><label className="lbl">Seuil de silence (s)</label>
              <input className="input" style={{ width: '100%' }} type="number" min={0} value={form.silence_threshold_s} onChange={(e) => setForm({ ...form, silence_threshold_s: Number(e.target.value) })} /></div>
            {createMut.isError && <p className="auth-err">Erreur à la création (nom déjà utilisé ?)</p>}
            <div className="actions">
              <button type="button" className="btn" onClick={() => setOpen(false)}>Annuler</button>
              <button type="submit" className="btn primary" disabled={createMut.isPending}>{createMut.isPending ? '…' : 'Créer'}</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
