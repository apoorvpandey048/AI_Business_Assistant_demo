import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Business Assistant",
  description:
    "Multi-source retrieval & orchestration — upload PDFs and SQLite databases, ask questions, and inspect grounded, cited answers.",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
    ],
  },
};

// Set the theme attribute BEFORE first paint to avoid a flash of the wrong theme.
// Reads the saved preference, falling back to the OS setting. Inlined so it runs
// synchronously ahead of hydration.
const themeScript = `(function(){try{var t=localStorage.getItem("aba.theme");if(!t){t=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
