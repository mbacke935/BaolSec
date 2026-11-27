/**
 * Comptes utilisateurs (EF-03, ES-01, C5 /users) : création, rôle, désactivation, déverrouillage.
 * Le serveur interdit de se retirer ses propres droits et de supprimer le dernier administrateur.
 */
import { useDeferredValue, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { admin, users } from '../api/endpoints';
import { errorMessage } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import {
  Badge, Card, Confirm, Empty, ErrorNotice, Field, LoadingRows, Modal, Notice, PageHeader, Segmented, useToast,
} from '../components/ui';
import { IconEdit, IconPlus, IconUsers } from '../components/icons';
import { ago, dateTime, ROLE } from '../lib/format';
import type { User, UserRole } from '../types/api';

type View = 'active' | 'inactive' | 'all';
const isLocked = (u: User) => !!u.locked_until && new Date(u.locked_until) > new Date();

export function UsersPage() {
  const { user: me } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [view, setView] = useState<View>('active');
  const [text, setText] = useState('');
  const [editing, setEditing] = useState<User | 'new' | null>(null);
  const [confirm, setConfirm] = useState<User | null>(null);
  const q = useQuery({ queryKey: ['users'], queryFn: users.list });
  const roles = useQuery({ queryKey: ['roles'], queryFn: admin.roles });

  const toggle = useMutation({
    mutationFn: (u: User) => (u.is_active ? users.deactivate(u.id) : users.reactivate(u.id)),
    onSuccess: (u) => { toast.ok(u.is_active ? `Compte ${u.username} réactivé et déverrouillé.` : `Compte ${u.username} désactivé.`); setConfirm(null); qc.invalidateQueries({ queryKey: ['users'] }); },
    onError: (e) => { toast.error(e); setConfirm(null); },
  });

  const all = q.data?.items ?? [];
  const needle = useDeferredValue(text).trim().toLowerCase();
  const rows = all
    .filter((u) => view === 'all' || (view === 'active' ? u.is_active : !u.is_active))
    .filter((u) => !needle || `${u.username} ${u.email ?? ''}`.toLowerCase().includes(needle))
    .sort((a, b) => a.username.localeCompare(b.username));

  return (
    <>
      <PageHeader title="Utilisateurs"
        subtitle="Comptes d’accès à BaolSec. Un compte désactivé ne peut plus se connecter ; ses actions passées restent tracées sous son nom."
        actions={<button className="btn primary" onClick={() => setEditing('new')}><IconPlus />Créer un compte</button>} />

      {roles.data && (
        <div className="grid grid-2 mb-16">
          {roles.data.filter((r) => r.api_role).map((r) => (
            <section key={r.id} className="card card-pad">
              <div className="row between"><h3 style={{ fontSize: 15, fontWeight: 600 }}>{r.api_role ? ROLE[r.api_role] : r.name}</h3><span className="small faint">{r.active_users} compte(s) actif(s)</span></div>
              {r.description && <p className="small muted mt-8">{r.description}</p>}
              <ul className="small muted mt-8" style={{ margin: '8px 0 0', paddingLeft: 18, display: 'grid', gap: 3 }}>
                {r.permissions.map((p) => <li key={p}>{p}</li>)}
              </ul>
            </section>
          ))}
        </div>
      )}

      <Card>
        <div className="card-body">
          <div className="filters">
            <Segmented<View> value={view} onChange={setView} options={[
              { value: 'active', label: 'Actifs', count: all.filter((u) => u.is_active).length },
              { value: 'inactive', label: 'Désactivés', count: all.filter((u) => !u.is_active).length },
              { value: 'all', label: 'Tous', count: all.length },
            ]} />
            <Field label="Filtrer" className="grow"><input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Nom ou adresse e-mail…" /></Field>
          </div>
        </div>
        {q.error ? <div className="card-body"><ErrorNotice error={q.error} retry={() => q.refetch()} /></div> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Utilisateur</th><th>Rôle</th><th>État</th><th>Dernière connexion</th><th>Créé le</th><th /></tr></thead>
              {q.isLoading ? <LoadingRows cols={6} /> : (
                <tbody>
                  {rows.map((u) => (
                    <tr key={u.id} className={u.is_active ? '' : 'dim'}>
                      <td className="title-cell"><strong>{u.username}{u.id === me?.id && <span className="faint small"> (vous)</span>}</strong><span>{u.email ?? '—'}</span></td>
                      <td><Badge tone={u.role === 'ADMIN' ? 'accent' : 'info'}>{ROLE[u.role]}</Badge></td>
                      <td>{!u.is_active ? <Badge>Désactivé</Badge> : isLocked(u)
                        ? <Badge tone="warn" title={`Jusqu’au ${dateTime(u.locked_until)}`}>Verrouillé</Badge> : <Badge tone="ok" dot>Actif</Badge>}</td>
                      <td className="faint nowrap" title={dateTime(u.last_login_at)}>{u.last_login_at ? ago(u.last_login_at) : 'Jamais'}</td>
                      <td className="faint nowrap">{dateTime(u.created_at)}</td>
                      <td className="actions">
                        {isLocked(u) && u.is_active && <button className="btn sm" onClick={() => toggle.mutate({ ...u, is_active: false })}>Déverrouiller</button>}{' '}
                        <button className="btn sm ghost" onClick={() => setEditing(u)} aria-label={`Modifier ${u.username}`}><IconEdit /></button>{' '}
                        {u.id !== me?.id && <button className={`btn sm ${u.is_active ? 'danger' : ''}`} onClick={() => (u.is_active ? setConfirm(u) : toggle.mutate(u))}>{u.is_active ? 'Désactiver' : 'Réactiver'}</button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              )}
            </table>
            {!q.isLoading && rows.length === 0 && <Empty title="Aucun compte" icon={<IconUsers />} />}
          </div>
        )}
      </Card>

      {editing && <UserForm user={editing === 'new' ? null : editing} self={editing !== 'new' && editing.id === me?.id} onClose={() => setEditing(null)} />}
      {confirm && (
        <Confirm title={`Désactiver ${confirm.username} ?`} danger confirmLabel="Désactiver" busy={toggle.isPending}
          onCancel={() => setConfirm(null)} onConfirm={() => toggle.mutate(confirm)}>
          L’utilisateur ne pourra plus se connecter et ses sessions en cours expireront. Le compte et son historique sont conservés ; vous pourrez le réactiver.
        </Confirm>
      )}
    </>
  );
}

function UserForm({ user, self, onClose }: { user: User | null; self: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [email, setEmail] = useState(user?.email ?? '');
  const [username, setUsername] = useState(user?.username ?? '');
  const [role, setRole] = useState<UserRole>(user?.role ?? 'ANALYST');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => {
      if (user) {
        const body: Record<string, unknown> = {};
        if (email.trim() !== (user.email ?? '')) body.email = email.trim();
        if (username.trim() !== user.username) body.username = username.trim();
        if (role !== user.role) body.role = role;
        if (password) body.password = password;
        return users.update(user.id, body);
      }
      return users.create({ email: email.trim(), username: username.trim() || undefined, password, role });
    },
    onSuccess: (u) => { toast.ok(user ? `Compte ${u.username} mis à jour.` : `Compte ${u.username} créé.`); qc.invalidateQueries({ queryKey: ['users'] }); qc.invalidateQueries({ queryKey: ['roles'] }); onClose(); },
    onError: (err) => setError(errorMessage(err)),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault(); setError(null);
    if (!email.trim()) return setError('L’adresse e-mail est obligatoire.');
    if (!user && password.length < 8) return setError('Le mot de passe doit contenir au moins 8 caractères.');
    if (user && password && password.length < 8) return setError('Le nouveau mot de passe doit contenir au moins 8 caractères.');
    save.mutate();
  };

  return (
    <Modal title={user ? `Modifier ${user.username}` : 'Créer un compte'}
      subtitle={user ? 'Laissez le mot de passe vide pour le conserver.' : 'Transmettez le mot de passe initial à l’utilisateur par un canal sûr.'}
      onClose={onClose}
      footer={<>
        <button className="btn ghost" onClick={onClose}>Annuler</button>
        <button className="btn primary" type="submit" form="user-form" disabled={save.isPending}>{save.isPending && <span className="spinner" />}{user ? 'Enregistrer' : 'Créer'}</button>
      </>}>
      <form id="user-form" className="stack" onSubmit={submit} autoComplete="off">
        {error && <Notice kind="error">{error}</Notice>}
        <div className="form-grid">
          <Field label="Adresse e-mail" className="full"><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus /></Field>
          <Field label="Identifiant" help={user ? undefined : 'Facultatif : déduit de l’adresse e-mail.'}><input className="input" value={username} onChange={(e) => setUsername(e.target.value)} /></Field>
          <Field label="Rôle" help={self ? 'Vous ne pouvez pas modifier votre propre rôle.' : undefined}>
            <select className="select" value={role} disabled={self} onChange={(e) => setRole(e.target.value as UserRole)}>
              <option value="ANALYST">Analyste — traite alertes et incidents</option>
              <option value="ADMIN">Administrateur — gère comptes, sources et règles</option>
            </select>
          </Field>
          <Field label={user ? 'Nouveau mot de passe' : 'Mot de passe initial'} className="full" help="8 caractères au minimum ; privilégiez une phrase de passe.">
            <input className="input" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        </div>
      </form>
    </Modal>
  );
}
