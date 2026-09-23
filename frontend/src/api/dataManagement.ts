import type {
  BackupList,
  BackupRecord,
  ConfirmationToken,
  DataAction,
  DataExport,
  DeleteAllResult,
  LocalDataStatus,
  RestoreResult,
} from '../types/dataManagement'

const localActionHeaders = {
  'Content-Type': 'application/json',
  'X-PFA-Local-Action': 'confirm',
}

async function errorMessage(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as
    | { detail?: { message?: string } }
    | null
  return body?.detail?.message || `请求失败（HTTP ${response.status}）`
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await errorMessage(response))
  return response.json() as Promise<T>
}

export async function fetchLocalDataStatus(): Promise<LocalDataStatus> {
  return parseResponse<LocalDataStatus>(await fetch('/api/v1/data/status'))
}

export async function fetchBackups(): Promise<BackupList> {
  return parseResponse<BackupList>(await fetch('/api/v1/data/backups'))
}

export async function requestConfirmation(
  action: DataAction,
  confirmationText: string,
  targetId?: string,
): Promise<ConfirmationToken> {
  return parseResponse<ConfirmationToken>(await fetch('/api/v1/data/confirmations', {
    method: 'POST',
    headers: localActionHeaders,
    body: JSON.stringify({
      action,
      confirmation_text: confirmationText,
      ...(targetId ? { target_id: targetId } : {}),
    }),
  }))
}

export async function createBackup(confirmationToken: string): Promise<BackupRecord> {
  return parseResponse<BackupRecord>(await fetch('/api/v1/data/backups', {
    method: 'POST',
    headers: localActionHeaders,
    body: JSON.stringify({ confirmation_token: confirmationToken }),
  }))
}

export async function restoreBackup(
  backupId: string,
  confirmationToken: string,
): Promise<RestoreResult> {
  return parseResponse<RestoreResult>(await fetch(`/api/v1/data/backups/${backupId}/restore`, {
    method: 'POST',
    headers: localActionHeaders,
    body: JSON.stringify({ confirmation_token: confirmationToken }),
  }))
}

export async function exportData(confirmationToken: string): Promise<DataExport> {
  const response = await fetch('/api/v1/data/exports', {
    method: 'POST',
    headers: localActionHeaders,
    body: JSON.stringify({ confirmation_token: confirmationToken }),
  })
  if (!response.ok) throw new Error(await errorMessage(response))
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  return {
    blob: await response.blob(),
    filename: match?.[1] || 'personal-finance-export.zip',
  }
}

export async function deleteAllData(confirmationToken: string): Promise<DeleteAllResult> {
  return parseResponse<DeleteAllResult>(await fetch('/api/v1/data/delete-all', {
    method: 'POST',
    headers: localActionHeaders,
    body: JSON.stringify({ confirmation_token: confirmationToken }),
  }))
}
