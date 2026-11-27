import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Polices auto-hébergées : aucune requête vers un service externe (fonctionnement hors ligne).
import '@fontsource/dm-sans/400.css';
import '@fontsource/dm-sans/500.css';
import '@fontsource/dm-sans/600.css';
import '@fontsource/dm-sans/700.css';
import '@fontsource/syne/600.css';
import '@fontsource/syne/700.css';
import '@fontsource/syne/800.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import './styles/app.css';
import { App } from './App';

const root = document.getElementById('root');
if (!root) throw new Error('Élément racine introuvable');
createRoot(root).render(<StrictMode><App /></StrictMode>);
