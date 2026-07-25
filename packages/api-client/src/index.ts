import createClient, { type Client } from "openapi-fetch";

import type { paths } from "../generated/schema";

export type { components, paths } from "../generated/schema";

/**
 * Typed API client. Every backend call in the app goes through this — never
 * hand-write request/response types or raw fetch typing (CLAUDE.md §6). The
 * `paths` type is generated from the FastAPI OpenAPI schema by `just api-client`.
 */
export function createApiClient(baseUrl: string): Client<paths> {
  return createClient<paths>({ baseUrl });
}
