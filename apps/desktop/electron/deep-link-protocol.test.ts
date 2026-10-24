import assert from 'node:assert/strict'

import { test } from 'vitest'

import { registerDeepLinkProtocol } from './deep-link-protocol'

function run(env: NodeJS.ProcessEnv, defaultApp = true) {
  const calls: unknown[][] = []
  const log: string[] = []
  registerDeepLinkProtocol({
    app: {
      setAsDefaultProtocolClient: (...args: unknown[]) => {
        calls.push(args)

        return true
      }
    },
    protocol: 'clawk',
    env,
    defaultApp,
    argv: ['/electron', '.'],
    execPath: '/electron',
    resolve: entry => `/checkout/${entry}`,
    log: line => log.push(line)
  })

  return { calls, log }
}

test('the E2E/dev guard leaves the OS clawk:// handler untouched; normal launches still register', () => {
  const skipped = run({ CLAWK_DESKTOP_SKIP_PROTOCOL_REGISTRATION: '1' })
  assert.deepEqual(skipped.calls, [])
  assert.match(skipped.log.join('\n'), /registration skipped/)

  assert.deepEqual(run({}).calls, [['clawk', '/electron', ['/checkout/.']]])
  assert.deepEqual(run({}, false).calls, [['clawk']])
})
