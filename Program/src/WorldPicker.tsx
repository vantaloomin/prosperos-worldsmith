import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderOpen } from 'lucide-react'
import { getJson, sendJson, type Settings, type WorldRef, type WorldsListing } from './api'
import { ImportPackage } from './Packages'

/** Choosing a world: the Dungeon checkout's built-in worlds, recent world folders, or any folder by its path. */
export function WorldPicker({ onOpen, busy }: { onOpen: (ref: WorldRef) => void; busy: boolean }) {
  const client = useQueryClient()
  const listing = useQuery({ queryKey: ['worlds'], queryFn: () => getJson<WorldsListing>('/api/worlds') })
  const [checkout, setCheckout] = useState<string | null>(null)
  const [folder, setFolder] = useState('')
  const saveCheckout = useMutation({
    mutationFn: (path: string) => sendJson<Settings>('/api/settings', 'PUT', { dungeon_checkout: path }),
    onSuccess: async () => { setCheckout(null); await client.invalidateQueries({ queryKey: ['worlds'] }) },
  })
  const shownCheckout = checkout ?? listing.data?.checkout ?? ''
  return (
    <div className="picker">
      <section>
        <h3>Dungeon checkout</h3>
        <form onSubmit={(event) => { event.preventDefault(); saveCheckout.mutate(shownCheckout) }}>
          <input aria-label="Dungeon checkout folder" placeholder="Z:\Coding Projects\prosperos-dungeon"
            value={shownCheckout} onChange={(event) => setCheckout(event.target.value)} />
          <button type="submit" disabled={saveCheckout.isPending}>Save</button>
        </form>
        {saveCheckout.isError && <p className="error">{saveCheckout.error.message}</p>}
        {listing.data?.checkout_problem && <p className="error">{listing.data.checkout_problem}</p>}
      </section>
      {!!listing.data?.builtin.length && (
        <section>
          <h3>Built-in worlds</h3>
          <ul className="choices">
            {listing.data.builtin.map((world) => (
              <li key={world.id}>
                <button type="button" disabled={busy} onClick={() => onOpen({ builtin: world.id })}>
                  <strong>{world.name}</strong>
                  {world.genre && <span className="muted">{world.genre}</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h3>World folder</h3>
        <form onSubmit={(event) => { event.preventDefault(); if (folder.trim()) onOpen({ folder: folder.trim() }) }}>
          <input aria-label="World folder" placeholder="A folder with a world.json" value={folder}
            onChange={(event) => setFolder(event.target.value)} />
          <button type="submit" disabled={busy}><FolderOpen size={14} aria-hidden /> Open</button>
        </form>
        {!!listing.data?.recent.length && (
          <ul className="choices">
            {listing.data.recent.map((item) => (
              <li key={item.folder}>
                <button type="button" disabled={busy} onClick={() => onOpen({ folder: item.folder })}>
                  <strong>{item.name}</strong><span className="muted path">{item.folder}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <ImportPackage onOpened={(path) => onOpen({ folder: path })} />
    </div>
  )
}
