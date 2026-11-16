import {describe, expect, it} from 'vitest';
import {readPack, slug, summarize} from './CareerBirth';

describe('role pack helpers', () => {
  it('builds stable ids from job titles', () => {
    expect(slug('Chief of Staff')).toBe('chief-of-staff');
    expect(slug('  UI/UX Specialist ')).toBe('ui-ux-specialist');
  });
  it('reads a bare list or an exported pack', () => {
    expect(readPack('[{"id":"editor"}]')).toHaveLength(1);
    expect(readPack('{"format":"funkbot-role-pack","presets":[{"id":"a"},{"id":"b"}]}')).toHaveLength(2);
  });
  it('reads the Employee DNA interchange pack (roles list)', () => {
    expect(readPack('{"format":"pack","roles":[{"id":"funk-role-01-editor"}]}')).toHaveLength(1);
  });
  it('rejects files without presets', () => {
    expect(() => readPack('{"roles":[]}')).toThrow(/no role presets/);
    expect(() => readPack('[]')).toThrow(/no role presets/);
    expect(() => readPack('not json')).toThrow(SyntaxError);
  });
  it('summarizes import outcomes without hiding skipped or invalid presets', () => {
    expect(summarize([{id:'a',outcome:'created'},{id:'b',outcome:'created'},{id:'c',outcome:'skipped_customized'},{id:null,outcome:'invalid',detail:'x'}]))
      .toBe('2 added · 1 kept (your edits) · 1 invalid');
    expect(summarize([])).toBe('Nothing to import.');
  });
});
