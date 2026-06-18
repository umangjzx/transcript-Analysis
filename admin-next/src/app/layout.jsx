import './globals.css';
import './app-components.css';
import Providers from '@/components/Providers';

export const metadata = {
  title: 'Melody Wings Safety',
  description: 'AI-powered audio grooming detection dashboard',
  icons: { icon: '/favicon.svg' },
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
