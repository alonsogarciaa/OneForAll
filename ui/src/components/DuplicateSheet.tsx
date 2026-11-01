import { GlassSheet } from './GlassSheet'
import type { TrackRecord } from '../lib/types'

interface Props {
  track: TrackRecord
  onForce(): void
  onClose(): void
}

export function DuplicateSheet({ track, onForce, onClose }: Props) {
  return (
    <GlassSheet
      title="Ya tienes esta canción"
      onClose={onClose}
      actions={
        <>
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn" onClick={() => window.oneforall.showInFolder(track.path)}>
            Abrir ubicación
          </button>
          <button className="btn btn-primary" onClick={onForce}>
            Descargar igualmente
          </button>
        </>
      }
    >
      <p className="sheet-text">
        «{track.title}» ya está en tu biblioteca. Si la descargas otra vez se guardará como una copia numerada en la misma carpeta.
      </p>
      <p className="sheet-path">{track.path}</p>
    </GlassSheet>
  )
}
