import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'

function Placeholder() {
  const [status, setStatus] = useState('Conectando…')
  useEffect(() => {
    window.oneforall
      .getEngine()
      .then(({ baseUrl, token }) => fetch(`${baseUrl}/health`, { headers: { 'X-Token': token } }))
      .then((r) => r.json())
      .then((j) => setStatus(j.ok ? 'Motor OK' : 'Motor sin respuesta'))
      .catch((e) => setStatus(`Error: ${e}`))
  }, [])
  return <p style={{ color: 'white', font: '16px system-ui', padding: 48 }}>{status}</p>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Placeholder />
  </StrictMode>
)
