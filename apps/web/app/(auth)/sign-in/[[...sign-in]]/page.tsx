import { SignIn } from "@clerk/nextjs";

import { AuthShell, SIGN_IN_PATH, SIGN_UP_PATH, authAppearance } from "../../AuthShell";

export default function SignInPage() {
  return (
    <AuthShell>
      {/* `path` names this route as the one Clerk's later steps (password, codes) navigate
          within, so a step never falls back to Clerk's hosted page. `signUpUrl` does the
          same for the "Sign up" link. */}
      <SignIn path={SIGN_IN_PATH} signUpUrl={SIGN_UP_PATH} appearance={authAppearance} />
    </AuthShell>
  );
}
