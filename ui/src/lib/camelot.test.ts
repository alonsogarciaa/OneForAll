import { camelotColor, compatLabel, contrastRatio, displayKey, CAMELOT_CODES } from './camelot'

describe('camelot', () => {
  it('shows camelot plus the Spanish musical name', () => {
    expect(displayKey('11A')).toBe('11A · Fa#m')
    expect(displayKey('8B')).toBe('8B · Do')
    expect(displayKey('8A')).toBe('8A · Lam')
    expect(displayKey('1A')).toBe('1A · Sol#m')
    expect(displayKey(null)).toBe('—')
  })
  it('lists the 24 codes', () => {
    expect(CAMELOT_CODES).toHaveLength(24)
  })
  it('keeps white text readable on every key colour', () => {
    for (const code of CAMELOT_CODES) expect(contrastRatio(camelotColor(code), '#ffffff')).toBeGreaterThanOrEqual(4.5)
  })
  it('labels compatibility levels', () => {
    expect(compatLabel('same')).toBe('Misma clave')
    expect(compatLabel('adjacent')).toBe('±1')
    expect(compatLabel('relative')).toBe('Relativa')
  })
})
