import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['-apple-system','BlinkMacSystemFont','"SF Pro Display"','"SF Pro Text"','"Plus Jakarta Sans"','"Helvetica Neue"','Arial','sans-serif'], mono: ['ui-monospace','"SF Mono"','Menlo','monospace'] },
      colors: { brand: { 50: '#eef2ff', 100: '#e0e7ff', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca', 900: '#1e1b4b' } },
    },
  },
  plugins: [],
};
export default config;
