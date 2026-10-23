import assert from 'node:assert/strict'

import { test } from 'vitest'

import { hasWindowsPathPrefix, isExternalVenvHolder, isClawksisOwnedVenvDaemon } from './venv-holder-select'

const SCRIPTS = 'C:\\Clawksis\\venv\\Scripts'

test('matches the hindsight daemon shim (exe under venv Scripts + hindsight cmdline)', () => {
  assert.equal(
    isClawksisOwnedVenvDaemon(
      'C:\\Clawksis\\venv\\Scripts\\pythonw.exe',
      'C:\\Clawksis\\venv\\Scripts\\pythonw.exe -m hindsight_api.main --daemon --idle-timeout 300 --port 9177',
      SCRIPTS
    ),
    true
  )
})

test('Windows path prefix match is ordinal case-insensitive', () => {
  assert.equal(
    isClawksisOwnedVenvDaemon(
      'c:\\clawk\\venv\\scripts\\python.exe',
      'python.exe -m hindsight_api.main --daemon',
      'C:\\Clawksis\\venv\\Scripts'
    ),
    true
  )
})

test('excludes external venv holders that are not the hindsight daemon', () => {
  // a user terminal running the clawk CLI from the venv — must NOT be killed
  assert.equal(isClawksisOwnedVenvDaemon('C:\\Clawksis\\venv\\Scripts\\clawk.exe', 'clawk chat -q "hi"', SCRIPTS), false)
  // an unrelated python script using the venv interpreter
  assert.equal(
    isClawksisOwnedVenvDaemon('C:\\Clawksis\\venv\\Scripts\\python.exe', 'python C:\\tools\\import.py', SCRIPTS),
    false
  )
})

test('excludes exes outside the venv even when the cmdline mentions hindsight', () => {
  assert.equal(
    isClawksisOwnedVenvDaemon('C:\\Other\\pythonw.exe', 'pythonw -m hindsight_api.main --daemon', SCRIPTS),
    false
  )
})

test('prefix boundary: sibling dirs (ScriptsX) do not match', () => {
  assert.equal(hasWindowsPathPrefix('C:\\Clawksis\\venv\\ScriptsX\\python.exe', SCRIPTS), false)
  assert.equal(hasWindowsPathPrefix('C:\\Clawksis\\venv\\Scripts\\python.exe', SCRIPTS), true)
})

test('null/undefined fields never match', () => {
  assert.equal(isClawksisOwnedVenvDaemon(null, 'x', SCRIPTS), false)
  assert.equal(isClawksisOwnedVenvDaemon('C:\\Clawksis\\venv\\Scripts\\pythonw.exe', null, SCRIPTS), false)
  assert.equal(isClawksisOwnedVenvDaemon(undefined, undefined, SCRIPTS), false)
})

// --- isExternalVenvHolder (#62311) ------------------------------------------

test('matches the autostart gateway shim (clawk.exe under venv Scripts)', () => {
  assert.equal(
    isExternalVenvHolder(
      'C:\\Clawksis\\venv\\Scripts\\clawk.exe',
      '"C:\\Clawksis\\venv\\Scripts\\clawk.exe" gateway run --external-supervisor',
      SCRIPTS
    ),
    true
  )
})

test('matches the dashboard scheduled task (python -m clawk_cli / -m clawk)', () => {
  assert.equal(
    isExternalVenvHolder(
      'C:\\Clawksis\\venv\\Scripts\\python.exe',
      '"C:\\Clawksis\\venv\\Scripts\\python.exe" -m clawk_cli.main dashboard',
      SCRIPTS
    ),
    true
  )
  assert.equal(
    isExternalVenvHolder('C:\\Clawksis\\venv\\Scripts\\pythonw.exe', 'pythonw.exe -m clawk serve', SCRIPTS),
    true
  )
})

test('never matches an unrelated process that merely borrows the venv interpreter', () => {
  // a user's own script running on the venv python — NOT Clawksis, must NOT be killed
  assert.equal(
    isExternalVenvHolder('C:\\Clawksis\\venv\\Scripts\\python.exe', 'python C:\\tools\\import.py', SCRIPTS),
    false
  )
  // hindsight daemon is selected by isClawksisOwnedVenvDaemon, not here
  assert.equal(
    isExternalVenvHolder('C:\\Clawksis\\venv\\Scripts\\pythonw.exe', 'pythonw -m hindsight_api.main --daemon', SCRIPTS),
    false
  )
})

test('never matches a process outside the venv, even with clawk in the cmdline', () => {
  // an editor / shell whose command line mentions the install root (#62445 regression guard)
  assert.equal(
    isExternalVenvHolder('C:\\Windows\\System32\\cmd.exe', 'cmd /c cd C:\\Clawksis\\venv\\Scripts && dir', SCRIPTS),
    false
  )
  assert.equal(isExternalVenvHolder('C:\\Other\\clawk.exe', 'clawk gateway run', SCRIPTS), false)
})

test('sibling-dir and boundary safety for the external selector', () => {
  assert.equal(isExternalVenvHolder('C:\\Clawksis\\venv\\ScriptsX\\clawk.exe', 'clawk gateway run', SCRIPTS), false)
  assert.equal(isExternalVenvHolder(null, 'clawk gateway run', SCRIPTS), false)
  assert.equal(isExternalVenvHolder('C:\\Clawksis\\venv\\Scripts\\clawk.exe', null, SCRIPTS), false)
})
