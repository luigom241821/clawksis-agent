/**
 * CLAWK_PYTHON for the electron contracts that drive real clawk_cli / pm code
 * (mac-sign, source-backend, checkout-source). CI exports the PM test
 * environment's interpreter; a developer's plain `npx vitest` does not, and the
 * PATH python3 lacks the application dependencies. Resolve the checkout's test
 * interpreter the way scripts/run_tests.sh does. Workers inherit process.env.
 */
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const repo = path.resolve(import.meta.dirname, '../..')

export default function setup(): void {
  if (process.env.CLAWK_PYTHON || process.platform === 'win32') {
    return
  }

  try {
    const python = execFileSync(
      'bash',
      [path.join(repo, 'scripts', 'run-in-clawk-env'), 'sh', '-c', 'printf %s "$__CLAWK_TEST_PYTHON"'],
      { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] }
    )

    if (python) {
      process.env.CLAWK_PYTHON = python
    }
  } catch (error: unknown) {
    // Electron tests that need no Python still run; only the contracts above fail, naming CLAWK_PYTHON.
    console.warn(`vitest: could not resolve the Clawksis test interpreter: ${String(error)}`)
  }
}
