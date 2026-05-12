import './globals.css';
import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import { SiteHeader } from '@/components/site-header';
import { SiteFooter } from '@/components/site-footer';
import { SITE_NAME, SITE_DESC } from '@/lib/constants';

const inter = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-sans' });
const mono = JetBrains_Mono({ subsets: ['latin'], display: 'swap', variable: '--font-mono' });

export const metadata: Metadata = {
  title: { default: SITE_NAME, template: `%s · ${SITE_NAME}` },
  description: SITE_DESC,
  icons: {
    icon: `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%23111827'/%3E%3Ctext x='50%25' y='55%25' fill='white' font-family='Inter,Arial' font-size='13' font-weight='700' text-anchor='middle' dominant-baseline='middle'%3EDR%3C/text%3E%3C/svg%3E`,
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen flex flex-col">
        <SiteHeader />
        <main className="flex-1 container-page py-6 sm:py-8">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
