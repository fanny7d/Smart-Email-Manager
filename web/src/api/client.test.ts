// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './client'


function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}


afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})


describe('API-first browser client', () => {
  it('preserves cursor and smart-view filters in account requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [], next_cursor: null, limit: 100 }))
    vi.stubGlobal('fetch', fetchMock)

    await api.accounts('healthy', 'cursor-token', 100, 'reauthorization')

    expect(fetchMock).toHaveBeenCalledOnce()
    const [path] = fetchMock.mock.calls[0]
    const params = new URLSearchParams(String(path).split('?')[1])
    expect(params.get('cursor')).toBe('cursor-token')
    expect(params.get('mail_health_status')).toBe('healthy')
    expect(params.get('view')).toBe('reauthorization')
    expect(params.get('limit')).toBe('100')
  })

  it('creates and executes a stable bulk preview without leaking the token into the URL', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({
        preview_token: 'sem_bulk_once',
        scope: 'filter',
        matched_count: 10,
        eligible_count: 8,
        skipped_count: 2,
        dangerous_count: 0,
        expires_at: '2026-08-29T00:00:00Z',
      }, 201))
      .mockResolvedValueOnce(jsonResponse({ updated_count: 8 }))
    vi.stubGlobal('fetch', fetchMock)

    const preview = await api.previewBulkAccounts(
      { scope: 'filter', view: 'token_failed' },
      'inactive',
      null,
    )
    await api.executeBulkAccounts(preview.preview_token)

    const [previewPath, previewInit] = fetchMock.mock.calls[0]
    const [executePath, executeInit] = fetchMock.mock.calls[1]
    expect(previewPath).toBe('/api/v1/accounts/bulk/previews')
    expect(JSON.parse(previewInit.body)).toMatchObject({
      selection: { scope: 'filter', view: 'token_failed' },
      changes: { lifecycle_status: 'inactive' },
    })
    expect(executePath).toBe('/api/v1/accounts/bulk/executions')
    expect(String(executePath)).not.toContain('sem_bulk_once')
    expect(JSON.parse(executeInit.body)).toEqual({ preview_token: 'sem_bulk_once' })
  })
})
