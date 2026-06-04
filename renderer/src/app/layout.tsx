import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "KCC Board",
  description: "건식벽체 구조검토",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="font-sans">{children}</body>
    </html>
  );
}
