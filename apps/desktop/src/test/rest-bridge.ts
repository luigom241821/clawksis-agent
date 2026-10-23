import { vi } from 'vitest'

import type { ClawksisApiRequest } from '@/global'

/** Install a fake `window.clawkDesktop.api`, the preload bridge every REST helper sends through. */
export function installRestBridge(answer: (request: ClawksisApiRequest) => object) {
  const api = vi.fn(async (request: ClawksisApiRequest) => answer(request))

  Object.defineProperty(window, 'clawkDesktop', { configurable: true, value: { api } })

  return api
}
