import { SignUp } from "@clerk/nextjs";

import { AuthShell, SIGN_IN_PATH, SIGN_UP_PATH, authAppearance } from "../../AuthShell";

export default function SignUpPage() {
  return (
    <AuthShell>
      {/* The same pair as sign-in, the other way round: verification steps stay on this
          route, and "Sign in" goes to ours rather than Clerk's hosted page. */}
      <SignUp path={SIGN_UP_PATH} signInUrl={SIGN_IN_PATH} appearance={authAppearance} />
    </AuthShell>
  );
}
