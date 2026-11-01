import { parsePortLine, RestartPolicy } from './engineProcess'

describe('parsePortLine', () => {
  it('reads port and token from the engine ready line', () => {
    expect(parsePortLine('{"port": 51234, "token": "abcDEF_123-xyz"}')).toEqual({ port: 51234, token: 'abcDEF_123-xyz' })
  })
  it('ignores other output', () => {
    expect(parsePortLine('INFO started')).toBeNull()
    expect(parsePortLine('{"port": "x"}')).toBeNull()
    expect(parsePortLine('{"port": 5}')).toBeNull()
  })
})

describe('RestartPolicy', () => {
  it('allows 3 restarts per minute, refuses the 4th, allows again later', () => {
    const p = new RestartPolicy(3)
    expect(p.shouldRestart(0)).toBe(true)
    expect(p.shouldRestart(1000)).toBe(true)
    expect(p.shouldRestart(2000)).toBe(true)
    expect(p.shouldRestart(3000)).toBe(false)
    expect(p.shouldRestart(61_000)).toBe(true)
  })
})
