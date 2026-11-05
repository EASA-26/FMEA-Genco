import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/genco-theme.css';
import './styles/tokens.css';
import './styles/base.css';
import './styles/shell.css';
import './styles/views.css';
import './styles/flow.css';
import './styles/review.css';
import './styles/export.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
