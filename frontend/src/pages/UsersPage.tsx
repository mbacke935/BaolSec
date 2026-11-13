/** Gestion des utilisateurs (ADMIN) — table (maquette) câblée à /users. */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { users as usersApi } from '../api/resources';
import { useSearch } from '../components/AppShell';
import { Modal } from '../components/Modal';
import type { User, UserCreate, UserRole } from '../types/api';
import { fmtDateTime } from '../lib/ui';

export function UsersPage() {
  const q = useSearch().toLowerCase();
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list() });

  const createMut = useMutation({
    mutationFn: (body: UserCreate) => usersApi.create(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setOpen(false); },
  });
  const updateMut = useMutation({
    mutationFn: ({ id, role }: { id: string; role: UserRole }) => usersApi.update(id, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });
  const disableMut = useMutation({
    mutationFn: (id: string) => usersApi.disable(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<UserCreate>({ email: '', password: '', role: 'ANALYST' });

  const rows = (data as User[]).filter((u) =>
    !q || `${u.email ?? ''} ${u.username} ${u.role}`.toLowerCase().includes(q),
  );

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Utilisateurs</h3>
        <button className="btn primary" style={{ padding: '8px 14px' }} onClick={() => setOpen(true)}>+ Nouvel utilisateur</button>
      </div>
      <p className="empty-note" style={{ padding: '0 0 12px' }}>Comptes, rôles et statut. Les droits sont appliqués par l'API.</p>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>E-MAIL</th><th>IDENTIFIANT</th><th>RÔLE</th><th>STATUT</th><th>CRÉÉ LE</th><th>ACTIONS</th></tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                <td style={{ fontWeight: 600, color: '#dbe6f0' }}>{u.email ?? '—'}</td>
                <td>{u.username}</td>
                <td>
                  <select
                    className="input"
                    style={{ padding: '4px 8px', fontSize: 12 }}
                    value={u.role}
                    onChange={(e) => updateMut.mutate({ id: u.id, role: e.target.value as UserRole })}
                  >
                    <option value="ANALYST">Analyste</option>
                    <option value="ADMIN">Administrateur</option>
                  </select>
                </td>
                <td><span className={u.is_active ? 'up' : 'down'}>{u.is_active ? '● Actif' : '○ Désactivé'}</span></td>
                <td style={{ color: '#7f96ab' }}>{fmtDateTime(u.created_at)}</td>
                <td>{u.is_active && (
                  <button className="rowbtn danger" onClick={() => { if (confirm(`Désactiver ${u.email ?? u.username} ?`)) disableMut.mutate(u.id); }}>Désactiver</button>
                )}</td>
              </tr>
            ))}
            {isLoading && <tr><td colSpan={6} className="empty-note">Chargement…</td></tr>}
            {!isLoading && rows.length === 0 && <tr><td colSpan={6} className="empty-note">Aucun utilisateur.</td></tr>}
          </tbody>
        </table>
      </div>

      {open && (
        <Modal title="Nouvel utilisateur" onClose={() => setOpen(false)}>
          <form onSubmit={(e) => { e.preventDefault(); createMut.mutate(form); }}>
            <div className="field"><label className="lbl">E-mail</label>
              <input className="input" style={{ width: '100%' }} type="email" value={form.email} required onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
            <div className="field"><label className="lbl">Mot de passe (min. 8)</label>
              <input className="input" style={{ width: '100%' }} type="password" minLength={8} value={form.password} required onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
            <div className="field"><label className="lbl">Rôle</label>
              <select className="input" style={{ width: '100%' }} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}>
                <option value="ANALYST">Analyste</option>
                <option value="ADMIN">Administrateur</option>
              </select></div>
            {createMut.isError && <p className="auth-err">Erreur (e-mail déjà utilisé ?)</p>}
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
