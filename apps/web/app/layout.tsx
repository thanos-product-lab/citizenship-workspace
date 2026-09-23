import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@cw/design-system/tokens.css";
import "./globals.css";
import { clerkAppearance } from "@/lib/clerkAppearance";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Citizenship Workspace",
  description: "Prepare a UK naturalisation readiness case with clarity.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // The same pages the middleware uses, so a sign-in or sign-up started from anywhere in
    // the app (the user menu, an expired session) lands on ours, not Clerk's hosted ones.
    <ClerkProvider signInUrl="/sign-in" signUpUrl="/sign-up" appearance={clerkAppearance}>
      <html lang="en">
        <body>
          <Providers>{children}</Providers>
        </body>
      </html>
    </ClerkProvider>
  );
}
