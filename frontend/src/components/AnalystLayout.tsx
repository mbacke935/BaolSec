/**
 * Layout de l'interface d'analyse (C23).
 * Design aligné sur la maquette BaolSec (--bg:#071321, --green2:#36d69a, etc.)
 */
import { type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

const CSS_VARS = `
  :root {
    --bg: #071321;
    --panel: #0d1d30;
    --panel2: #10243a;
    --line: #1c3650;
    --text: #eef5fb;
    --muted: #9aadc0;
    --green: #16a36b;
    --green2: #36d69a;
    --blue: #48a5ed;
    --red: #f05c68;
    --amber: #eab45c;
  }
`;

const NAV = [
  { path: '/',           icon: '◉', label: 'Tableau de bord' },
  { path: '/incidents',  icon: '⚡', label: 'Incidents' },
  { path: '/search',     icon: '🔍', label: 'Recherche' },
  { path: '/coverage',   icon: '📡', label: 'Couverture' },
];

export function AnalystLayout({ children, userEmail }: { children: ReactNode; userEmail?: string }) {
  const loc = useLocation();

  return (
    <>
      <style>{CSS_VARS}</style>
      <div style={{ display: 'grid', gridTemplateColumns: '235px 1fr', minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, sans-serif', fontSize: '15px' }}>
        {/* Sidebar */}
        <aside style={{ background: '#091827', borderRight: '1px solid var(--line)', padding: '22px 14px', display: 'flex', flexDirection: 'column' }}>
          {/* Logo */}
          <div style={{ padding: '0 10px 25px', display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 800, fontSize: '19px', letterSpacing: '-0.5px' }}>
            <span style={{ color: 'var(--green2)' }}>Baol</span><span>Sec</span>
            <span style={{ marginLeft: 'auto', fontSize: '10px', color: 'var(--green2)', border: '1px solid #16a36b55', borderRadius: '4px', padding: '1px 5px' }}>Analyse</span>
          </div>

          <span style={{ fontSize: '10px', letterSpacing: '1.4px', color: '#698198', padding: '0 12px 8px', textTransform: 'uppercase' }}>Navigation</span>

          {NAV.map(({ path, icon, label }) => {
            const active = path === '/' ? loc.pathname === '/' : loc.pathname.startsWith(path);
            return (
              <Link
                key={path}
                to={path}
                style={{
                  width: '100%', textAlign: 'left', color: active ? 'var(--green2)' : '#a9bbcc',
                  background: active ? '#123a3a' : 'none', border: 0, borderRadius: '9px',
                  padding: '11px 12px', fontSize: '13px', margin: '2px 0', display: 'flex',
                  alignItems: 'center', gap: '8px', textDecoration: 'none', cursor: 'pointer',
                }}
              >
                <span>{icon}</span> {label}
              </Link>
            );
          })}

          {userEmail && (
            <div style={{ marginTop: 'auto', borderTop: '1px solid var(--line)', padding: '18px 10px 0', fontSize: '12px', color: '#b7c6d4' }}>
              <div>Connecté en tant que</div>
              <div style={{ color: 'var(--text)', fontWeight: 600 }}>{userEmail}</div>
            </div>
          )}
        </aside>

        {/* Contenu */}
        <main style={{ padding: '25px 30px', minWidth: 0, overflowY: 'auto' }}>
          {children}
        </main>
      </div>
    </>
  );
}
