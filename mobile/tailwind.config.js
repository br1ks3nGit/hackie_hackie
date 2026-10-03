// Token names and values mirror backend/uno.config.ts (source: docs/design-system.md, section 6).
// Change a token in both configs. Hex strings only.
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./App.tsx', './src/**/*.{ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: '#0062CC', hover: '#0052A8', active: '#00428A', fg: '#FFFFFF' },
        surface: { DEFAULT: '#FFFFFF', muted: '#F3F4F6' },
        border: { DEFAULT: '#D1D5DB', strong: '#6B7280' },
        text: { DEFAULT: '#111827', muted: '#4B5563' },
        nav: { DEFAULT: '#111827', fg: '#E5E7EB' },
        focus: '#1D4ED8',
        success: { DEFAULT: '#15803D', soft: '#DCFCE7', ink: '#166534' },
        warning: { DEFAULT: '#B45309', soft: '#FEF3C7', ink: '#92400E' },
        danger: { DEFAULT: '#B91C1C', soft: '#FEE2E2', ink: '#991B1B' },
        info: { DEFAULT: '#1D4ED8', soft: '#DBEAFE', ink: '#1E40AF' },
        tier: {
          a: { DEFAULT: '#15803D', soft: '#DCFCE7', ink: '#14532D' },
          b: { DEFAULT: '#4D7C0F', soft: '#ECFCCB', ink: '#365314' },
          c: { DEFAULT: '#A16207', soft: '#FEF08A', ink: '#713F12' },
          d: { DEFAULT: '#C2410C', soft: '#FFEDD5', ink: '#7C2D12' },
          e: { DEFAULT: '#B91C1C', soft: '#FEE2E2', ink: '#7F1D1D' },
        },
        event: {
          'harsh-brake': '#C2410C',
          'harsh-accel': '#7E22CE',
          'sharp-corner': '#0E7490',
          speeding: '#B91C1C',
          crash: '#111827',
        },
      },
    },
  },
  plugins: [],
};
