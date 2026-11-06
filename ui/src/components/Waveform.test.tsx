import { fireEvent, render, screen } from '@testing-library/react'
import { Waveform } from './Waveform'

const data = { peaks: [0, 1], low: [0, 1], mid: [0, 0], high: [0, 0] }

function setup(snap?: number[], loop: { start: number; end: number } | null = null) {
  const onSeek = vi.fn()
  const onLoop = vi.fn()
  render(<Waveform data={data} beats={[]} duration={100} position={0} onSeek={onSeek} loop={loop} onLoop={onLoop} snap={snap} />)
  const el = screen.getByRole('slider')
  el.getBoundingClientRect = () => ({ left: 0, width: 1000, top: 0, height: 80, right: 1000, bottom: 80, x: 0, y: 0, toJSON() {} })
  return { el, onSeek, onLoop }
}

describe('Waveform loop drag', () => {
  it('a tiny drag is a seek, never a zero-length loop', () => {
    const { el, onSeek, onLoop } = setup()
    fireEvent.mouseDown(el, { clientX: 100 })
    fireEvent.mouseUp(window, { clientX: 101 })
    expect(onSeek).toHaveBeenCalledWith(10.1)
    expect(onLoop).not.toHaveBeenCalled()
  })

  it('a drag marks a loop snapped to the nearest beats', () => {
    const { el, onSeek, onLoop } = setup([9.8, 10.3, 13.9, 14.4])
    fireEvent.mouseDown(el, { clientX: 140 })
    fireEvent.mouseUp(window, { clientX: 100 })
    expect(onLoop).toHaveBeenCalledWith(9.8, 13.9)
    expect(onSeek).not.toHaveBeenCalled()
  })

  it('Alt disables snapping', () => {
    const { el, onLoop } = setup([9.8, 13.9])
    fireEvent.mouseDown(el, { clientX: 100 })
    fireEvent.mouseUp(window, { clientX: 140, altKey: true })
    expect(onLoop).toHaveBeenCalledWith(10, 14)
  })

  it('a drag released outside the wave still counts', () => {
    const { el, onLoop } = setup()
    fireEvent.mouseDown(el, { clientX: 100 })
    fireEvent.mouseUp(window, { clientX: 1200 })
    expect(onLoop).toHaveBeenCalledWith(10, 100)
  })

  it('a drag inside one beat (both edges snap to the same beat) is a seek', () => {
    const { el, onSeek, onLoop } = setup([10, 20])
    fireEvent.mouseDown(el, { clientX: 106 })
    fireEvent.mouseUp(window, { clientX: 114 })
    expect(onLoop).not.toHaveBeenCalled()
    expect(onSeek).toHaveBeenCalledWith(11.4)
  })

  it('a click next to a loop edge is a seek', () => {
    const { el, onSeek, onLoop } = setup(undefined, { start: 10, end: 20 })
    fireEvent.mouseDown(el, { clientX: 102 })
    fireEvent.mouseUp(window, { clientX: 102 })
    expect(onSeek).toHaveBeenCalledWith(10.2)
    expect(onLoop).not.toHaveBeenCalled()
  })

  it('dragging a loop edge moves only that edge', () => {
    const { el, onLoop } = setup(undefined, { start: 10, end: 20 })
    fireEvent.mouseDown(el, { clientX: 200 })
    fireEvent.mouseUp(window, { clientX: 300 })
    expect(onLoop).toHaveBeenCalledWith(10, 30)
  })
})
