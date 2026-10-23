import { describe, expect, it } from 'vitest'

import {
  normalizeClawksisOpenString,
  pathFromClawksisDeepLink,
  pathFromOpenDeepLink,
  resolveClawksisOpenPath
} from './clawk-open-target'

describe('normalizeClawksisOpenString', () => {
  it('accepts hash-router paths and strips a leading hash', () => {
    expect(normalizeClawksisOpenString('/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeClawksisOpenString('#/index-network/intent/1')).toBe('/index-network/intent/1')
  })

  it('maps plugin-scoped clawk:// deep links to the same path', () => {
    expect(normalizeClawksisOpenString('clawk://index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeClawksisOpenString('clawk://index-network/intent/1?focus=true')).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('maps clawk://open/… deep links by stripping the open host', () => {
    expect(normalizeClawksisOpenString('clawk://open/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeClawksisOpenString('clawk://open/settings/plugins')).toBe('/settings/plugins')
  })

  it('rejects reserved clawk kinds and unsafe paths', () => {
    expect(normalizeClawksisOpenString('clawk://blueprint/morning-brief')).toBeNull()
    expect(normalizeClawksisOpenString('clawk://plugin/install')).toBeNull()
    expect(normalizeClawksisOpenString('https://example.com/x')).toBeNull()
    expect(normalizeClawksisOpenString('/../etc/passwd')).toBeNull()
    expect(normalizeClawksisOpenString('index-network')).toBeNull()
  })
})

describe('resolveClawksisOpenPath', () => {
  it('merges structured path + params', () => {
    expect(resolveClawksisOpenPath({ path: '/index-network/intent/1', params: { focus: 'true' } })).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('resolves href the same as a bare string', () => {
    expect(resolveClawksisOpenPath({ href: 'clawk://index-network/intent/1' })).toBe('/index-network/intent/1')
  })
})

describe('pathFromClawksisDeepLink', () => {
  it('builds the navigate path from a plugin-scoped deep-link payload', () => {
    expect(pathFromClawksisDeepLink('index-network', 'intent/1')).toBe('/index-network/intent/1')
  })

  it('builds the navigate path from clawk://open/… payloads', () => {
    expect(pathFromOpenDeepLink('index-network/intent/1')).toBe('/index-network/intent/1')
    expect(pathFromClawksisDeepLink('open', 'agent/42')).toBe('/agent/42')
  })

  it('ignores reserved kinds', () => {
    expect(pathFromClawksisDeepLink('blueprint', 'morning-brief')).toBeNull()
    expect(pathFromClawksisDeepLink('plugin', 'install')).toBeNull()
  })
})
