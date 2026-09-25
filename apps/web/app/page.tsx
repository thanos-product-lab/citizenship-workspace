
import { AccountMenu } from "@/features/account/AccountMenu";
import { CasesPanel } from "@/features/cases/CasesPanel";

export default function HomePage() {
  return (
    <main style={{ maxWidth: "48rem", margin: "0 auto", padding: "var(--cw-space-8)" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          paddingBottom: "var(--cw-space-6)",
          borderBottom: "1px solid var(--cw-border)",
        }}
      >
        <span style={{ fontWeight: "var(--cw-weight-semibold)" }}>Citizenship Workspace</span>
        <AccountMenu />
      </header>

      <section style={{ paddingTop: "var(--cw-space-8)" }}>
        <h1 style={{ fontSize: "var(--cw-text-2xl)", margin: 0 }}>Your workspace</h1>
        <p style={{ color: "var(--cw-text-muted)", marginTop: "var(--cw-space-2)" }}>
          Each case is one citizenship application: your answers, your trips and your
          documents.
        </p>
        <CasesPanel />
      </section>
    </main>
  );
}
