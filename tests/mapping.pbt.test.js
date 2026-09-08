// Property-based tests for the pure device-line -> action mapping (serial.js).
// Covers PBT-02 (totality), PBT-03 (purity/determinism), PBT-07 (table consistency).
const test = require('node:test');
const assert = require('node:assert/strict');
const fc = require('fast-check');
const { parseDeviceLine } = require('../serial.js');

const ACTIONS = new Set(['yes', 'no', 'stop', 'confirm', 'nav_up', 'nav_down']);
const BUTTON = { '0': 'yes', '1': 'no', '2': 'stop', '8': 'confirm' };
const ENCODER = { CW: 'nav_down', VDN: 'nav_down', CCW: 'nav_up', VUP: 'nav_up' };
const upperToken = fc.array(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')), { minLength: 1, maxLength: 6 }).map(chars => chars.join(''));

test('PBT-02 totality: any input yields null or a valid action, never throws', () => {
  fc.assert(fc.property(fc.oneof(fc.string(), fc.anything()), (input) => {
    const result = parseDeviceLine(input);
    assert.ok(result === null || ACTIONS.has(result));
  }));
});

test('PBT-03 purity: the same line always maps to the same result', () => {
  fc.assert(fc.property(fc.string(), (line) => {
    assert.equal(parseDeviceLine(line), parseDeviceLine(line));
  }));
});

test('PBT-07 consistency: BTN:<0-8> lines agree with the button table', () => {
  fc.assert(fc.property(fc.integer({ min: 0, max: 8 }), (digit) => {
    assert.equal(parseDeviceLine(`BTN:${digit}`), BUTTON[String(digit)] ?? null);
  }));
});

test('PBT-07 consistency: ENC:<TOKEN> lines agree with the encoder table', () => {
  fc.assert(fc.property(upperToken, (token) => {
    assert.equal(parseDeviceLine(`ENC:${token}`), ENCODER[token] ?? null);
  }));
});

test('PBT-07 anything not matching the exact framing never maps to an action', () => {
  fc.assert(fc.property(fc.string(), (line) => {
    const framed = /^BTN:[0-8]$/.test(line) || /^ENC:[A-Z]+$/.test(line);
    if (!framed) assert.equal(parseDeviceLine(line), null);
  }));
});
