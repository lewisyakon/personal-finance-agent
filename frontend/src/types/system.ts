export interface ComponentStatus {
  available: boolean
  message: string
}

export interface SystemStatus {
  app: ComponentStatus
  database: ComponentStatus
  model: ComponentStatus
}

