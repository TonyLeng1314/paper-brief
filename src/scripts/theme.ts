type ThemeName = 'paper' | 'mist' | 'night' | 'mono';
type AccentName = 'default' | 'rust' | 'teal' | 'blue' | 'green' | 'magenta';

interface ThemeState {
  theme: ThemeName;
  accent: AccentName;
}

const STORAGE_KEY = 'paper-brief-theme';
const THEMES = new Set<ThemeName>(['paper', 'mist', 'night', 'mono']);
const ACCENTS = new Set<AccentName>([
  'default',
  'rust',
  'teal',
  'blue',
  'green',
  'magenta',
]);
const THEME_COLORS: Record<ThemeName, string> = {
  paper: '#f5efde',
  mist: '#f3f6f5',
  night: '#171918',
  mono: '#fafafa',
};

function readState(): ThemeState {
  try {
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}');
    return {
      theme: THEMES.has(stored.theme) ? stored.theme : 'paper',
      accent: ACCENTS.has(stored.accent) ? stored.accent : 'default',
    };
  } catch {
    return { theme: 'paper', accent: 'default' };
  }
}

function applyState(state: ThemeState, persist = true): void {
  document.documentElement.dataset.theme = state.theme;
  if (state.accent === 'default') {
    delete document.documentElement.dataset.accent;
  } else {
    document.documentElement.dataset.accent = state.accent;
  }

  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', THEME_COLORS[state.theme]);

  document.querySelectorAll<HTMLElement>('[data-theme-option]').forEach((option) => {
    const active = option.dataset.themeOption === state.theme;
    option.dataset.active = String(active);
    option.setAttribute('aria-checked', String(active));
  });
  document.querySelectorAll<HTMLElement>('[data-accent-option]').forEach((option) => {
    const active = option.dataset.accentOption === state.accent;
    option.dataset.active = String(active);
    option.setAttribute('aria-checked', String(active));
  });

  if (persist) {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {}
  }
}

export function initThemePicker(): void {
  const picker = document.querySelector<HTMLElement>('[data-theme-picker]');
  const toggle = picker?.querySelector<HTMLButtonElement>('[data-theme-toggle]');
  const panel = picker?.querySelector<HTMLElement>('[data-theme-panel]');
  if (!picker || !toggle || !panel) return;

  let state = readState();
  applyState(state, false);

  const setOpen = (open: boolean): void => {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) {
      panel
        .querySelector<HTMLButtonElement>('[data-theme-option][data-active="true"]')
        ?.focus();
    }
  };

  toggle.addEventListener('click', () => setOpen(panel.hidden));

  picker.querySelectorAll<HTMLButtonElement>('[data-theme-option]').forEach((option) => {
    option.addEventListener('click', () => {
      const theme = option.dataset.themeOption as ThemeName;
      if (!THEMES.has(theme)) return;
      state = { ...state, theme };
      applyState(state);
    });
  });

  picker.querySelectorAll<HTMLButtonElement>('[data-accent-option]').forEach((option) => {
    option.addEventListener('click', () => {
      const accent = option.dataset.accentOption as AccentName;
      if (!ACCENTS.has(accent)) return;
      state = { ...state, accent };
      applyState(state);
    });
  });

  picker.querySelector<HTMLButtonElement>('[data-theme-reset]')?.addEventListener('click', () => {
    state = { theme: 'paper', accent: 'default' };
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {}
    applyState(state, false);
  });

  document.addEventListener('pointerdown', (event) => {
    if (!panel.hidden && !picker.contains(event.target as Node)) setOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) {
      setOpen(false);
      toggle.focus();
    }
  });
}
