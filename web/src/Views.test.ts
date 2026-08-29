import { describe, expect, it } from 'vitest'

import type { Account } from './api/client'
import { resolveMailboxSelection } from './mailboxSelection'

function account(id: string, groupId: string | null): Account {
  return {
    id,
    email: `${id}@outlook.com`,
    provider: 'outlook',
    account_type: 'outlook',
    lifecycle_status: 'active',
    authorization_status: 'valid',
    token_status: 'valid',
    mail_health_status: 'healthy',
    proxy_health_status: 'healthy',
    group_id: groupId,
    health_reason_code: null,
    health_error_summary: null,
    consecutive_failures: 0,
    last_mail_check_at: null,
    last_mail_success_at: null,
    row_version: 1,
  }
}

describe('resolveMailboxSelection', () => {
  const accounts = [account('first', null), account('grouped', 'group-1')]

  it('keeps a selected mailbox that remains in scope', () => {
    expect(resolveMailboxSelection(accounts, 'grouped', 'group-1')).toBe('grouped')
  })

  it('replaces a mailbox that disappeared from the loaded pages', () => {
    expect(resolveMailboxSelection(accounts, 'missing', '')).toBe('first')
  })

  it('clears the selection when the chosen group has no loaded mailbox', () => {
    expect(resolveMailboxSelection(accounts, 'first', 'empty-group')).toBe('')
  })
})
