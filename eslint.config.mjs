import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.next/**",
      "**/next-env.d.ts",
      "**/coverage/**",
      // Generated from the FastAPI OpenAPI schema — never hand-linted or edited.
      "packages/api-client/generated/**",
      // The Python virtualenv. Not ours to lint, and not obviously JavaScript at all
      // until M7 added boto3: botocore pulls in urllib3, which ships an Emscripten
      // worker `.js` that eslint picked up and failed on `self` being undefined.
      "services/platform/.venv/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    languageOptions: {
      globals: { ...globals.node },
    },
  },
);
