// This thin client is the bootstrap boundary. `pnpm generate:api` writes the
// generated OpenAPI client beside it; application code must not call fetch
// outside this module.

export type StatusCount = { status: string; count: number }

export type FleetSummary = {
  total_accounts: number
  active_accounts: number
  needs_attention: number
  lifecycle: StatusCount[]
  authorization: StatusCount[]
  token: StatusCount[]
  mail_health: StatusCount[]
  proxy_health: StatusCount[]
}

export type AccountViewFilters = {
  lifecycle_statuses?: string[]
  authorization_statuses?: string[]
  token_statuses?: string[]
  mail_health_statuses?: string[]
  proxy_health_statuses?: string[]
  group_id?: string | null
  ungrouped?: boolean
  untagged?: boolean
  min_consecutive_failures?: number | null
  last_mail_success_before?: string | null
  query?: string | null
}

export type BuiltinAccountView = {
  key: string
  name: string
  description: string
  filters: AccountViewFilters
}

export type SavedAccountView = {
  id: string
  name: string
  filters: AccountViewFilters
  sort_order: number
}

export type AccountViews = {
  builtin: BuiltinAccountView[]
  saved: SavedAccountView[]
}

export type ApiToken = {
  id: string
  name: string
  token_prefix: string
  scopes: string[]
  expires_at: string | null
  revoked_at: string | null
  last_used_at: string | null
  created_at: string
}

export type ApiTokenCreated = {
  token: ApiToken
  secret: string
}

export type Account = {
  id: string
  email: string
  provider: string
  account_type: string
  lifecycle_status: string
  authorization_status: string
  token_status: string
  mail_health_status: string
  proxy_health_status: string
  group_id: string | null
  health_reason_code: string | null
  health_error_summary: string | null
  consecutive_failures: number
  last_mail_check_at: string | null
  last_mail_success_at: string | null
  row_version: number
}

export type AccountPage = {
  items: Account[]
  next_cursor: string | null
  limit: number
}

export type AccountBulkPreview = {
  preview_token: string
  scope: string
  matched_count: number
  eligible_count: number
  skipped_count: number
  dangerous_count: number
  expires_at: string
}

export type Job = {
  id: string
  job_type: string
  status: string
  total_count: number
  succeeded_count: number
  failed_count: number
  skipped_count: number
}

export type JobEvent = {
  sequence: number
  event_type: string
  level: string
  message: string
  data: Record<string, unknown>
  created_at: string
}

export type JobEventsPage = {
  items: JobEvent[]
  next_sequence: number | null
}

export type TokenRefreshSummary = {
  total_refreshable: number
  never: number
  success: number
  failed: number
  stale: number
}

export type TokenRefreshLog = {
  id: string
  account_id: string
  job_id: string | null
  status: string
  channel: string | null
  reason_code: string | null
  error_summary: string | null
  rotated: boolean
  created_at: string
}

export type Schedule = {
  id: string
  name: string
  task_type: string
  cron_expression: string
  timezone: string
  enabled: boolean
  payload: Record<string, unknown>
  next_run_at: string
  last_run_at: string | null
  last_job_id: string | null
}

export type ProxyProfile = {
  id: string
  name: string
  enabled: boolean
  primary_hint: string
  fallback_hint_1: string | null
  fallback_hint_2: string | null
  health_status: string
  health_reason_code: string | null
}

export type RetentionStats = {
  account_count: number
  message_count: number
  body_count: number
  estimated_bytes: number
}

export type EmailShare = {
  id: string
  account_id: string
  status: string
  token?: string
  share_path?: string
  expires_at: string | null
}

export type PublicShareStatus = {
  status: string
  account_id: string
  email: string
  allowed_folders: string[]
  expires_at: string | null
}

export type ForwardingDestination = {
  id: string
  name: string
  channel: string
  enabled: boolean
  config: Record<string, unknown>
}

export type WorkProject = {
  id: string
  name: string
  description: string
  status: string
  default_lease_seconds: number
  total_count: number
  to_claim_count: number
  leased_count: number
  done_count: number
  failed_count: number
}

export type ProjectClaim = {
  project_account_id: string
  project_id: string
  account_id: string
  email: string
  claim_token: string
  lease_owner: string
  lease_expires_at: string
  attempt_count: number
}

export type ProjectAccount = {
  id: string
  account_id: string
  email: string
  status: string
  lease_owner: string | null
  lease_expires_at: string | null
  attempt_count: number
  error_summary: string | null
  finished_at: string | null
}

export type ProjectEvent = {
  sequence: number
  event_type: string
  actor: string | null
  data: Record<string, unknown>
  created_at: string
}

export type Group = {
  id: string
  name: string
  description: string
  color: string
  sort_order: number
  level: number
  parent_id: string | null
  system_key: string | null
  direct_account_count: number
  descendant_account_count: number
}

export type Tag = { id: string; name: string; color: string }
export type Alias = { id: string; email: string; created_at: string }

export type ImportItem = {
  id: string
  line_number: number
  status: string
  email: string | null
  error_code: string | null
  error_message: string | null
  created_account_id: string | null
}

export type ImportBatch = {
  id: string
  status: string
  total_count: number
  valid_count: number
  invalid_count: number
  conflict_count: number
  created_count: number
  skipped_count: number
  failed_count: number
  items: ImportItem[]
}

export type MailSummary = {
  id: string
  folder: string
  subject: string
  sender: string
  received_at: string
  is_read: boolean
  has_attachments: boolean
  body_preview: string
  id_mode: string
}

export type MailPage = {
  items: MailSummary[]
  has_more: boolean
  method: string
}

export type MailAttachment = {
  id: string
  name: string
  content_type: string
  size: number
  is_inline: boolean
}

export type MailDetail = {
  id: string
  folder: string
  subject: string
  sender: string
  recipients: string[]
  cc: string[]
  received_at: string
  is_read: boolean
  body: string
  body_type: string
  attachments: MailAttachment[]
  id_mode: string
  method: string
}

export type VerificationCode = {
  account_id: string
  email: string
  code: string
  code_type: 'verification' | 'otp' | 'login' | 'security'
  subject: string
  sender: string
  received_at: string
  folder: string
  message_id: string
  method: string
  confidence: 'high' | 'medium'
}

export type VerificationCodePage = {
  items: VerificationCode[]
  checked_accounts: number
  failed_accounts: number
  partial_errors: Record<string, string>
}

class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

let runtimeToken = sessionStorage.getItem('sem-api-token') ?? ''

export function setApiToken(token: string) {
  runtimeToken = token.trim()
  if (runtimeToken) sessionStorage.setItem('sem-api-token', runtimeToken)
  else sessionStorage.removeItem('sem-api-token')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = runtimeToken || import.meta.env.VITE_SEM_API_TOKEN
  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')
  if (init?.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    const problem = await response.json().catch(() => ({ detail: response.statusText }))
    throw new ApiError(response.status, problem.detail ?? 'API request failed')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function requestBlob(path: string): Promise<Blob> {
  const token = runtimeToken || import.meta.env.VITE_SEM_API_TOKEN
  const headers = new Headers({ Accept: '*/*' })
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(path, { headers })
  if (!response.ok) {
    const problem = await response.json().catch(() => ({ detail: response.statusText }))
    throw new ApiError(response.status, problem.detail ?? 'Download failed')
  }
  return response.blob()
}

export const api = {
  apiTokens: () => request<ApiToken[]>('/api/v1/auth/tokens'),
  createApiToken: (name: string, scopes: string[], expiresInDays: number | null) =>
    request<ApiTokenCreated>('/api/v1/auth/tokens', {
      method: 'POST',
      body: JSON.stringify({ name, scopes, expires_in_days: expiresInDays }),
    }),
  revokeApiToken: (tokenId: string) => request<ApiToken>(`/api/v1/auth/tokens/${tokenId}/revoke`, { method: 'POST' }),
  fleetSummary: () => request<FleetSummary>('/api/v1/fleet/summary'),
  accountViews: () => request<AccountViews>('/api/v1/fleet/views'),
  createAccountView: (name: string, filters: AccountViewFilters, sortOrder = 0) =>
    request<SavedAccountView>('/api/v1/fleet/views', {
      method: 'POST',
      body: JSON.stringify({ name, filters, sort_order: sortOrder }),
    }),
  updateAccountView: (viewId: string, name: string, filters: AccountViewFilters, sortOrder: number) =>
    request<SavedAccountView>(`/api/v1/fleet/views/${viewId}`, {
      method: 'PUT',
      body: JSON.stringify({ name, filters, sort_order: sortOrder }),
    }),
  deleteAccountView: (viewId: string) => request<void>(`/api/v1/fleet/views/${viewId}`, { method: 'DELETE' }),
  accounts: (mailHealth?: string, cursor?: string | null, limit = 100, view?: string, savedViewId?: string) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (mailHealth) params.set('mail_health_status', mailHealth)
    if (cursor) params.set('cursor', cursor)
    if (view) params.set('view', view)
    if (savedViewId) params.set('saved_view_id', savedViewId)
    return request<AccountPage>(`/api/v1/accounts?${params}`)
  },
  bulkAccounts: (
    accountIds: string[],
    lifecycleStatus: string | null,
    groupId: string | null,
  ) =>
    request<{ updated_count: number }>('/api/v1/accounts/bulk/mutations', {
      method: 'POST',
      body: JSON.stringify({
        account_ids: accountIds,
        lifecycle_status: lifecycleStatus,
        move_group: groupId !== null,
        group_id: groupId || null,
      }),
    }),
  previewBulkAccounts: (
    selection: Record<string, unknown>,
    lifecycleStatus: string | null,
    groupId: string | null,
  ) => request<AccountBulkPreview>('/api/v1/accounts/bulk/previews', {
    method: 'POST',
    body: JSON.stringify({
      selection,
      changes: {
        lifecycle_status: lifecycleStatus,
        move_group: groupId !== null,
        group_id: groupId || null,
      },
    }),
  }),
  executeBulkAccounts: (previewToken: string) =>
    request<{ updated_count: number }>('/api/v1/accounts/bulk/executions', {
      method: 'POST',
      body: JSON.stringify({ preview_token: previewToken }),
    }),
  groups: () => request<Group[]>('/api/v1/groups'),
  createGroup: (name: string, parentId?: string) =>
    request<Group>('/api/v1/groups', {
      method: 'POST',
      body: JSON.stringify({ name, parent_id: parentId || null }),
    }),
  updateGroup: (groupId: string, payload: Record<string, unknown>) =>
    request<Group>(`/api/v1/groups/${groupId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteGroup: (groupId: string) => request<void>(`/api/v1/groups/${groupId}`, { method: 'DELETE' }),
  tags: () => request<Tag[]>('/api/v1/tags'),
  createTag: (name: string, color: string) =>
    request<Tag>('/api/v1/tags', {
      method: 'POST',
      body: JSON.stringify({ name, color }),
    }),
  deleteTag: (tagId: string) => request<void>(`/api/v1/tags/${tagId}`, { method: 'DELETE' }),
  accountTags: (accountId: string) => request<Tag[]>(`/api/v1/accounts/${accountId}/tags`),
  replaceAccountTags: (accountId: string, tagIds: string[]) =>
    request<Tag[]>(`/api/v1/accounts/${accountId}/tags`, {
      method: 'PUT',
      body: JSON.stringify({ action: 'replace', tag_ids: tagIds }),
    }),
  accountAliases: (accountId: string) => request<Alias[]>(`/api/v1/accounts/${accountId}/aliases`),
  replaceAccountAliases: (accountId: string, aliases: string[]) =>
    request<Alias[]>(`/api/v1/accounts/${accountId}/aliases`, {
      method: 'PUT',
      body: JSON.stringify({ aliases }),
    }),
  importBatches: () => request<ImportBatch[]>('/api/v1/import-batches'),
  createImportBatch: (content: string, accountType: 'outlook', provider: 'outlook') =>
    request<ImportBatch>('/api/v1/import-batches', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ content, account_type: accountType, provider }),
    }),
  commitImportBatch: (batchId: string) =>
    request<ImportBatch>(`/api/v1/import-batches/${batchId}/commit`, { method: 'POST' }),
  rollbackImportBatch: (batchId: string) =>
    request<ImportBatch>(`/api/v1/import-batches/${batchId}/rollback`, { method: 'POST' }),
  jobs: () => request<Job[]>('/api/v1/jobs?limit=50'),
  jobEvents: (jobId: string) => request<JobEventsPage>(`/api/v1/jobs/${jobId}/events?limit=200`),
  pauseJob: (jobId: string) => request<Job>(`/api/v1/jobs/${jobId}/pause`, { method: 'POST' }),
  resumeJob: (jobId: string) => request<Job>(`/api/v1/jobs/${jobId}/resume`, { method: 'POST' }),
  cancelJob: (jobId: string) => request<Job>(`/api/v1/jobs/${jobId}/cancel`, { method: 'POST' }),
  mail: (accountId: string, folder = 'inbox') =>
    request<MailPage>(`/api/v1/accounts/${accountId}/mail?folder=${folder}&method=auto`),
  verificationCodes: (accountId: string, recentMinutes = 30) =>
    request<VerificationCodePage>(`/api/v1/accounts/${accountId}/verification-codes?recent_minutes=${recentMinutes}&messages_per_account=30&include_junk=true&method=auto`),
  queryVerificationCodes: (accountIds: string[], recentMinutes = 30, accountLimit = 100) =>
    request<VerificationCodePage>('/api/v1/verification-codes/query', {
      method: 'POST',
      body: JSON.stringify({
        account_ids: accountIds,
        recent_minutes: recentMinutes,
        messages_per_account: 30,
        account_limit: accountLimit,
        include_junk: true,
        method: 'auto',
      }),
    }),
  mailDetail: (accountId: string, messageId: string, folder = 'inbox') =>
    request<MailDetail>(
      `/api/v1/accounts/${accountId}/mail/messages/${encodeURIComponent(messageId)}?folder=${folder}&method=auto`,
    ),
  markMailRead: (accountId: string, messageId: string, folder: string) =>
    request<void>(`/api/v1/accounts/${accountId}/mail/messages/${encodeURIComponent(messageId)}/read?folder=${folder}&method=auto`, { method: 'POST' }),
  deleteMail: (accountId: string, messageId: string, folder: string) =>
    request<void>(`/api/v1/accounts/${accountId}/mail/messages/${encodeURIComponent(messageId)}?folder=${folder}&method=auto`, { method: 'DELETE' }),
  rawMail: (accountId: string, messageId: string, folder: string) =>
    requestBlob(`/api/v1/accounts/${accountId}/mail/messages/${encodeURIComponent(messageId)}/raw?folder=${folder}&method=auto`),
  mailAttachment: (accountId: string, messageId: string, attachmentId: string, folder: string) =>
    requestBlob(`/api/v1/accounts/${accountId}/mail/messages/${encodeURIComponent(messageId)}/attachments/${encodeURIComponent(attachmentId)}?folder=${folder}&method=auto`),
  createMetadataHealthCheck: (limit = 100) =>
    request<Job>('/api/v1/health-check-jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ account_ids: [], limit, mode: 'metadata' }),
    }),
  createConnectivityHealthCheck: (accountIds: string[]) =>
    request<Job>('/api/v1/health-check-jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ account_ids: accountIds, limit: Math.max(1, accountIds.length), mode: 'connectivity' }),
    }),
  tokenRefreshSummary: () => request<TokenRefreshSummary>('/api/v1/token-refresh-summary'),
  tokenRefreshLogs: () => request<TokenRefreshLog[]>('/api/v1/token-refresh-logs?limit=100'),
  createTokenRefresh: (failedOnly = false, limit = 500) =>
    request<Job>('/api/v1/token-refresh-jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ account_ids: [], failed_only: failedOnly, limit }),
    }),
  schedules: () => request<Schedule[]>('/api/v1/schedules'),
  createSchedule: (
    name: string,
    cronExpression: string,
    timezone: string,
    taskType: 'token_refresh' | 'retention_sync' | 'forwarding',
  ) =>
    request<Schedule>('/api/v1/schedules', {
      method: 'POST',
      body: JSON.stringify({
        name,
        task_type: taskType,
        cron_expression: cronExpression,
        timezone,
        enabled: true,
        payload: taskType === 'token_refresh'
          ? { account_ids: [], failed_only: false, limit: 500 }
          : { account_ids: [], limit: 500 },
      }),
    }),
  deleteSchedule: async (scheduleId: string) => {
    await request<void>(`/api/v1/schedules/${scheduleId}`, { method: 'DELETE' })
  },
  proxies: () => request<ProxyProfile[]>('/api/v1/proxies'),
  createProxy: (name: string, primaryUrl: string) =>
    request<ProxyProfile>('/api/v1/proxies', {
      method: 'POST',
      body: JSON.stringify({ name, primary_url: primaryUrl, enabled: true }),
    }),
  assignAccountProxy: (accountId: string, proxyProfileId: string | null) =>
    request<void>(`/api/v1/proxies/accounts/${accountId}`, {
      method: 'PUT',
      body: JSON.stringify({ proxy_profile_id: proxyProfileId }),
    }),
  probeProxy: (proxyProfileId: string) =>
    request<{ status: string; reason_code: string }>(`/api/v1/proxies/${proxyProfileId}/probe`, {
      method: 'POST',
    }),
  deleteProxy: (proxyProfileId: string) => request<void>(`/api/v1/proxies/${proxyProfileId}`, { method: 'DELETE' }),
  retentionStats: () => request<RetentionStats>('/api/v1/retention/stats'),
  writeRetentionPolicy: (accountId: string, retainBodies: boolean) =>
    request(`/api/v1/retention/accounts/${accountId}/policy`, {
      method: 'PUT',
      body: JSON.stringify({
        enabled: true,
        retain_bodies: retainBodies,
        folders: ['inbox', 'junkemail'],
        max_messages: 1000,
        max_age_days: 30,
      }),
    }),
  syncRetention: (accountId: string) =>
    request<Job>('/api/v1/retention/sync-jobs', {
      method: 'POST',
      body: JSON.stringify({ account_ids: [accountId], limit: 1 }),
    }),
  shares: () => request<EmailShare[]>('/api/v1/email-shares'),
  createShare: (accountId: string, durationMinutes: number) =>
    request<EmailShare>('/api/v1/email-shares', {
      method: 'POST',
      body: JSON.stringify({
        account_id: accountId,
        duration_minutes: durationMinutes,
        allowed_folders: ['inbox'],
      }),
    }),
  revokeShare: (shareId: string) => request<EmailShare>(`/api/v1/email-shares/${shareId}/revoke`, { method: 'POST' }),
  deleteShare: (shareId: string) => request<void>(`/api/v1/email-shares/${shareId}`, { method: 'DELETE' }),
  publicShareStatus: (token: string) =>
    request<PublicShareStatus>(`/api/v1/public/email-shares/${encodeURIComponent(token)}/status`),
  publicShareMail: (token: string, folder = 'inbox') =>
    request<MailPage>(`/api/v1/public/email-shares/${encodeURIComponent(token)}/mail?folder=${folder}&source=auto`),
  publicShareDetail: (token: string, messageId: string, folder = 'inbox') =>
    request<MailDetail>(`/api/v1/public/email-shares/${encodeURIComponent(token)}/mail/${encodeURIComponent(messageId)}?folder=${folder}&source=auto`),
  forwardingDestinations: () =>
    request<ForwardingDestination[]>('/api/v1/forwarding/destinations'),
  createForwardingDestination: (
    name: string,
    channel: 'smtp',
    config: Record<string, string | number | boolean>,
    secret: string,
  ) =>
    request<ForwardingDestination>('/api/v1/forwarding/destinations', {
      method: 'POST',
      body: JSON.stringify({ name, channel, config, secret }),
    }),
  testForwardingDestination: (destinationId: string) =>
    request<{ success: boolean; reason_code: string }>(`/api/v1/forwarding/destinations/${destinationId}/test`, { method: 'POST' }),
  deleteForwardingDestination: (destinationId: string) =>
    request<void>(`/api/v1/forwarding/destinations/${destinationId}`, { method: 'DELETE' }),
  configureForwarding: (accountId: string, destinationIds: string[]) =>
    request(`/api/v1/forwarding/accounts/${accountId}`, {
      method: 'PUT',
      body: JSON.stringify({
        enabled: true,
        include_junk: false,
        window_minutes: 0,
        destination_ids: destinationIds,
      }),
    }),
  runForwarding: (accountId: string) =>
    request<Job>('/api/v1/forwarding/jobs', {
      method: 'POST',
      body: JSON.stringify({ account_ids: [accountId], limit: 1 }),
    }),
  projects: () => request<WorkProject[]>('/api/v1/projects'),
  createProject: (name: string, accountIds: string[]) =>
    request<WorkProject>('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify({
        name,
        description: '',
        default_lease_seconds: 300,
        account_ids: accountIds,
      }),
    }),
  claimProject: (projectId: string, owner: string) =>
    request<ProjectClaim>(`/api/v1/projects/${projectId}/claims`, {
      method: 'POST',
      body: JSON.stringify({ owner }),
    }),
  finishProjectClaim: (projectAccountId: string, claimToken: string, action: 'complete' | 'release' | 'fail') =>
    request(`/api/v1/projects/leases/${projectAccountId}/${action}`, {
      method: 'POST',
      body: JSON.stringify({ claim_token: claimToken, result: {}, error_summary: action === 'fail' ? 'Marked failed from Web console' : null }),
    }),
  heartbeatProjectClaim: (projectAccountId: string, claimToken: string) =>
    request(`/api/v1/projects/leases/${projectAccountId}/heartbeat`, {
      method: 'POST',
      body: JSON.stringify({ claim_token: claimToken }),
    }),
  projectEvents: (projectId: string) => request<ProjectEvent[]>(`/api/v1/projects/${projectId}/events?limit=200`),
  projectAccounts: (projectId: string) => request<ProjectAccount[]>(`/api/v1/projects/${projectId}/accounts?limit=5000`),
  mutateProjectAccounts: (projectId: string, action: 'reset_failed' | 'remove' | 'restore', projectAccountIds: string[]) =>
    request<{ updated_count: number; skipped_count: number }>(`/api/v1/projects/${projectId}/account-actions`, {
      method: 'POST',
      body: JSON.stringify({ action, project_account_ids: projectAccountIds }),
    }),
  setProjectStatus: (projectId: string, status: 'active' | 'paused' | 'completed') =>
    request<WorkProject>(`/api/v1/projects/${projectId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    }),
  job: (jobId: string) => request<Job>(`/api/v1/jobs/${jobId}`),
}
