import type { SystemStatus } from '../types/system'

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const response = await fetch('/api/v1/system/status')
  if (!response.ok) {
    throw new Error(`状态接口失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<SystemStatus>
}

