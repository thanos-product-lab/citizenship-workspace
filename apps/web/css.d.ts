// Ambient declaration for CSS side-effect imports (global stylesheets), e.g.
// `import "@cw/design-system/tokens.css"` and `import "./globals.css"`.
// TypeScript has no native type for CSS, so this keeps such imports type-checking
// in every editor/tool state. The bundler (Next/Turbopack) handles the actual CSS.
declare module "*.css";
