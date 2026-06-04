import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Trading Lab",
  description: "Local Alpaca paper trading operator dashboard",
};

// Synchronously resolve the user's theme preference and stamp it on <html>
// before the body paints. Without this the page renders with the dark default
// and then flips to light once React mounts.
const THEME_BOOTSTRAP = `(function(){try{var p=window.localStorage.getItem('dashTheme')||'system';if(p!=='light'&&p!=='dark'&&p!=='system')p='system';document.documentElement.dataset.themePref=p;var t=p;if(p==='system'){t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark';}document.documentElement.dataset.theme=t;}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: the bootstrap script below writes
    // data-theme-pref / data-theme to <html> before React hydrates, so the
    // client tree intentionally diverges from the server tree on those attrs.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
