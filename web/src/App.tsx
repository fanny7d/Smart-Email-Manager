import { useEffect, useState } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, setApiToken, type Account, type AccountViews, type FleetSummary, type StatusCount } from './api/client'
import {
  AutomationView,
  ImportsView,
  JobsView,
  MailView,
  OrganizationView,
  PublicShareView,
  ProjectsView,
  SettingsView,
} from './Views'
import './styles.css'

type View = 'fleet' | 'mail' | 'organization' | 'imports' | 'automation' | 'projects' | 'settings' | 'jobs'
const terminalJobStates = new Set(['completed', 'partial', 'failed', 'cancelled'])
const managementViews: [View, string, string][] = [
  ['fleet', '账号总览', '健康、筛选与批量管理'],
  ['organization', '分组与标签', '整理邮箱资产'],
  ['imports', '批量导入', '添加 Outlook 邮箱'],
  ['automation', '自动化', '刷新与定时计划'],
  ['projects', '项目租约', '自动化账号工作池'],
  ['settings', '系统设置', '代理、分享与令牌'],
  ['jobs', '任务记录', '查看后台任务进度'],
]

function countFor(items: StatusCount[] | undefined, status: string): number {
  return items?.find((item) => item.status === status)?.count ?? 0
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: '启用', inactive: '停用', never: '从未检查', unknown: '未知',
    healthy: '健康', degraded: '降级', failed: '失败', valid: '有效', invalid: '失效',
    reauthorization_required: '需重新授权', not_configured: '未配置',
  }
  return labels[status] ?? status
}

function StatusPill({ value }: { value: string }) {
  return <span className={`status-pill status-${value}`}>{statusLabel(value)}</span>
}

function AccountRow({ account, checked, onToggle }: { account: Account; checked: boolean; onToggle: () => void }) {
  return (
    <tr>
      <td><input aria-label={`选择 ${account.email}`} type="checkbox" checked={checked} onChange={onToggle} /></td>
      <td><div className="account-email">{account.email}</div><div className="account-provider">{account.provider}</div></td>
      <td><StatusPill value={account.lifecycle_status} /></td>
      <td><StatusPill value={account.authorization_status} /></td>
      <td><StatusPill value={account.token_status} /></td>
      <td><StatusPill value={account.mail_health_status} />{account.health_reason_code && <div className="reason-code">{account.health_reason_code}</div>}</td>
      <td><StatusPill value={account.proxy_health_status} /></td>
    </tr>
  )
}

function FleetView({
  summary,
  accounts,
  healthFilter,
  setHealthFilter,
  accountViews,
  smartView,
  setSmartView,
  isLoading,
  hasNextPage,
  isFetchingNextPage,
  loadNextPage,
}: {
  summary: { data?: FleetSummary }
  accounts: Account[]
  healthFilter: string
  setHealthFilter: (value: string) => void
  accountViews?: AccountViews
  smartView: string
  setSmartView: (value: string) => void
  isLoading: boolean
  hasNextPage: boolean
  isFetchingNextPage: boolean
  loadNextPage: () => void
}) {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<string[]>([])
  const [lifecycle, setLifecycle] = useState('')
  const [groupId, setGroupId] = useState('')
  const [bulkScope, setBulkScope] = useState<'ids' | 'filter'>('ids')
  const [savedViewName, setSavedViewName] = useState('')
  const groups = useQuery({ queryKey: ['groups'], queryFn: api.groups })
  const previewBulk = useMutation({
    mutationFn: () => api.previewBulkAccounts(
      bulkScope === 'ids'
        ? { scope: 'ids', account_ids: selected }
        : {
            scope: 'filter',
            mail_health_status: healthFilter || null,
            view: smartView.startsWith('builtin:') ? smartView.slice(8) : null,
            saved_view_id: smartView.startsWith('saved:') ? smartView.slice(6) : null,
          },
      lifecycle || null,
      groupId || null,
    ),
  })
  const executeBulk = useMutation({
    mutationFn: () => api.executeBulkAccounts(previewBulk.data!.preview_token),
    onSuccess: () => {
      setSelected([])
      previewBulk.reset()
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['fleet-summary'] })
    },
  })
  useEffect(() => {
    previewBulk.reset()
  }, [bulkScope, groupId, healthFilter, lifecycle, selected, smartView])
  const saveView = useMutation({
    mutationFn: () => {
      const activeFilters = smartView.startsWith('builtin:')
        ? accountViews?.builtin.find((item) => item.key === smartView.slice(8))?.filters
        : smartView.startsWith('saved:')
          ? accountViews?.saved.find((item) => item.id === smartView.slice(6))?.filters
          : healthFilter
            ? { mail_health_statuses: [healthFilter] }
            : {}
      return api.createAccountView(savedViewName, activeFilters ?? {})
    },
    onSuccess: (created) => {
      setSavedViewName('')
      setHealthFilter('')
      setSmartView(`saved:${created.id}`)
      void queryClient.invalidateQueries({ queryKey: ['account-views'] })
    },
  })
  const updateView = useMutation({
    mutationFn: ({ id, name, sortOrder }: { id: string; name: string; sortOrder: number }) => {
      const current = accountViews?.saved.find((item) => item.id === id)
      if (!current) throw new Error('保存视图不存在')
      return api.updateAccountView(id, name, current.filters, sortOrder)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['account-views'] }),
  })
  const deleteView = useMutation({
    mutationFn: (id: string) => api.deleteAccountView(id),
    onSuccess: (_result, id) => {
      if (smartView === `saved:${id}`) setSmartView('')
      void queryClient.invalidateQueries({ queryKey: ['account-views'] })
    },
  })
  const toggle = (accountId: string) => setSelected((current) => current.includes(accountId) ? current.filter((item) => item !== accountId) : [...current, accountId])
  return (
    <main>
      <section className="metric-grid" aria-label="邮箱资产概览">
        <article className="metric-card metric-primary"><span>总账号</span><strong>{summary.data?.total_accounts ?? '—'}</strong><small>{summary.data?.active_accounts ?? 0} 个启用</small></article>
        <article className="metric-card metric-danger"><span>需要处理</span><strong>{summary.data?.needs_attention ?? '—'}</strong><small>跨授权、Token、邮件和代理</small></article>
        <article className="metric-card"><span>从未检查 Token</span><strong>{countFor(summary.data?.token, 'never')}</strong><small>建议优先抽样验证</small></article>
        <article className="metric-card"><span>邮件健康</span><strong>{countFor(summary.data?.mail_health, 'healthy')}</strong><small>{countFor(summary.data?.mail_health, 'failed')} 个失败</small></article>
      </section>
      <section className="accounts-panel">
        <div className="panel-header"><div><div className="eyebrow">ACCOUNTS</div><h2>邮箱运营表格</h2></div><div className="filters" role="group" aria-label="邮件健康筛选">{[['', '全部'], ['unknown', '未知'], ['healthy', '健康'], ['degraded', '降级'], ['failed', '失败']].map(([value, label]) => <button type="button" className={!smartView && healthFilter === value ? 'filter-active' : ''} onClick={() => { setSmartView(''); setHealthFilter(value) }} key={value || 'all'}>{label}</button>)}</div></div>
        <div className="smart-view-panel"><div><strong>内置智能视图</strong><div className="smart-view-list">{accountViews?.builtin.map((item) => <button title={item.description} className={smartView === `builtin:${item.key}` ? 'filter-active' : ''} type="button" onClick={() => { setHealthFilter(''); setSmartView(`builtin:${item.key}`) }} key={item.key}>{item.name}</button>)}</div></div><div><strong>保存筛选</strong><div className="saved-view-list">{accountViews?.saved.map((item) => <div key={item.id}><button className={smartView === `saved:${item.id}` ? 'filter-active' : ''} type="button" onClick={() => { setHealthFilter(''); setSmartView(`saved:${item.id}`) }}>{item.name}</button><button title="上移" type="button" onClick={() => updateView.mutate({ id: item.id, name: item.name, sortOrder: item.sort_order - 10 })}>↑</button><button title="下移" type="button" onClick={() => updateView.mutate({ id: item.id, name: item.name, sortOrder: item.sort_order + 10 })}>↓</button><button title="重命名" type="button" onClick={() => { const name = window.prompt('保存视图名称', item.name); if (name?.trim()) updateView.mutate({ id: item.id, name: name.trim(), sortOrder: item.sort_order }) }}>改名</button><button className="danger-button" title="删除" type="button" onClick={() => deleteView.mutate(item.id)}>×</button></div>)}</div><div className="save-view-form"><input aria-label="保存视图名称" value={savedViewName} onChange={(event) => setSavedViewName(event.target.value)} placeholder="保存当前筛选" /><button type="button" disabled={!savedViewName.trim() || saveView.isPending} onClick={() => saveView.mutate()}>保存</button></div>{(saveView.error ?? updateView.error ?? deleteView.error) && <div className="inline-error">{(saveView.error ?? updateView.error ?? deleteView.error)?.message}</div>}</div></div>
        <div className="bulk-toolbar"><select aria-label="批量作用范围" value={bulkScope} onChange={(event) => setBulkScope(event.target.value as typeof bulkScope)}><option value="ids">已选择账号</option><option value="filter">当前筛选全部匹配</option></select><button type="button" disabled={bulkScope === 'filter'} onClick={() => setSelected(selected.length === accounts.length ? [] : accounts.map((item) => item.id))}>{selected.length === accounts.length ? '取消全选' : '全选已加载账号'}</button><span>{bulkScope === 'ids' ? `已选 ${selected.length}/${accounts.length}` : '服务端冻结当前筛选，最多 20,000 个'}</span><select aria-label="批量生命周期" value={lifecycle} onChange={(event) => setLifecycle(event.target.value)}><option value="">不改生命周期</option><option value="active">启用</option><option value="inactive">停用</option><option value="archived">归档</option></select><select aria-label="批量分组" value={groupId} onChange={(event) => setGroupId(event.target.value)}><option value="">不改分组</option>{groups.data?.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}</select><button className="primary-button" type="button" disabled={(bulkScope === 'ids' && !selected.length) || previewBulk.isPending || (!lifecycle && !groupId)} onClick={() => previewBulk.mutate()}>生成服务端预览</button></div>
        {previewBulk.data && <div className="bulk-preview" aria-live="polite"><div><strong>稳定快照已生成</strong><span>匹配 {previewBulk.data.matched_count} · 将更新 {previewBulk.data.eligible_count} · 跳过 {previewBulk.data.skipped_count} · 危险 {previewBulk.data.dangerous_count}</span><small>有效期至 {new Date(previewBulk.data.expires_at).toLocaleTimeString()}</small></div><button className={previewBulk.data.dangerous_count ? 'danger-button' : 'primary-button'} type="button" disabled={!previewBulk.data.eligible_count || executeBulk.isPending} onClick={() => { const message = previewBulk.data!.dangerous_count ? `包含 ${previewBulk.data!.dangerous_count} 个归档操作，确认执行一次性快照？` : `确认更新 ${previewBulk.data!.eligible_count} 个账号？`; if (window.confirm(message)) executeBulk.mutate() }}>确认执行快照</button></div>}
        {(previewBulk.error ?? executeBulk.error) && <div className="inline-error">{(previewBulk.error ?? executeBulk.error)?.message}</div>}
        {isLoading ? <div className="empty-state">正在加载资产状态…</div> : accounts.length ? <><div className="table-scroll"><table><thead><tr><th>选择</th><th>邮箱</th><th>生命周期</th><th>授权</th><th>Token</th><th>邮件健康</th><th>代理</th></tr></thead><tbody>{accounts.map((account) => <AccountRow account={account} checked={selected.includes(account.id)} onToggle={() => toggle(account.id)} key={account.id} />)}</tbody></table></div><div className="pagination-bar"><span>已加载 {accounts.length} 个账号</span><button type="button" disabled={!hasNextPage || isFetchingNextPage} onClick={loadNextPage}>{isFetchingNextPage ? '加载中…' : hasNextPage ? '加载下一页' : '已加载全部'}</button></div></> : <div className="empty-state">当前筛选没有账号</div>}
      </section>
    </main>
  )
}

function AuthenticatedApp() {
  const queryClient = useQueryClient()
  const [view, setView] = useState<View>('mail')
  const [healthFilter, setHealthFilter] = useState('')
  const [smartView, setSmartView] = useState('')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [tokenInput, setTokenInput] = useState('')
  const [managementOpen, setManagementOpen] = useState(false)

  const summary = useQuery({ queryKey: ['fleet-summary'], queryFn: api.fleetSummary, refetchInterval: 10_000, enabled: view === 'fleet' })
  const accountViews = useQuery({ queryKey: ['account-views'], queryFn: api.accountViews, enabled: view === 'fleet' })
  const builtinView = smartView.startsWith('builtin:') ? smartView.slice(8) : undefined
  const savedViewId = smartView.startsWith('saved:') ? smartView.slice(6) : undefined
  const accounts = useInfiniteQuery({
    queryKey: ['accounts', healthFilter, smartView],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => api.accounts(healthFilter || undefined, pageParam, 100, builtinView, savedViewId),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })
  const activeJob = useQuery({
    queryKey: ['job', activeJobId], queryFn: () => api.job(activeJobId as string), enabled: Boolean(activeJobId),
    refetchInterval: (query) => query.state.data?.status && terminalJobStates.has(query.state.data.status) ? false : 1_000,
  })
  const checkHealth = useMutation({
    mutationFn: () => api.createConnectivityHealthCheck((accounts.data?.pages.flatMap((page) => page.items) ?? []).map((item) => item.id)),
    onSuccess: (job) => setActiveJobId(job.id),
  })

  useEffect(() => {
    if (activeJob.data && terminalJobStates.has(activeJob.data.status)) {
      void queryClient.invalidateQueries({ queryKey: ['fleet-summary'] })
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    }
  }, [activeJob.data, queryClient])

  useEffect(() => {
    if (!managementOpen) return
    const closeOnOutsideClick = (event: PointerEvent) => {
      const target = event.target as Element | null
      if (!target?.closest('.management-menu')) setManagementOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setManagementOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsideClick)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsideClick)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [managementOpen])

  const saveToken = () => {
    setApiToken(tokenInput)
    void queryClient.invalidateQueries()
  }
  const error = accounts.error ?? (view === 'fleet' ? summary.error ?? accountViews.error : null)
  const accountItems = accounts.data?.pages.flatMap((page) => page.items) ?? []
  const navigate = (nextView: View) => {
    if (nextView === 'mail') {
      setHealthFilter('')
      setSmartView('')
    }
    setView(nextView)
    setManagementOpen(false)
  }
  const managementActive = managementViews.some(([value]) => value === view)

  return (
    <div className="app-shell">
      <header className="simple-topbar">
        <button className="brand-button" type="button" onClick={() => navigate('mail')}>Smart Email Manager</button>
        <nav className="primary-nav" aria-label="主要功能">
          <button type="button" className={view === 'mail' ? 'primary-nav-active' : ''} aria-current={view === 'mail' ? 'page' : undefined} onClick={() => navigate('mail')}>邮箱</button>
        </nav>
        <div className="management-menu">
          <button className={managementActive || managementOpen ? 'management-trigger management-trigger-active' : 'management-trigger'} type="button" aria-expanded={managementOpen} aria-controls="management-popover" onClick={() => setManagementOpen((open) => !open)}>管理</button>
          {managementOpen && <div className="management-popover" id="management-popover">
            <div className="management-links">
              {managementViews.map(([value, label, description]) => <button className={view === value ? 'management-link-active' : ''} type="button" onClick={() => navigate(value)} key={value}><strong>{label}</strong><span>{description}</span></button>)}
            </div>
            <div className="management-actions">
              <button type="button" disabled={checkHealth.isPending || !accountItems.length} onClick={() => checkHealth.mutate()}>{checkHealth.isPending ? '正在创建检查任务…' : `检查已加载账号（${accountItems.length}）`}</button>
              <details>
                <summary>临时 API Token</summary>
                <div className="token-inline-form">
                  <input aria-label="API Token" type="password" value={tokenInput} onChange={(event) => setTokenInput(event.target.value)} placeholder="仅保存在当前标签页" />
                  <button type="button" onClick={saveToken}>应用</button>
                </div>
              </details>
            </div>
          </div>}
        </div>
      </header>
      {error && <div className="error-banner">{error.message}</div>}
      {activeJob.data && <section className="job-banner" aria-live="polite"><div><strong>健康检查任务</strong><span>{activeJob.data.status}</span></div><div>{activeJob.data.succeeded_count}/{activeJob.data.total_count} 完成</div></section>}
      {view === 'fleet' && <FleetView summary={summary} accounts={accountItems} healthFilter={healthFilter} setHealthFilter={setHealthFilter} accountViews={accountViews.data} smartView={smartView} setSmartView={setSmartView} isLoading={summary.isLoading || accounts.isLoading} hasNextPage={Boolean(accounts.hasNextPage)} isFetchingNextPage={accounts.isFetchingNextPage} loadNextPage={() => void accounts.fetchNextPage()} />}
      {view === 'mail' && <MailView accounts={accountItems} hasNextPage={Boolean(accounts.hasNextPage)} isFetchingNextPage={accounts.isFetchingNextPage} loadNextPage={() => void accounts.fetchNextPage()} />}
      {view === 'organization' && <OrganizationView accounts={accountItems} />}
      {view === 'imports' && <ImportsView />}
      {view === 'automation' && <AutomationView />}
      {view === 'projects' && <ProjectsView accounts={accountItems} />}
      {view === 'settings' && <SettingsView accounts={accountItems} />}
      {view === 'jobs' && <JobsView />}
    </div>
  )
}

export default function App() {
  const match = window.location.pathname.match(/^\/shared\/mail\/([^/]+)$/)
  return match ? <PublicShareView token={decodeURIComponent(match[1])} /> : <AuthenticatedApp />
}
