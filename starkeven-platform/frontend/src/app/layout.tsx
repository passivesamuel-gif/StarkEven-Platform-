import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { ThemeProvider } from '@/components/ThemeContext';
import './globals.css';

export const metadata: Metadata = {
  title: 'StarkEven | B2B lead & data intelligence API',
  description: 'Enrich any company domain with tech stack, email infrastructure and hiring signals. Deterministic, fast, pay-per-lookup.',
};

const themeInitScript = `
(function() {
  try {
    var saved = localStorage.getItem('starkeven_theme');
    var dark = saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.classList.toggle('dark', dark);
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-screen bg-[#FBFBFD] font-sans text-slate-900 antialiased transition-colors dark:bg-[#0B0B0C] dark:text-slate-100">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
