import type { CSSProperties } from 'react';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { users as usersApi, toList } from '../api/resources';
import type { User, UserCreate, UserRole, UserUpdate } from '../types/api';
import '../styles/design-system.css';

function initials(email: string) {
  const parts = email.split('@')[0].split(/[._-]/);
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : email.slice(0, 2).toUpperCase();
}

export function UsersPage() {
  const qc = useQueryClient();
  const { data: dataRaw, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list(),
  });

  const data = toList<User>(dataRaw);

  const disableMut = useMutation({
    mutationFn: (id: string) => usersApi.disable(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });
  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: UserUpdate }) => usersApi.update(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });
  const createMut = useMutation({
    mutationFn: (body: UserCreate) => usersApi.create(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setShowForm(false); setEmail(''); setPassword(''); },
  });

  const [showForm,  setShowForm]  = useState(false);
  const [email,     setEmail]     = useState('');
  const [password,  setPassword]  = useState('');
  const [role,      setRole]      = useState<UserRole>('ANALYST');

  const activeCount = data.filter((u) => u.is_active).length;
  const adminCount  = data.filter((u) => u.role === 'ADMIN').length;

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title">Utilisateurs <span>& accès</span></h1>
          <p className="bs-page-sub">Gestion des comptes et des droits d'accès au SIEM</p>
        </div>
        <button
          className="bs-btn bs-btn-primary bs-btn-sm"
          onClick={() => { setShowForm((v) => !v); setEmail(''); setPassword(''); }}
        >
          {showForm ? 'Fermer' : '+ Nouvel utilisateur'}
        </button>
      </div>

      {/* KPIs */}
      <div className="bs-kpi-grid">
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--success)' } as CSSProperties}>
          <div className="bs-kpi-label">Comptes actifs</div>
          <div className="bs-kpi-value bs-glow-accent">{isLoading ? '…' : activeCount}</div>
          <div className="bs-kpi-sub">Utilisateurs avec accès</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent3)' } as CSSProperties}>
          <div className="bs-kpi-label">Administrateurs</div>
          <div className="bs-kpi-value">{isLoading ? '…' : adminCount}</div>
          <div className="bs-kpi-sub">Accès complet</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent2)' } as CSSProperties}>
          <div className="bs-kpi-label">Total</div>
          <div className="bs-kpi-value">{isLoading ? '…' : data.length}</div>
          <div className="bs-kpi-sub">Comptes enregistrés</div>
        </div>
      </div>

      {/* Formulaire de création */}
      {showForm && (
        <div className="bs-card bs-mb-16">
          <div className="bs-section-header">
            <span className="bs-section-title">Créer un compte</span>
          </div>
          <form
            onSubmit={(e) => { e.preventDefault(); createMut.mutate({ email, password, role }); }}
            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10, alignItems: 'end', maxWidth: 700 }}
          >
            <div>
              <label className="bs-label">Adresse email *</label>
              <input
                className="bs-input"
                type="email"
                placeholder="analyst@baolsec.io"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="bs-label">Mot de passe *</label>
              <input
                className="bs-input"
                type="password"
                placeholder="Min. 8 caractères"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>
            <div>
              <label className="bs-label">Rôle</label>
              <select
                className="bs-select"
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole)}
              >
                <option value="ANALYST">ANALYST</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label className="bs-label">&nbsp;</label>
              <button
                type="submit"
                className="bs-btn bs-btn-primary bs-btn-sm"
                disabled={createMut.isPending}
              >
                {createMut.isPending ? '…' : '+ Créer'}
              </button>
            </div>
            {createMut.isError && (
              <div className="bs-error" style={{ gridColumn: '1 / -1', fontSize: 12 }}>
                Email déjà utilisé ou erreur serveur
              </div>
            )}
          </form>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <div className="bs-loading"><div className="bs-spinner" /> Chargement des utilisateurs…</div>
      ) : (
        <div className="bs-card" style={{ padding: 0 }}>
          <div className="bs-table-wrap" style={{ border: 'none', borderRadius: 'var(--radius)' }}>
            <table className="bs-table">
              <thead>
                <tr>
                  <th>Utilisateur</th>
                  <th>Rôle</th>
                  <th>Statut</th>
                  <th>Inscrit le</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.map((u: User) => (
                  <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div className="bs-user-avatar" style={{
                          width: 30, height: 30, minWidth: 30, fontSize: 11,
                          background: u.role === 'ADMIN' ? 'rgba(124,58,237,0.2)' : 'rgba(0,212,170,0.15)',
                          color: u.role === 'ADMIN' ? 'var(--accent3)' : 'var(--accent)',
                        }}>
                          {initials(u.email)}
                        </div>
                        <span style={{ fontWeight: 500, fontSize: 13, color: 'var(--fg)' }}>{u.email}</span>
                      </div>
                    </td>
                    <td>
                      <select
                        className="bs-select"
                        value={u.role}
                        onChange={(e) => updateMut.mutate({ id: u.id, body: { role: e.target.value as UserRole } })}
                        style={{ padding: '3px 8px', fontSize: 11, width: 'auto' }}
                        disabled={updateMut.isPending}
                      >
                        <option value="ANALYST">ANALYST</option>
                        <option value="ADMIN">ADMIN</option>
                      </select>
                    </td>
                    <td>
                      <span className={`bs-badge ${u.is_active ? 'active' : 'neutral'}`}>
                        {u.is_active ? 'Actif' : 'Désactivé'}
                      </span>
                    </td>
                    <td className="bs-mono" style={{ fontSize: 11, color: 'var(--fg3)' }}>
                      {new Date(u.created_at).toLocaleDateString('fr-FR')}
                    </td>
                    <td>
                      {u.is_active && (
                        <button
                          className="bs-btn bs-btn-danger bs-btn-xs"
                          disabled={disableMut.isPending}
                          onClick={() => {
                            if (window.confirm(`Désactiver l'utilisateur « ${u.email} » ?`)) {
                              disableMut.mutate(u.id);
                            }
                          }}
                        >
                          Désactiver
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {data.length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <div className="bs-empty">
                        <div className="bs-empty-icon">◎</div>
                        <div className="bs-empty-text">Aucun utilisateur enregistré</div>
                        <div className="bs-empty-sub">Créez le premier compte ci-dessus</div>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
