/**
 * Tailwind CSS — Market Suite Design System
 * Tokens mapeados para CSS vars definidas em index.css.
 * Fonte da verdade: design_system_market.md
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],

  // dark mode via class="dark" no <html>
  darkMode: 'class',

  theme: {
    extend: {
      colors: {
        // ── Backgrounds ──────────────────────────────────
        'bg-canvas':          'var(--color-bg-canvas)',
        'bg-sidebar':         'var(--color-bg-sidebar)',

        // ── Superfícies ──────────────────────────────────
        'surface-card':       'var(--color-surface-card)',
        'surface-overlay':    'var(--color-surface-overlay)',
        'surface-hover':      'var(--color-surface-hover)',
        'surface-active':     'var(--color-surface-active)',

        // ── Bordas ────────────────────────────────────────
        'border-default':     'var(--color-border-default)',
        'border-subtle':      'var(--color-border-subtle)',
        'border-accent':      'var(--color-border-accent)',

        // ── Texto ─────────────────────────────────────────
        'text-primary':       'var(--color-text-primary)',
        'text-secondary':     'var(--color-text-secondary)',
        'text-muted':         'var(--color-text-muted)',
        'text-disabled':      'var(--color-text-disabled)',
        'text-inverse':       'var(--color-text-inverse)',

        // ── Acento / Marca ────────────────────────────────
        'accent-primary':     'var(--color-accent-primary)',
        'accent-secondary':   'var(--color-accent-secondary)',

        // ── Semântico ─────────────────────────────────────
        'success':            'var(--color-semantic-success)',
        'success-bg':         'var(--color-semantic-success-bg)',
        'danger':             'var(--color-semantic-danger)',
        'danger-bg':          'var(--color-semantic-danger-bg)',
        'warning':            'var(--color-semantic-warning)',
        'warning-bg':         'var(--color-semantic-warning-bg)',
        'info':               'var(--color-semantic-info)',
        'info-bg':            'var(--color-semantic-info-bg)',
      },

      borderRadius: {
        sm:   'var(--radius-sm)',
        md:   'var(--radius-md)',
        lg:   'var(--radius-lg)',
        xl:   'var(--radius-xl)',
        full: 'var(--radius-full)',
      },

      boxShadow: {
        sm:            'var(--shadow-sm)',
        md:            'var(--shadow-md)',
        lg:            'var(--shadow-lg)',
        glow:          'var(--shadow-glow)',
        'glow-subtle': 'var(--shadow-glow-subtle)',
      },

      transitionDuration: {
        fast:   '150ms',
        normal: '250ms',
        slow:   '350ms',
      },

      transitionTimingFunction: {
        'easing':        'cubic-bezier(0.4, 0, 0.2, 1)',
        'easing-out':    'cubic-bezier(0, 0, 0.2, 1)',
        'easing-in':     'cubic-bezier(0.4, 0, 1, 1)',
        'easing-bounce': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },

      animation: {
        'page-enter':       'page-enter 350ms cubic-bezier(0,0,0.2,1) both',
        'card-enter':       'card-enter 250ms cubic-bezier(0,0,0.2,1) both',
        'shimmer':          'shimmer 1.5s linear infinite',
        'glow-pulse':       'glow-pulse 2s ease-in-out infinite',
        'badge-pop':        'badge-pop 250ms cubic-bezier(0.34,1.56,0.64,1) both',
        'sidebar-enter':    'sidebar-enter 350ms cubic-bezier(0,0,0.2,1) both',
        'toast-enter':      'toast-enter 250ms cubic-bezier(0,0,0.2,1) both',
        'toast-exit':       'toast-exit 150ms cubic-bezier(0.4,0,1,1) both',
        'gradient-drift':   'gradient-drift 20s ease-in-out infinite',
        'price-flash-up':   'price-flash-up 600ms cubic-bezier(0,0,0.2,1) both',
        'price-flash-down': 'price-flash-down 600ms cubic-bezier(0,0,0.2,1) both',
      },
    },
  },

  plugins: [],
}
