import { useEffect, useRef, useState } from "react"
import { getPreparedInput } from "./api"

type ViewerState =
  | { status: "loading"; incidentId: string; request: number }
  | { status: "error"; incidentId: string; request: number; message: string }
  | { status: "loaded"; incidentId: string; request: number; raw: string; pretty: string }

export default function PreparedJsonViewer({ incidentId, onClose }: { incidentId: string; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [state, setState] = useState<ViewerState>({ status: "loading", incidentId, request: 0 })
  const [copyMessage, setCopyMessage] = useState("")
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  useEffect(() => {
    let active = true
    getPreparedInput(incidentId).then((raw) => {
      const pretty = JSON.stringify(JSON.parse(raw), null, 2)
      if (active) setState({ status: "loaded", incidentId, request: retry, raw, pretty })
    }).catch((failure: unknown) => {
      if (active) setState({ status: "error", incidentId, request: retry, message: failure instanceof Error ? failure.message : "Unable to load prepared JSON" })
    })
    return () => { active = false }
  }, [incidentId, retry])

  const shownState: ViewerState = state.incidentId === incidentId && state.request === retry
    ? state : { status: "loading", incidentId, request: retry }

  async function copyJson() {
    if (shownState.status !== "loaded") return
    try {
      await navigator.clipboard.writeText(shownState.raw)
      setCopyMessage("Copied")
    } catch {
      setCopyMessage("Could not copy JSON")
    }
  }

  return <dialog ref={dialogRef} className="prepared-json-dialog" aria-labelledby="prepared-json-title" onClose={onClose} onCancel={onClose}>
    <div className="prepared-json-shell">
      <header className="prepared-json-header">
        <div>
          <h2 id="prepared-json-title">Prepared canonical JSON</h2>
          <p>{incidentId}</p>
        </div>
        <button type="button" className="prepared-json-close" onClick={() => dialogRef.current?.close()} aria-label="Close prepared JSON">×</button>
      </header>
      <div className="prepared-json-actions">
        {shownState.status === "loaded" && <button type="button" onClick={copyJson}>Copy JSON</button>}
        {shownState.status === "error" && <button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button>}
        {copyMessage && <span role="status">{copyMessage}</span>}
      </div>
      {shownState.status === "loading" && <p className="prepared-json-message" role="status">Loading prepared JSON…</p>}
      {shownState.status === "error" && <p className="prepared-json-message" role="alert">Unable to load prepared JSON: {shownState.message}</p>}
      {shownState.status === "loaded" && <pre className="prepared-json-body"><code>{shownState.pretty}</code></pre>}
    </div>
  </dialog>
}
