import { fit } from './fit'

// same table as engine/tests/discover/test_quick.py::test_fit
describe('fit', () => {
  it.each([
    [[128, '8A'], [128, '8A'], 'encaja'],
    [[128, '8A'], [64, '9A'], 'encaja'],
    [[128, '8A'], [140, '8A'], 'cerca'],
    [[128, '8A'], [128, '3B'], 'cerca'],
    [[128, '8A'], [100, '3B'], null],
    [[null, null], [128, '8A'], null],
    [[128, null], [121, null], 'cerca'],
    [[128, '8A'], [null, null], null],
    [[128, '8A'], [256, '8B'], 'encaja']
  ] as const)('%j vs %j → %s', (ref, cand, expected) => {
    expect(fit(ref[0], ref[1], cand[0], cand[1])).toBe(expected)
  })
})
