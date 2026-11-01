import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Toaster } from 'sonner';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'MediExplain AI — Understand Your Medical Reports',
  description: 'Upload your laboratory report and receive easy-to-understand explanations, detailed parameter insights and questions to discuss with your doctor.',
  keywords: 'medical report explanation, lab results, health report AI, medical AI India',
  openGraph: {
    title: 'MediExplain AI',
    description: 'Your Reports. Simplified. Your Health Conversations. Empowered.',
    type: 'website',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="min-h-screen bg-surface font-sans antialiased">
        {children}
        <Toaster position="top-right" richColors closeButton />
      </body>
    </html>
  );
}
