import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: '#0f172a',
          medium: '#1e3a5f',
          light: '#1e40af'
        },
        teal: {
          DEFAULT: '#0d9488',
          light: '#14b8a6',
          dark: '#0f766e'
        },
        'blue-grey': {
          DEFAULT: '#64748b',
          light: '#94a3b8',
          subtle: '#cbd5e1'
        },
        surface: '#f8fafc',
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: '#0d9488',
          foreground: '#ffffff'
        },
        secondary: {
          DEFAULT: '#f1f5f9',
          foreground: '#0f172a'
        },
        destructive: {
          DEFAULT: '#ef4444',
          foreground: '#ffffff'
        },
        muted: {
          DEFAULT: '#f1f5f9',
          foreground: '#64748b'
        },
        accent: {
          DEFAULT: '#f0fdfa',
          foreground: '#0f172a'
        },
        card: {
          DEFAULT: '#ffffff',
          foreground: '#0f172a'
        },
        popover: {
          DEFAULT: '#ffffff',
          foreground: '#0f172a'
        }
      },
      borderRadius: {
        lg: '0.75rem',
        md: '0.625rem',
        sm: '0.375rem'
      },
      fontFamily: {
        sans: [
          'Inter',
          'system-ui',
          'sans-serif'
        ]
      },
      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.08)',
        'card-hover': '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)'
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' }
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' }
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'fade-in': 'fade-in 0.3s ease-out'
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
