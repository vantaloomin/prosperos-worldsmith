import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Download, FileDown, FileUp } from 'lucide-react'
import { sendJson, type WorldOverview, type WorldRef } from './api'

interface Exported { path: string; name: string; engine: number; documents: number; assets: number; size: number }

/** The open world written as one .sqlite package: to share, or (an own world) installed straight into Dungeon. */
export function ExportPackage({ world }: { world: WorldRef }) {
  const [to, setTo] = useState('')
  const exported = useMutation({ mutationFn: () => sendJson<Exported>('/api/worlds/export', 'POST', { ...world, to: to.trim() || null }) })
  const installed = useMutation({ mutationFn: () => sendJson<Exported>('/api/worlds/install', 'POST', world) })
  const own = 'folder' in world
  return (
    <section className="package">
      <h3>World package</h3>
      {own ? (
        <>
          <p className="muted small">Install puts the whole world (entries, documents, art and town data) into Dungeon as one package. It shows under Worlds &gt; World packages next time Dungeon lists them. Installing again replaces it.</p>
          <div className="row tight">
            <button type="button" disabled={installed.isPending} onClick={() => installed.mutate()}><Download size={14} aria-hidden /> {installed.isPending ? 'Installing…' : 'Install into Dungeon'}</button>
          </div>
          {installed.isError && <p className="error" role="alert">{installed.error.message}</p>}
          {installed.data && <p className="ok">Installed {installed.data.name} as <code>{installed.data.path}</code>.</p>}
        </>
      ) : (
        <p className="muted small">This is a built-in world, so your saves are already in the Dungeon checkout and ship with a Dungeon pull request. You can still write it out as one file to share.</p>
      )}
      <form onSubmit={(event) => { event.preventDefault(); exported.mutate() }}>
        <input aria-label="Export to" placeholder="Folder or file to write the .sqlite to (empty: Worldsmith's exports folder)" value={to} onChange={(event) => setTo(event.target.value)} />
        <button type="submit" disabled={exported.isPending}><FileDown size={14} aria-hidden /> {exported.isPending ? 'Writing…' : 'Export .sqlite'}</button>
      </form>
      {exported.isError && <p className="error" role="alert">{exported.error.message}</p>}
      {exported.data && (
        <p className="ok">Wrote {exported.data.name} to <code>{exported.data.path}</code> ({Math.ceil(exported.data.size / 1024)} KB, {exported.data.engine} town and map files).</p>
      )}
    </section>
  )
}

/** A .sqlite package turned back into a world folder, then opened. */
export function ImportPackage({ onOpened }: { onOpened: (folder: string) => void }) {
  const [file, setFile] = useState('')
  const [folder, setFolder] = useState('')
  const imported = useMutation({
    mutationFn: () => sendJson<{ folder: string; world: WorldOverview }>('/api/worlds/import', 'POST', { package: file.trim(), folder: folder.trim() }),
    onSuccess: (done) => onOpened(done.folder),
  })
  return (
    <section>
      <h3>World package</h3>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); if (file.trim() && folder.trim()) imported.mutate() }}>
        <input aria-label="Package file" placeholder="A world package (.sqlite)" value={file} onChange={(event) => setFile(event.target.value)} />
        <input aria-label="New world folder" placeholder="An empty or new folder to unpack it into" value={folder} onChange={(event) => setFolder(event.target.value)} />
        <button type="submit" disabled={imported.isPending}><FileUp size={14} aria-hidden /> Unpack and open</button>
      </form>
      {imported.isError && <p className="error" role="alert">{imported.error.message}</p>}
    </section>
  )
}
