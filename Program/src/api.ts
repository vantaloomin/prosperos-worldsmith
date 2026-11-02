/** Calls to the local Worldsmith server. Errors carry the server's own message. */
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? 'The request was not understood.' : body.detail
    throw new Error(body.error ?? detail ?? `The server answered ${response.status}.`)
  }
  return body as T
}

export const getJson = <T,>(path: string) => call<T>(path)
export const sendJson = <T,>(path: string, method: 'POST' | 'PUT', data: unknown) =>
  call<T>(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })

export interface Health { ok: boolean; name: string; version: string }
export interface FormatSource { repo: string; commit: string; package_format: number; sections: string[]; engine_kinds: string[] }
export interface Settings { dungeon_checkout: string | null; recent_folders: string[] }
export interface BuiltinWorld { id: string; name: string; genre: string; pitch: string }
export interface WorldsListing {
  checkout: string | null
  checkout_problem: string
  builtin: BuiltinWorld[]
  recent: { folder: string; name: string }[]
}
export type WorldRef = { builtin: string } | { folder: string }
export interface Town { id: string; name: string; summary: string; road: boolean; places: number; notables: number; parts: string[] }
export interface WorldOverview {
  world: { id: string | null; name: string | null; genre: string | null; pitch: string | null; default_ruleset: string | null; status: string | null }
  kind: 'builtin' | 'folder'
  folder: string
  towns: Town[]
  sections: Record<string, { entries: number; hidden: number }>
  documents: number
  engine: Record<string, number>
  problems: string[]
}
export interface TownFiles {
  id: string
  parts: Record<string, Record<string, unknown> | null>
  problems: Record<string, string[]>
  undo: { id: number; at: string; kind: string }[]
}
