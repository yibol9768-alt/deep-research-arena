import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: '1rem', sm: '1.5rem', lg: '2rem' },
      screens: { '2xl': '1440px' },
    },
    extend: {
      colors: {
        // canvas
        bg: '#FAFAF7',
        surface: '#fdf7ff',
        'surface-low': '#f8f2fa',
        'surface-mid': '#f2ecf4',
        'surface-high': '#ece6ee',
        white: '#ffffff',

        // ink
        ink: '#0B0B0F',
        'ink-soft': '#1d1b20',
        muted: '#494551',
        'muted-2': '#7a7582',
        hairline: '#E8E8E4',
        'outline-soft': '#cbc4d2',

        // brand
        brand: { DEFAULT: '#7F4BF3', dark: '#4f378a', soft: '#cfbcff', wash: '#e0d2ff', footer: '#C8A8FF' },

        // semantic
        good: '#34A853',
        warn: '#FF9900',
        bad: '#E5484D',
        gold: '#F5B800',
        silver: '#B8BCC4',
        bronze: '#C97C42',

        // provider palette (per-agent / per-backbone)
        p: {
          openai: '#1f1f1f',
          anthropic: '#cc785c',
          google: '#34A853',
          meta: '#047AFE',
          deepseek: '#1c7ff8',
          xai: '#ff6900',
          mistral: '#ff7018',
          glm: '#86b737',
          qwen: '#FF9900',
          minimax: '#EB3568',
          nvidia: '#76B900',
          z: '#6E5BFF',
          smolagents: '#7F4BF3',
          camel: '#cc785c',
          deerflow: '#1c7ff8',
          storm: '#494551',
          ldr: '#34A853',
          flowsearcher: '#7F4BF3',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['var(--font-instrument)', 'Georgia', 'Cambria', 'serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      fontSize: {
        display: ['clamp(40px, 6vw, 64px)', { lineHeight: '1.05', letterSpacing: '-0.02em' }],
        'display-lg': ['48px', { lineHeight: '1.1', letterSpacing: '-0.02em', fontWeight: '400' }],
        'h-md': ['32px', { lineHeight: '1.2', fontWeight: '400' }],
        'h-sm': ['24px', { lineHeight: '1.3', fontWeight: '400' }],
        caps: ['12px', { lineHeight: '1', letterSpacing: '0.05em', fontWeight: '600' }],
        data: ['13px', { lineHeight: '1', fontWeight: '500' }],
      },
      borderRadius: {
        DEFAULT: '0.5rem',
        card: '14px',
        pill: '9999px',
        tab: '8px',
      },
      boxShadow: {
        soft: '0 2px 8px rgba(11,11,15,.04)',
        lift: '0 1px 2px rgba(11,11,15,.04), 0 8px 24px -8px rgba(11,11,15,.08)',
        hover: '0 2px 4px rgba(11,11,15,.06), 0 16px 40px -12px rgba(127,75,243,.25)',
        ring: '0 0 0 4px rgba(127,75,243,.18)',
      },
      transitionTimingFunction: {
        smooth: 'cubic-bezier(0.4, 0, 0.2, 1)',
        back: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      keyframes: {
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        breathe: {
          '0%,100%': { opacity: '0.6' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.5s cubic-bezier(0.4, 0, 0.2, 1)',
        shimmer: 'shimmer 2.4s linear infinite',
        breathe: 'breathe 3s ease-in-out infinite',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}

export default config
