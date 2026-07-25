import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@cw/design-system/tokens.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Citizenship Workspace",
  description: "Prepare a UK naturalisation readiness case with clarity.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>{children}</body>
      </html>
    </ClerkProvider>
  );
}
