import type { Usage } from '@clawk/shared/gateway-events'

export { usageFromTick } from '@clawk/shared/usage-tick'

export const ZERO: Usage = { calls: 0, input: 0, output: 0, total: 0 }
