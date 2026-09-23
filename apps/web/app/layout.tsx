import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@cw/design-system/tokens.css";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Citizenship Workspace",
  description: "Prepare a UK naturalisation readiness case with clarity.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // The same page the middleware sends signed-out visitors to, so a sign-in started from
    // anywhere in the app (the user menu, an expired session) lands there too.
    <ClerkProvider signInUrl="/sign-in">
      <html lang="en">
        <body>
          <Providers>{children}</Providers>
        </body>
      </html>
    </ClerkProvider>
  );
}
