import type { Account } from './api/client'

export function resolveMailboxSelection(accounts: Account[], currentId: string, groupId: string): string {
  const selected = accounts.find((account) => account.id === currentId)
  if (selected && (!groupId || selected.group_id === groupId)) return currentId
  return accounts.find((account) => !groupId || account.group_id === groupId)?.id ?? ''
}
