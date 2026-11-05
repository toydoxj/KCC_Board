import type { Metadata } from "next";

import "./globals.css";
import { APP_FULL_TITLE } from "@/lib/app-info";

export const metadata: Metadata = {
  title: APP_FULL_TITLE,
  description: APP_FULL_TITLE,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="font-sans" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
