/** Calls to the local Worldsmith server. Errors carry the server's own message. */
export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.error ?? `The server answered ${response.status}.`)
  return body as T
}

export interface Health { ok: boolean; name: string; version: string }
export interface FormatSource { repo: string; commit: string; package_format: number; sections: string[]; engine_kinds: string[] }
