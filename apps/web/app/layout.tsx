import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@cw/design-system/tokens.css";
import "./globals.css";
import { clerkAppearance } from "@/lib/clerkAppearance";
import { THEME_BOOT_SCRIPT } from "@/lib/theme";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Citizenship Workspace",
  description: "Prepare your UK citizenship application.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // The same pages the middleware uses, so a sign-in or sign-up started from anywhere in
    // the app (the user menu, an expired session) lands on ours, not Clerk's hosted ones.
    <ClerkProvider signInUrl="/sign-in" signUpUrl="/sign-up" appearance={clerkAppearance}>
      {/* `suppressHydrationWarning` on `<html>` only, and for one reason: the boot script
          below may set `data-theme` on it before React hydrates, so the server's `<html>`
          and the browser's legitimately differ by that attribute. It does not reach the
          children. */}
      <html lang="en" suppressHydrationWarning>
        <head>
          {/* Applies a saved Light or Dark choice before the first paint. See `lib/theme`. */}
          <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
        </head>
        <body>
          <Providers>{children}</Providers>
        </body>
      </html>
    </ClerkProvider>
  );
}
