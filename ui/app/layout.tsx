import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Business Knowledge Assistant",
  description:
    "Multi-source retrieval & orchestration — query routing, hybrid retrieval, grounded answers, full traceability.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
