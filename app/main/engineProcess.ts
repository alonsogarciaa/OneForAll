import { spawn, type ChildProcess } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { createInterface } from 'node:readline'

export interface EngineInfo {
  baseUrl: string
  token: string
}

export type EngineState = 'ready' | 'restarting' | 'failed'

export function parsePortLine(line: string): { port: number; token: string } | null {
  try {
    const v = JSON.parse(line.trim())
    if (Number.isInteger(v?.port) && typeof v?.token === 'string' && v.token.length > 0) {
      return { port: v.port, token: v.token }
    }
  } catch {
    // not the ready line
  }
  return null
}

export class RestartPolicy {
  private stamps: number[] = []
  constructor(private maxPerMinute = 3) {}

  shouldRestart(now: number): boolean {
    this.stamps = this.stamps.filter((t) => now - t < 60_000)
    if (this.stamps.length >= this.maxPerMinute) return false
    this.stamps.push(now)
    return true
  }
}

export interface EngineOptions {
  pythonCmd: string[]
  dataRoot?: string
  fake: boolean
  toolsDir?: string
  modelsDir?: string
  cwd?: string
}

const READY_TIMEOUT_MS = 30_000

export class EngineProcess extends EventEmitter {
  private child: ChildProcess | null = null
  private info: Promise<EngineInfo> | null = null
  private stopping = false
  private policy = new RestartPolicy(3)

  constructor(private opts: EngineOptions) {
    super()
  }

  start(): Promise<EngineInfo> {
    this.stopping = false
    this.info = this.spawnOnce()
    return this.info
  }

  current(): Promise<EngineInfo> {
    return this.info ?? this.start()
  }

  /** Manual retry after the engine gave up (state 'failed'). */
  restart(): Promise<EngineInfo> {
    this.policy = new RestartPolicy(3)
    this.killChild()
    return this.start()
  }

  async stop(): Promise<void> {
    this.stopping = true
    const child = this.child
    if (!child || child.exitCode !== null) return
    try {
      const info = await this.info
      if (info) {
        await fetch(`${info.baseUrl}/shutdown`, { method: 'POST', headers: { 'X-Token': info.token } }).catch(() => undefined)
      }
    } catch {
      // engine never became ready
    }
    const exited = new Promise<void>((res) => child.once('exit', () => res()))
    const timeout = new Promise<void>((res) => setTimeout(res, 3000))
    await Promise.race([exited, timeout])
    this.killChild()
  }

  private killChild(): void {
    const child = this.child
    if (!child || child.exitCode !== null || child.pid === undefined) return
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true })
    } else {
      child.kill('SIGKILL')
    }
  }

  private spawnOnce(): Promise<EngineInfo> {
    const [cmd, ...pre] = this.opts.pythonCmd
    const args = [...pre, '--port', '0', '--parent-pid', String(process.pid)]
    if (this.opts.dataRoot) args.push('--data-root', this.opts.dataRoot)
    if (this.opts.fake) args.push('--fake')
    const env = { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' }
    if (this.opts.toolsDir) env.ONEFORALL_TOOLS = this.opts.toolsDir
    if (this.opts.modelsDir) env.ONEFORALL_MODELS = this.opts.modelsDir

    const child = spawn(cmd, args, { cwd: this.opts.cwd, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
    this.child = child
    child.stderr?.on('data', (d) => process.stderr.write(`[engine] ${d}`))

    return new Promise<EngineInfo>((resolve, reject) => {
      let ready = false
      const timer = setTimeout(() => {
        if (!ready) reject(new Error('El motor no respondió a tiempo'))
      }, READY_TIMEOUT_MS)
      createInterface({ input: child.stdout! }).on('line', (line) => {
        if (ready) return
        const parsed = parsePortLine(line)
        if (parsed) {
          ready = true
          clearTimeout(timer)
          resolve({ baseUrl: `http://127.0.0.1:${parsed.port}`, token: parsed.token })
          this.emit('state', 'ready' satisfies EngineState)
        }
      })
      child.once('error', (err) => {
        clearTimeout(timer)
        if (!ready) reject(err)
      })
      child.once('exit', (code) => {
        clearTimeout(timer)
        if (!ready) reject(new Error(`El motor se cerró al arrancar (código ${code})`))
        if (this.child === child && !this.stopping) this.onUnexpectedExit()
      })
    })
  }

  private onUnexpectedExit(): void {
    if (this.policy.shouldRestart(Date.now())) {
      this.emit('state', 'restarting' satisfies EngineState)
      this.info = this.spawnOnce()
      this.info.catch(() => undefined)
    } else {
      this.emit('state', 'failed' satisfies EngineState)
    }
  }
}
