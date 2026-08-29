import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Account, type ImportBatch, type MailAttachment } from './api/client'

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty-state">{children}</div>
}

function saveDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

export function PublicShareView({ token }: { token: string }) {
  const [folder, setFolder] = useState('inbox')
  const [messageId, setMessageId] = useState('')
  const status = useQuery({ queryKey: ['public-share-status', token], queryFn: () => api.publicShareStatus(token), retry: false })
  const mail = useQuery({ queryKey: ['public-share-mail', token, folder], queryFn: () => api.publicShareMail(token, folder), retry: false })
  const detail = useQuery({ queryKey: ['public-share-detail', token, folder, messageId], queryFn: () => api.publicShareDetail(token, messageId, folder), enabled: Boolean(messageId), retry: false })
  const error = status.error ?? mail.error
  return <div className="public-share"><header className="share-header"><div className="eyebrow">READ-ONLY MAIL SHARE</div><h1>{status.data?.email ?? '邮箱分享'}</h1><span>{status.data?.expires_at ? `有效期至 ${new Date(status.data.expires_at).toLocaleString()}` : '长期有效'}</span></header>{error ? <main><div className="inline-error">{error.message}</div></main> : <><nav className="main-nav" aria-label="分享邮箱文件夹">{status.data?.allowed_folders.map((value) => <button className={folder === value ? 'nav-active' : ''} type="button" onClick={() => { setFolder(value); setMessageId('') }} key={value}>{value === 'inbox' ? '收件箱' : '垃圾邮件'}</button>)}</nav><main className="mail-workspace share-workspace"><section className="mail-column"><div className="column-title">邮件列表</div>{mail.data?.items.length ? mail.data.items.map((message) => <button className={message.id === messageId ? 'selected-row' : ''} type="button" onClick={() => setMessageId(message.id)} key={message.id}><strong>{message.subject || '无主题'}</strong><span>{message.sender}</span><small>{message.body_preview}</small></button>) : <Empty>{mail.isLoading ? '正在读取分享邮箱…' : '暂无邮件'}</Empty>}</section><section className="mail-detail"><div className="column-title">只读详情</div>{detail.data ? <article><h2>{detail.data.subject || '无主题'}</h2><p>{detail.data.sender} · {detail.data.received_at}</p><pre>{detail.data.body}</pre></article> : <Empty>{detail.isLoading ? '正在加载详情…' : '选择一封邮件'}</Empty>}</section></main></>}</div>
}

export function OrganizationView({ accounts }: { accounts: Account[] }) {
  const queryClient = useQueryClient()
  const [groupName, setGroupName] = useState('')
  const [parentId, setParentId] = useState('')
  const [tagName, setTagName] = useState('')
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '')
  const [aliasesText, setAliasesText] = useState('')
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([])
  const groups = useQuery({ queryKey: ['groups'], queryFn: api.groups })
  const tags = useQuery({ queryKey: ['tags'], queryFn: api.tags })
  const aliases = useQuery({ queryKey: ['account-aliases', accountId], queryFn: () => api.accountAliases(accountId), enabled: Boolean(accountId) })
  const accountTags = useQuery({ queryKey: ['account-tags', accountId], queryFn: () => api.accountTags(accountId), enabled: Boolean(accountId) })
  useEffect(() => {
    if (!accountId && accounts[0]) setAccountId(accounts[0].id)
  }, [accountId, accounts])
  useEffect(() => {
    setAliasesText(aliases.data?.map((item) => item.email).join('\n') ?? '')
  }, [aliases.data])
  useEffect(() => {
    setSelectedTagIds(accountTags.data?.map((item) => item.id) ?? [])
  }, [accountTags.data])
  const createGroup = useMutation({
    mutationFn: () => api.createGroup(groupName, parentId || undefined),
    onSuccess: () => {
      setGroupName('')
      setParentId('')
      void queryClient.invalidateQueries({ queryKey: ['groups'] })
    },
  })
  const updateGroup = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => api.updateGroup(id, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['groups'] }),
  })
  const deleteGroup = useMutation({
    mutationFn: (id: string) => api.deleteGroup(id),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['groups'] }); void queryClient.invalidateQueries({ queryKey: ['accounts'] }) },
  })
  const createTag = useMutation({
    mutationFn: () => api.createTag(tagName, '#2563eb'),
    onSuccess: () => {
      setTagName('')
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
    },
  })
  const deleteTag = useMutation({
    mutationFn: (id: string) => api.deleteTag(id),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['tags'] }); void queryClient.invalidateQueries({ queryKey: ['account-tags', accountId] }) },
  })
  const saveAliases = useMutation({
    mutationFn: () => api.replaceAccountAliases(accountId, aliasesText.split(/[\n,]/).map((item) => item.trim()).filter(Boolean)),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['account-aliases', accountId] }),
  })
  const saveTags = useMutation({
    mutationFn: () => api.replaceAccountTags(accountId, selectedTagIds),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['account-tags', accountId] }),
  })
  const error = groups.error ?? tags.error ?? aliases.error ?? accountTags.error ?? createGroup.error ?? updateGroup.error ?? deleteGroup.error ?? createTag.error ?? deleteTag.error ?? saveAliases.error ?? saveTags.error

  return (
    <main className="workspace-grid organization-layout">
      {error && <div className="inline-error organization-error">{error.message}</div>}
      <section className="workspace-card">
        <div className="panel-header"><div><div className="eyebrow">GROUPS</div><h2>分组结构</h2></div></div>
        <form className="inline-form" onSubmit={(event) => { event.preventDefault(); if (groupName) createGroup.mutate() }}>
          <input aria-label="新分组名称" value={groupName} onChange={(event) => setGroupName(event.target.value)} placeholder="新分组名称" />
          <select aria-label="父分组" value={parentId} onChange={(event) => setParentId(event.target.value)}><option value="">根分组</option>{groups.data?.filter((group) => group.level < 3 && group.system_key !== 'temporary').map((group) => <option value={group.id} key={group.id}>{'—'.repeat(group.level - 1)}{group.name}</option>)}</select>
          <button type="submit">创建</button>
        </form>
        <div className="stack-list">
          {groups.data?.map((group) => (
            <div className="organization-row" style={{ paddingLeft: `${16 + (group.level - 1) * 24}px` }} key={group.id}>
              <div><span className="color-dot" style={{ background: group.color }} /><strong>{group.name}</strong><span>{group.descendant_account_count} 个账号</span>{group.system_key && <span className="status-pill">系统</span>}</div>
              <div className="row-actions"><button title="上移" type="button" disabled={updateGroup.isPending} onClick={() => updateGroup.mutate({ id: group.id, payload: { sort_order: group.sort_order - 1 } })}>↑</button><button title="下移" type="button" disabled={updateGroup.isPending} onClick={() => updateGroup.mutate({ id: group.id, payload: { sort_order: group.sort_order + 1 } })}>↓</button><button type="button" disabled={updateGroup.isPending} onClick={() => { const name = window.prompt('分组名称', group.name); if (name?.trim()) updateGroup.mutate({ id: group.id, payload: { name: name.trim() } }) }}>改名</button>{!group.system_key && <button className="danger-button" type="button" disabled={deleteGroup.isPending} onClick={() => { if (window.confirm('删除分组及其子分组？账号会移回默认分组。')) deleteGroup.mutate(group.id) }}>删除</button>}</div>
            </div>
          )) ?? <Empty>正在加载分组…</Empty>}
        </div>
      </section>
      <section className="workspace-card">
        <div className="panel-header"><div><div className="eyebrow">TAGS</div><h2>标签</h2></div></div>
        <form className="inline-form" onSubmit={(event) => { event.preventDefault(); if (tagName) createTag.mutate() }}>
          <input aria-label="新标签名称" value={tagName} onChange={(event) => setTagName(event.target.value)} placeholder="新标签名称" />
          <button type="submit">创建</button>
        </form>
        <div className="tag-cloud">
          {tags.data?.length ? tags.data.map((tag) => (
            <span className="tag-chip" style={{ borderColor: tag.color }} key={tag.id}>{tag.name}<button aria-label={`删除标签 ${tag.name}`} type="button" onClick={() => { if (window.confirm(`删除标签“${tag.name}”？`)) deleteTag.mutate(tag.id) }}>×</button></span>
          )) : <Empty>暂无人工标签</Empty>}
        </div>
      </section>
      <section className="workspace-card organization-account-card"><div className="panel-header"><div><div className="eyebrow">ACCOUNT ORGANIZATION</div><h2>账号别名与标签</h2></div></div><div className="form-stack"><label>账号<select value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="">请选择</option>{accounts.map((account) => <option value={account.id} key={account.id}>{account.email}</option>)}</select></label><label>别名（每行一个）<textarea rows={6} value={aliasesText} onChange={(event) => setAliasesText(event.target.value)} placeholder="alias@example.com" /></label><button type="button" disabled={!accountId || saveAliases.isPending} onClick={() => saveAliases.mutate()}>保存别名</button><fieldset className="tag-selector"><legend>人工标签</legend>{tags.data?.map((tag) => <label className="checkbox-row" key={tag.id}><input type="checkbox" checked={selectedTagIds.includes(tag.id)} onChange={() => setSelectedTagIds((current) => current.includes(tag.id) ? current.filter((id) => id !== tag.id) : [...current, tag.id])} />{tag.name}</label>)}</fieldset><button type="button" disabled={!accountId || saveTags.isPending} onClick={() => saveTags.mutate()}>保存账号标签</button></div></section>
    </main>
  )
}

export function ImportsView() {
  const queryClient = useQueryClient()
  const [content, setContent] = useState('')
  const [activeBatch, setActiveBatch] = useState<ImportBatch | null>(null)
  const batches = useQuery({ queryKey: ['import-batches'], queryFn: api.importBatches })
  const plan = useMutation({
    mutationFn: () => api.createImportBatch(content, 'outlook', 'outlook'),
    onSuccess: (batch) => {
      setActiveBatch(batch)
      void queryClient.invalidateQueries({ queryKey: ['import-batches'] })
    },
  })
  const commit = useMutation({
    mutationFn: (batchId: string) => api.commitImportBatch(batchId),
    onSuccess: (batch) => {
      setActiveBatch(batch)
      const createdAccountIds = batch.items.map((item) => item.created_account_id).filter((value): value is string => Boolean(value))
      if (createdAccountIds.length) void api.createConnectivityHealthCheck(createdAccountIds)
      void queryClient.invalidateQueries({ queryKey: ['import-batches'] })
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['fleet-summary'] })
    },
  })
  const rollback = useMutation({
    mutationFn: (batchId: string) => api.rollbackImportBatch(batchId),
    onSuccess: (batch) => {
      setActiveBatch(batch)
      void queryClient.invalidateQueries({ queryKey: ['import-batches'] })
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['fleet-summary'] })
    },
  })

  return (
    <main className="workspace-grid imports-layout">
      <section className="workspace-card">
        <div className="panel-header"><div><div className="eyebrow">PREFLIGHT</div><h2>导入预检</h2></div></div>
        <div className="form-stack">
          <label>Outlook 账号内容<textarea value={content} onChange={(event) => setContent(event.target.value)} rows={12} placeholder="email----password----client_id----refresh_token" /></label>
          <button className="primary-button" type="button" disabled={!content.trim() || plan.isPending} onClick={() => plan.mutate()}>只做预检</button>
        </div>
      </section>
      <section className="workspace-card">
        <div className="panel-header"><div><div className="eyebrow">RESULT</div><h2>批次结果</h2></div></div>
        {activeBatch ? (
          <>
            <div className="batch-metrics"><span>总数 <strong>{activeBatch.total_count}</strong></span><span>有效 <strong>{activeBatch.valid_count}</strong></span><span>无效 <strong>{activeBatch.invalid_count}</strong></span><span>冲突 <strong>{activeBatch.conflict_count}</strong></span></div>
            <div className="stack-list compact">
              {activeBatch.items.map((item) => <div className="stack-row" key={item.id}><span>#{item.line_number}</span><strong>{item.email || '无法解析'}</strong><span className={`status-pill status-${item.status}`}>{item.status}</span><span>{item.error_code || ''}</span></div>)}
            </div>
            <div className="batch-actions">
              <button type="button" disabled={!activeBatch.valid_count || activeBatch.status !== 'validated' || commit.isPending} onClick={() => commit.mutate(activeBatch.id)}>确认提交有效账号</button>
              <button className="danger-button" type="button" disabled={!['completed', 'partial'].includes(activeBatch.status) || rollback.isPending} onClick={() => { if (window.confirm('只会删除本批次新建且之后未修改的账号，确认回滚？')) rollback.mutate(activeBatch.id) }}>有限回滚</button>
            </div>
            {(commit.error ?? rollback.error) && <div className="inline-error">{(commit.error ?? rollback.error)?.message}</div>}
          </>
        ) : <Empty>预检不会写入正式账号表。</Empty>}
        <div className="history-list"><strong>最近批次</strong>{batches.data?.slice(0, 5).map((batch) => <button type="button" onClick={() => setActiveBatch(batch)} key={batch.id}>{batch.status} · {batch.total_count} 项</button>)}</div>
      </section>
    </main>
  )
}

export function JobsView() {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState('')
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs, refetchInterval: 2_000 })
  const events = useQuery({ queryKey: ['job-events', jobId], queryFn: () => api.jobEvents(jobId), enabled: Boolean(jobId), refetchInterval: 2_000 })
  const selectedJob = jobs.data?.find((job) => job.id === jobId)
  const action = useMutation({
    mutationFn: ({ id, type }: { id: string; type: 'pause' | 'resume' | 'cancel' }) => type === 'pause' ? api.pauseJob(id) : type === 'resume' ? api.resumeJob(id) : api.cancelJob(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
      void queryClient.invalidateQueries({ queryKey: ['job-events', jobId] })
    },
  })
  return (
    <main className="workspace-grid jobs-layout">
      <section className="workspace-card"><div className="panel-header"><div><div className="eyebrow">AUTOMATION</div><h2>持久化任务</h2></div></div>
        {jobs.data?.length ? <div className="table-scroll"><table><thead><tr><th>类型</th><th>状态</th><th>进度</th><th>ID</th></tr></thead><tbody>{jobs.data.map((job) => <tr className={job.id === jobId ? 'table-row-selected' : ''} onClick={() => setJobId(job.id)} key={job.id}><td>{job.job_type}</td><td><span className={`status-pill status-${job.status}`}>{job.status}</span></td><td>{job.succeeded_count + job.failed_count + job.skipped_count}/{job.total_count}</td><td>{job.id.slice(0, 8)}</td></tr>)}</tbody></table></div> : <Empty>暂无任务</Empty>}
      </section>
      <section className="workspace-card"><div className="panel-header"><div><div className="eyebrow">CONTROL & EVENTS</div><h2>任务控制与事件</h2></div></div>
        {selectedJob ? <><div className="job-actions"><button type="button" disabled={action.isPending || ['paused', 'completed', 'partial', 'failed', 'cancelled', 'cancelling'].includes(selectedJob.status)} onClick={() => action.mutate({ id: selectedJob.id, type: 'pause' })}>暂停</button><button type="button" disabled={action.isPending || selectedJob.status !== 'paused'} onClick={() => action.mutate({ id: selectedJob.id, type: 'resume' })}>恢复</button><button className="danger-button" type="button" disabled={action.isPending || ['completed', 'partial', 'failed', 'cancelled'].includes(selectedJob.status)} onClick={() => action.mutate({ id: selectedJob.id, type: 'cancel' })}>取消</button></div>{action.error && <div className="inline-error">{action.error.message}</div>}<div className="event-list">{events.data?.items.length ? events.data.items.map((event) => <article key={event.sequence}><span>#{event.sequence} · {event.event_type}</span><strong>{event.message}</strong><small>{new Date(event.created_at).toLocaleString()}</small></article>) : <Empty>{events.isLoading ? '正在读取事件…' : '暂无事件'}</Empty>}</div></> : <Empty>选择一条任务查看持久化事件。</Empty>}
      </section>
    </main>
  )
}

export function AutomationView() {
  const queryClient = useQueryClient()
  const [scheduleName, setScheduleName] = useState('每日 Token 刷新')
  const [cronExpression, setCronExpression] = useState('0 3 * * *')
  const [timezone, setTimezone] = useState('Asia/Shanghai')
  const [failedOnly, setFailedOnly] = useState(false)
  const [taskType, setTaskType] = useState<'token_refresh' | 'retention_sync' | 'forwarding'>('token_refresh')
  const summary = useQuery({
    queryKey: ['token-refresh-summary'],
    queryFn: api.tokenRefreshSummary,
  })
  const logs = useQuery({
    queryKey: ['token-refresh-logs'],
    queryFn: api.tokenRefreshLogs,
    refetchInterval: 5_000,
  })
  const schedules = useQuery({ queryKey: ['schedules'], queryFn: api.schedules })
  const refresh = useMutation({
    mutationFn: () => api.createTokenRefresh(failedOnly),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
      void queryClient.invalidateQueries({ queryKey: ['token-refresh-logs'] })
    },
  })
  const createSchedule = useMutation({
    mutationFn: () => api.createSchedule(scheduleName, cronExpression, timezone, taskType),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['schedules'] }),
  })
  const deleteSchedule = useMutation({
    mutationFn: (scheduleId: string) => api.deleteSchedule(scheduleId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['schedules'] }),
  })
  const error = summary.error ?? logs.error ?? schedules.error ?? refresh.error ?? createSchedule.error

  return (
    <main>
      {error && <div className="inline-error">{error.message}</div>}
      <section className="metric-grid automation-metrics" aria-label="Token 刷新概览">
        <article className="metric-card metric-primary"><span>可刷新账号</span><strong>{summary.data?.total_refreshable ?? '—'}</strong><small>已保存 OAuth refresh token</small></article>
        <article className="metric-card"><span>刷新成功</span><strong>{summary.data?.success ?? '—'}</strong><small>最近状态成功</small></article>
        <article className="metric-card metric-danger"><span>刷新失败</span><strong>{summary.data?.failed ?? '—'}</strong><small>需要重试或重新授权</small></article>
        <article className="metric-card"><span>尚未刷新</span><strong>{summary.data?.never ?? '—'}</strong><small>{summary.data?.stale ?? 0} 个状态过期</small></article>
      </section>
      <section className="workspace-grid">
        <article className="workspace-card">
          <div className="panel-header"><div><div className="eyebrow">TOKEN REFRESH</div><h2>批量刷新</h2></div></div>
          <div className="form-stack">
            <label className="checkbox-row"><input type="checkbox" checked={failedOnly} onChange={(event) => setFailedOnly(event.target.checked)} />只刷新失败账号</label>
            <button className="primary-button" type="button" disabled={refresh.isPending} onClick={() => refresh.mutate()}>{refresh.isPending ? '正在创建任务…' : '创建刷新任务'}</button>
            {refresh.data && <div className="notice-box">任务 {refresh.data.id.slice(0, 8)} 已创建，共 {refresh.data.total_count} 个账号。</div>}
          </div>
          <div className="panel-header"><div><div className="eyebrow">HISTORY</div><h2>刷新记录</h2></div></div>
          <div className="stack-list compact">
            {logs.data?.length ? logs.data.map((log) => <div className="stack-row" key={log.id}><span className={`status-pill status-${log.status}`}>{log.status}</span><strong>{log.account_id.slice(0, 8)}</strong><span>{log.channel || 'all'} · {log.reason_code || '—'}{log.rotated ? ' · 已轮换' : ''}</span></div>) : <Empty>暂无刷新记录</Empty>}
          </div>
        </article>
        <article className="workspace-card">
          <div className="panel-header"><div><div className="eyebrow">SCHEDULES</div><h2>定时计划</h2></div></div>
          <form className="form-stack" onSubmit={(event) => { event.preventDefault(); if (scheduleName && cronExpression) createSchedule.mutate() }}>
            <label>计划名称<input value={scheduleName} onChange={(event) => setScheduleName(event.target.value)} /></label>
            <label>任务类型<select value={taskType} onChange={(event) => setTaskType(event.target.value as typeof taskType)}><option value="token_refresh">Token 刷新</option><option value="retention_sync">本地保留同步</option><option value="forwarding">邮件转发</option></select></label>
            <label>Cron（5 段）<input value={cronExpression} onChange={(event) => setCronExpression(event.target.value)} placeholder="0 3 * * *" /></label>
            <label>时区<input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Shanghai" /></label>
            <button type="submit" disabled={createSchedule.isPending}>保存计划</button>
          </form>
          <div className="stack-list">
            {schedules.data?.length ? schedules.data.map((schedule) => <div className="schedule-row" key={schedule.id}><div><strong>{schedule.name}</strong><span>{schedule.cron_expression} · {schedule.timezone}</span><small>下次：{new Date(schedule.next_run_at).toLocaleString()}</small></div><button type="button" disabled={deleteSchedule.isPending} onClick={() => deleteSchedule.mutate(schedule.id)}>删除</button></div>) : <Empty>暂无定时计划</Empty>}
          </div>
        </article>
      </section>
    </main>
  )
}

export function ProjectsView({ accounts }: { accounts: Account[] }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([])
  const [projectId, setProjectId] = useState('')
  const [selectedProjectAccounts, setSelectedProjectAccounts] = useState<string[]>([])
  const [owner, setOwner] = useState('browser-worker')
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects })
  const events = useQuery({ queryKey: ['project-events', projectId], queryFn: () => api.projectEvents(projectId), enabled: Boolean(projectId), refetchInterval: 5_000 })
  const projectAccounts = useQuery({ queryKey: ['project-accounts', projectId], queryFn: () => api.projectAccounts(projectId), enabled: Boolean(projectId), refetchInterval: 5_000 })
  const createProject = useMutation({
    mutationFn: () => api.createProject(name, selectedAccounts),
    onSuccess: (project) => {
      setName('')
      setSelectedAccounts([])
      setProjectId(project.id)
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
  const claim = useMutation({ mutationFn: () => api.claimProject(projectId, owner), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['projects'] }); void queryClient.invalidateQueries({ queryKey: ['project-accounts', projectId] }) } })
  const finish = useMutation({
    mutationFn: (action: 'complete' | 'release' | 'fail') => api.finishProjectClaim(claim.data!.project_account_id, claim.data!.claim_token, action),
    onSuccess: () => { claim.reset(); void queryClient.invalidateQueries({ queryKey: ['projects'] }); void queryClient.invalidateQueries({ queryKey: ['project-events', projectId] }); void queryClient.invalidateQueries({ queryKey: ['project-accounts', projectId] }) },
  })
  const heartbeat = useMutation({
    mutationFn: () => api.heartbeatProjectClaim(claim.data!.project_account_id, claim.data!.claim_token),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['project-events', projectId] }),
  })
  const setStatus = useMutation({
    mutationFn: (status: 'active' | 'paused' | 'completed') => api.setProjectStatus(projectId, status),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['projects'] }); void queryClient.invalidateQueries({ queryKey: ['project-events', projectId] }) },
  })
  const projectAccountAction = useMutation({
    mutationFn: (action: 'reset_failed' | 'remove' | 'restore') => api.mutateProjectAccounts(projectId, action, selectedProjectAccounts),
    onSuccess: () => { setSelectedProjectAccounts([]); void queryClient.invalidateQueries({ queryKey: ['projects'] }); void queryClient.invalidateQueries({ queryKey: ['project-events', projectId] }); void queryClient.invalidateQueries({ queryKey: ['project-accounts', projectId] }) },
  })
  const toggleAccount = (accountId: string) => setSelectedAccounts((current) => current.includes(accountId) ? current.filter((item) => item !== accountId) : [...current, accountId])
  const error = createProject.error ?? claim.error ?? finish.error ?? heartbeat.error ?? setStatus.error ?? projectAccountAction.error ?? events.error ?? projectAccounts.error
  return <main className="workspace-grid projects-layout">
    <section className="workspace-card"><div className="panel-header"><div><div className="eyebrow">PROJECT POOL</div><h2>创建账号工作池</h2></div></div><form className="form-stack" onSubmit={(event) => { event.preventDefault(); createProject.mutate() }}><label>项目名称<input value={name} onChange={(event) => setName(event.target.value)} /></label><div className="account-checklist"><button type="button" onClick={() => setSelectedAccounts(selectedAccounts.length === accounts.length ? [] : accounts.map((item) => item.id))}>{selectedAccounts.length === accounts.length ? '取消全选' : `选择当前已加载 ${accounts.length} 个账号`}</button>{accounts.map((account) => <label className="checkbox-row" key={account.id}><input type="checkbox" checked={selectedAccounts.includes(account.id)} onChange={() => toggleAccount(account.id)} />{account.email}</label>)}</div><button type="submit" disabled={!name || !selectedAccounts.length}>创建项目</button></form><div className="stack-list">{projects.data?.map((project) => <button className={`channel-choice ${project.id === projectId ? 'selected-row' : ''}`} type="button" onClick={() => { setProjectId(project.id); setSelectedProjectAccounts([]); claim.reset() }} key={project.id}><strong>{project.name}</strong><span>{project.status} · 待领取 {project.to_claim_count} · 租约中 {project.leased_count} · 完成 {project.done_count} · 失败 {project.failed_count}</span></button>)}</div></section>
    <section className="workspace-card"><div className="panel-header"><div><div className="eyebrow">LEASE</div><h2>领取与控制</h2></div></div><div className="form-stack"><label>项目<select value={projectId} onChange={(event) => { setProjectId(event.target.value); claim.reset() }}><option value="">请选择</option>{projects.data?.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select></label><div className="project-status-actions"><button type="button" disabled={!projectId || setStatus.isPending} onClick={() => setStatus.mutate('active')}>启用</button><button type="button" disabled={!projectId || setStatus.isPending} onClick={() => setStatus.mutate('paused')}>暂停</button><button type="button" disabled={!projectId || setStatus.isPending} onClick={() => setStatus.mutate('completed')}>完成项目</button></div><label>领取者<input value={owner} onChange={(event) => setOwner(event.target.value)} /></label><button type="button" disabled={!projectId || !owner || claim.isPending || Boolean(claim.data)} onClick={() => claim.mutate()}>原子领取下一个账号</button>{error && <div className="inline-error">{error.message}</div>}{claim.data && <div className="claim-card"><span>已领取</span><strong>{claim.data.email}</strong><small>租约到期：{new Date(claim.data.lease_expires_at).toLocaleString()}</small><div className="secret-result"><strong>Claim Token 仅显示一次</strong><code>{claim.data.claim_token}</code></div><div className="claim-actions"><button type="button" disabled={heartbeat.isPending} onClick={() => heartbeat.mutate()}>续租</button><button type="button" disabled={finish.isPending} onClick={() => finish.mutate('complete')}>标记完成</button><button type="button" disabled={finish.isPending} onClick={() => finish.mutate('release')}>释放回池</button><button className="danger-button" type="button" disabled={finish.isPending} onClick={() => finish.mutate('fail')}>标记失败</button></div></div>}</div><div className="panel-header"><div><div className="eyebrow">TIMELINE</div><h2>项目事件</h2></div></div><div className="event-list">{events.data?.length ? events.data.map((event) => <article key={event.sequence}><span>#{event.sequence} · {event.event_type}</span><strong>{event.actor || 'system'}</strong><small>{new Date(event.created_at).toLocaleString()}</small></article>) : <Empty>{projectId ? '暂无事件' : '选择项目查看事件'}</Empty>}</div></section>
    <section className="workspace-card project-accounts-card"><div className="panel-header"><div><div className="eyebrow">PROJECT ACCOUNTS</div><h2>账号状态与受控操作</h2></div><div className="project-status-actions"><button type="button" disabled={!selectedProjectAccounts.length || projectAccountAction.isPending} onClick={() => projectAccountAction.mutate('reset_failed')}>重置失败</button><button className="danger-button" type="button" disabled={!selectedProjectAccounts.length || projectAccountAction.isPending} onClick={() => { if (window.confirm('移除选中的非租约账号？')) projectAccountAction.mutate('remove') }}>移除</button><button type="button" disabled={!selectedProjectAccounts.length || projectAccountAction.isPending} onClick={() => projectAccountAction.mutate('restore')}>恢复</button></div></div>{projectAccounts.data?.length ? <div className="table-scroll"><table><thead><tr><th>选择</th><th>邮箱</th><th>状态</th><th>领取者</th><th>尝试</th><th>租约/完成时间</th></tr></thead><tbody>{projectAccounts.data.map((item) => <tr key={item.id}><td><input aria-label={`选择项目账号 ${item.email}`} type="checkbox" checked={selectedProjectAccounts.includes(item.id)} onChange={() => setSelectedProjectAccounts((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} /></td><td>{item.email}</td><td><span className={`status-pill status-${item.status}`}>{item.status}</span></td><td>{item.lease_owner || '—'}</td><td>{item.attempt_count}</td><td>{item.lease_expires_at ? new Date(item.lease_expires_at).toLocaleString() : item.finished_at ? new Date(item.finished_at).toLocaleString() : '—'}</td></tr>)}</tbody></table></div> : <Empty>{projectId ? '项目暂无账号' : '选择项目查看账号状态'}</Empty>}</section>
  </main>
}


export function SettingsView({ accounts }: { accounts: Account[] }) {
  const queryClient = useQueryClient()
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '')
  const [proxyName, setProxyName] = useState('')
  const [proxyUrl, setProxyUrl] = useState('')
  const [proxyId, setProxyId] = useState('')
  const [retainBodies, setRetainBodies] = useState(false)
  const [shareMinutes, setShareMinutes] = useState(1440)
  const [forwardName, setForwardName] = useState('')
  const [forwardEndpoint, setForwardEndpoint] = useState('')
  const [forwardTarget, setForwardTarget] = useState('')
  const [forwardSecret, setForwardSecret] = useState('')
  const [destinationId, setDestinationId] = useState('')
  const [tokenName, setTokenName] = useState('automation-client')
  const [tokenScopes, setTokenScopes] = useState('accounts:read,mail:read,jobs:read')
  const [tokenDays, setTokenDays] = useState(30)
  useEffect(() => {
    if (!accountId && accounts[0]) setAccountId(accounts[0].id)
  }, [accountId, accounts])
  const proxies = useQuery({ queryKey: ['proxies'], queryFn: api.proxies })
  const retentionStats = useQuery({ queryKey: ['retention-stats'], queryFn: api.retentionStats })
  const shares = useQuery({ queryKey: ['shares'], queryFn: api.shares })
  const destinations = useQuery({ queryKey: ['forwarding-destinations'], queryFn: api.forwardingDestinations })
  const apiTokens = useQuery({ queryKey: ['api-tokens'], queryFn: api.apiTokens })
  const createProxy = useMutation({
    mutationFn: () => api.createProxy(proxyName, proxyUrl),
    onSuccess: () => { setProxyName(''); setProxyUrl(''); void queryClient.invalidateQueries({ queryKey: ['proxies'] }) },
  })
  const assignProxy = useMutation({ mutationFn: () => api.assignAccountProxy(accountId, proxyId || null) })
  const probeProxy = useMutation({
    mutationFn: (profileId: string) => api.probeProxy(profileId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['proxies'] }),
  })
  const deleteProxy = useMutation({
    mutationFn: (profileId: string) => api.deleteProxy(profileId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['proxies'] }),
  })
  const retention = useMutation({
    mutationFn: () => api.writeRetentionPolicy(accountId, retainBodies),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['retention-stats'] }),
  })
  const retentionSync = useMutation({ mutationFn: () => api.syncRetention(accountId) })
  const createShare = useMutation({
    mutationFn: () => api.createShare(accountId, shareMinutes),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['shares'] }),
  })
  const revokeShare = useMutation({
    mutationFn: (shareId: string) => api.revokeShare(shareId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['shares'] }),
  })
  const deleteShare = useMutation({
    mutationFn: (shareId: string) => api.deleteShare(shareId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['shares'] }),
  })
  const createDestination = useMutation({
    mutationFn: () => {
      const config: Record<string, string | number | boolean> = { host: forwardEndpoint, port: 465, recipient: forwardTarget, use_ssl: true }
      return api.createForwardingDestination(forwardName, 'smtp', config, forwardSecret)
    },
    onSuccess: () => { setForwardName(''); setForwardSecret(''); void queryClient.invalidateQueries({ queryKey: ['forwarding-destinations'] }) },
  })
  const configureForward = useMutation({ mutationFn: () => api.configureForwarding(accountId, destinationId ? [destinationId] : []) })
  const runForward = useMutation({ mutationFn: () => api.runForwarding(accountId) })
  const testDestination = useMutation({ mutationFn: (id: string) => api.testForwardingDestination(id) })
  const deleteDestination = useMutation({
    mutationFn: (id: string) => api.deleteForwardingDestination(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['forwarding-destinations'] }),
  })
  const createToken = useMutation({
    mutationFn: () => api.createApiToken(tokenName, tokenScopes.split(',').map((item) => item.trim()).filter(Boolean), tokenDays || null),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['api-tokens'] }),
  })
  const revokeToken = useMutation({
    mutationFn: (id: string) => api.revokeApiToken(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['api-tokens'] }),
  })
  const errors = [proxies.error, retentionStats.error, shares.error, destinations.error, apiTokens.error, createProxy.error, assignProxy.error, retention.error, createShare.error, createDestination.error, deleteProxy.error, revokeShare.error, deleteShare.error, testDestination.error, deleteDestination.error, createToken.error, revokeToken.error].filter(Boolean) as Error[]

  return (
    <main>
      {errors[0] && <div className="inline-error">{errors[0].message}</div>}
      <div className="settings-account-bar"><label>当前账号<select value={accountId} onChange={(event) => setAccountId(event.target.value)}>{accounts.map((account) => <option value={account.id} key={account.id}>{account.email}</option>)}</select></label></div>
      <section className="settings-grid">
        <article className="workspace-card"><div className="panel-header"><div><div className="eyebrow">PROXY</div><h2>代理配置</h2></div></div><form className="form-stack" onSubmit={(event) => { event.preventDefault(); createProxy.mutate() }}><label>名称<input value={proxyName} onChange={(event) => setProxyName(event.target.value)} /></label><label>主代理 URL<input type="password" value={proxyUrl} onChange={(event) => setProxyUrl(event.target.value)} placeholder="socks5h://user:pass@host:port" /></label><button type="submit" disabled={!proxyName || !proxyUrl}>保存加密代理</button></form><div className="form-stack"><label>给当前账号分配<select value={proxyId} onChange={(event) => setProxyId(event.target.value)}><option value="">直连/继承分组</option>{proxies.data?.map((proxy) => <option value={proxy.id} key={proxy.id}>{proxy.name} · {proxy.primary_hint}</option>)}</select></label><button type="button" disabled={!accountId} onClick={() => assignProxy.mutate()}>应用代理</button></div><div className="stack-list compact">{proxies.data?.map((proxy) => <div className="schedule-row" key={proxy.id}><div><strong>{proxy.name}</strong><span>{proxy.health_status} · {proxy.health_reason_code || '尚未探测'}</span></div><div className="row-actions"><button type="button" disabled={probeProxy.isPending} onClick={() => probeProxy.mutate(proxy.id)}>探测</button><button className="danger-button" type="button" disabled={deleteProxy.isPending} onClick={() => { if (window.confirm('删除代理配置？已分配账号会回退到继承或直连。')) deleteProxy.mutate(proxy.id) }}>删除</button></div></div>)}</div></article>
        <article className="workspace-card"><div className="panel-header"><div><div className="eyebrow">RETENTION & SHARE</div><h2>本地保留与分享</h2></div></div><div className="batch-metrics"><span>缓存邮件<strong>{retentionStats.data?.message_count ?? 0}</strong></span><span>缓存正文<strong>{retentionStats.data?.body_count ?? 0}</strong></span></div><div className="form-stack"><label className="checkbox-row"><input type="checkbox" checked={retainBodies} onChange={(event) => setRetainBodies(event.target.checked)} />同步正文（默认只保留列表）</label><button type="button" disabled={!accountId} onClick={() => retention.mutate()}>启用保留策略</button><button type="button" disabled={!accountId} onClick={() => retentionSync.mutate()}>创建同步任务</button><label>分享时长（分钟）<input type="number" min="1" value={shareMinutes} onChange={(event) => setShareMinutes(Number(event.target.value))} /></label><button type="button" disabled={!accountId} onClick={() => createShare.mutate()}>创建只读分享</button>{createShare.data?.share_path && <div className="secret-result"><strong>仅显示一次</strong><code>{createShare.data.share_path}</code></div>}</div><div className="stack-list compact">{shares.data?.map((share) => <div className="schedule-row" key={share.id}><div><strong>{share.status}</strong><span>{share.expires_at ? `到期 ${new Date(share.expires_at).toLocaleString()}` : '长期有效'}</span></div><div className="row-actions"><button type="button" disabled={share.status !== 'active' || revokeShare.isPending} onClick={() => revokeShare.mutate(share.id)}>吊销</button><button className="danger-button" type="button" disabled={deleteShare.isPending} onClick={() => deleteShare.mutate(share.id)}>删除</button></div></div>)}</div></article>
        <article className="workspace-card"><div className="panel-header"><div><div className="eyebrow">SMTP FORWARDING</div><h2>邮件转发</h2></div></div><form className="form-stack" onSubmit={(event) => { event.preventDefault(); createDestination.mutate() }}><label>目的地名称<input value={forwardName} onChange={(event) => setForwardName(event.target.value)} /></label><label>SMTP Host<input value={forwardEndpoint} onChange={(event) => setForwardEndpoint(event.target.value)} /></label><label>收件人<input value={forwardTarget} onChange={(event) => setForwardTarget(event.target.value)} /></label><label>SMTP 密码<input type="password" value={forwardSecret} onChange={(event) => setForwardSecret(event.target.value)} /></label><button type="submit" disabled={!forwardName || !forwardEndpoint || !forwardTarget}>保存目的地</button></form><div className="form-stack"><label>当前账号目的地<select value={destinationId} onChange={(event) => setDestinationId(event.target.value)}><option value="">请选择</option>{destinations.data?.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><button type="button" disabled={!accountId || !destinationId} onClick={() => configureForward.mutate()}>启用账号转发</button><button type="button" disabled={!accountId} onClick={() => runForward.mutate()}>立即扫描</button>{testDestination.data && <div className="notice-box">测试：{testDestination.data.success ? '成功' : '失败'} · {testDestination.data.reason_code}</div>}</div><div className="stack-list compact">{destinations.data?.map((item) => <div className="schedule-row" key={item.id}><div><strong>{item.name}</strong><span>{item.enabled ? '启用' : '停用'}</span></div><div className="row-actions"><button type="button" onClick={() => testDestination.mutate(item.id)}>测试</button><button className="danger-button" type="button" onClick={() => deleteDestination.mutate(item.id)}>删除</button></div></div>)}</div></article>
        <article className="workspace-card settings-wide"><div className="panel-header"><div><div className="eyebrow">API TOKENS</div><h2>自动化访问令牌</h2></div></div><form className="token-form" onSubmit={(event) => { event.preventDefault(); createToken.mutate() }}><label>名称<input value={tokenName} onChange={(event) => setTokenName(event.target.value)} /></label><label>Scopes（逗号分隔）<input value={tokenScopes} onChange={(event) => setTokenScopes(event.target.value)} /></label><label>有效天数<input type="number" min="1" max="3650" value={tokenDays} onChange={(event) => setTokenDays(Number(event.target.value))} /></label><button type="submit" disabled={!tokenName || !tokenScopes || createToken.isPending}>创建令牌</button></form>{createToken.data && <div className="secret-result token-secret"><strong>令牌仅显示一次，请立即保存到自动化密钥存储</strong><code>{createToken.data.secret}</code></div>}<div className="table-scroll"><table><thead><tr><th>名称</th><th>前缀</th><th>Scopes</th><th>到期</th><th>最近使用</th><th>操作</th></tr></thead><tbody>{apiTokens.data?.map((token) => <tr key={token.id}><td>{token.name}</td><td>{token.token_prefix}</td><td>{token.scopes.join(', ')}</td><td>{token.expires_at ? new Date(token.expires_at).toLocaleDateString() : '永不'}</td><td>{token.last_used_at ? new Date(token.last_used_at).toLocaleString() : '从未'}</td><td><button className="danger-button table-action" type="button" disabled={Boolean(token.revoked_at) || revokeToken.isPending} onClick={() => revokeToken.mutate(token.id)}>{token.revoked_at ? '已吊销' : '吊销'}</button></td></tr>)}</tbody></table></div></article>
      </section>
    </main>
  )
}


export function MailView({ accounts }: { accounts: Account[] }) {
  const queryClient = useQueryClient()
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '')
  const [messageId, setMessageId] = useState('')
  const [messageFolder, setMessageFolder] = useState('')
  const [folder, setFolder] = useState<'inbox' | 'junkemail' | 'deleteditems' | 'all'>('inbox')
  useEffect(() => {
    if (!accountId && accounts[0]) setAccountId(accounts[0].id)
  }, [accountId, accounts])
  const mail = useQuery({ queryKey: ['mail', accountId, folder], queryFn: () => api.mail(accountId, folder), enabled: Boolean(accountId), retry: false })
  const detailFolder = messageFolder || (folder === 'all' ? 'inbox' : folder)
  const detail = useQuery({ queryKey: ['mail-detail', accountId, detailFolder, messageId], queryFn: () => api.mailDetail(accountId, messageId, detailFolder), enabled: Boolean(accountId && messageId), retry: false })
  useEffect(() => {
    if (!mail.dataUpdatedAt) return
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    void queryClient.invalidateQueries({ queryKey: ['fleet-summary'] })
  }, [mail.dataUpdatedAt, queryClient])
  const markRead = useMutation({
    mutationFn: () => api.markMailRead(accountId, messageId, detailFolder),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['mail', accountId] }); void queryClient.invalidateQueries({ queryKey: ['mail-detail', accountId, detailFolder, messageId] }) },
  })
  const remove = useMutation({
    mutationFn: () => api.deleteMail(accountId, messageId, detailFolder),
    onSuccess: () => { setMessageId(''); setMessageFolder(''); void queryClient.invalidateQueries({ queryKey: ['mail', accountId] }) },
  })
  const raw = useMutation({
    mutationFn: () => api.rawMail(accountId, messageId, detailFolder),
    onSuccess: (blob) => saveDownload(blob, `message-${messageId}.eml`),
  })
  const attachment = useMutation({
    mutationFn: (item: MailAttachment) => api.mailAttachment(accountId, messageId, item.id, detailFolder).then((blob) => ({ blob, item })),
    onSuccess: ({ blob, item }) => saveDownload(blob, item.name || 'attachment'),
  })

  const healthLabel = (account: Account) => {
    if (account.id === accountId && mail.data) return `已连接 · ${mail.data.method.toUpperCase()}`
    return ({ healthy: '健康', degraded: '降级', failed: '失败', unknown: '未检查' } as Record<string, string>)[account.mail_health_status] ?? account.mail_health_status
  }

  return (
    <main className="mail-workspace">
      <section className="mail-column account-column"><div className="column-title">邮箱账号</div>{accounts.map((account) => <button className={account.id === accountId ? 'selected-row' : ''} type="button" onClick={() => { setAccountId(account.id); setMessageId(''); setMessageFolder('') }} key={account.id}><strong>{account.email}</strong><span>{healthLabel(account)}</span></button>)}</section>
      <section className="mail-column">
        <div className="column-title mail-list-toolbar">
          <span>邮件列表</span>
          <select aria-label="邮件文件夹" value={folder} onChange={(event) => { setFolder(event.target.value as typeof folder); setMessageId(''); setMessageFolder('') }}>
            <option value="inbox">收件箱</option>
            <option value="junkemail">垃圾邮件</option>
            <option value="deleteditems">已删除</option>
            <option value="all">收件箱 + 垃圾邮件</option>
          </select>
          <button type="button" disabled={mail.isFetching} onClick={() => void mail.refetch()}>{mail.isFetching ? '读取中' : '刷新'}</button>
        </div>
        {mail.error ? <div className="mail-query-state mail-query-error" role="alert"><strong>读取失败</strong><span>{mail.error.message}</span></div> : mail.data?.items.length ? mail.data.items.map((message) => <button className={message.id === messageId && message.folder === messageFolder ? 'selected-row' : ''} type="button" onClick={() => { setMessageId(message.id); setMessageFolder(message.folder) }} key={`${message.folder}:${message.id}`}><strong>{message.subject || '无主题'}</strong><span>{message.sender}</span><small>{message.body_preview}</small></button>) : mail.isLoading ? <Empty>正在连接邮箱…</Empty> : mail.data ? <div className="mail-query-state" aria-live="polite"><strong>{mail.data.method.toUpperCase()} 已连接</strong><span>邮件服务器返回 0 封，此文件夹目前为空。</span></div> : <Empty>请选择邮箱账号</Empty>}
      </section>
      <section className="mail-detail"><div className="column-title">邮件详情</div>{detail.error ? <div className="mail-query-state mail-query-error" role="alert"><strong>详情读取失败</strong><span>{detail.error.message}</span></div> : detail.data ? <article><div className="mail-detail-heading"><div><h2>{detail.data.subject || '无主题'}</h2><p>{detail.data.sender} · {detail.data.received_at}</p></div><div className="mail-actions"><button type="button" disabled={detail.data.is_read || markRead.isPending} onClick={() => markRead.mutate()}>{detail.data.is_read ? '已读' : '标记已读'}</button><button type="button" disabled={raw.isPending} onClick={() => raw.mutate()}>下载原始 MIME</button><button className="danger-button" type="button" disabled={remove.isPending} onClick={() => { if (window.confirm('删除这封邮件？此操作会同步到远端邮箱。')) remove.mutate() }}>删除</button></div></div>{(markRead.error ?? remove.error ?? raw.error ?? attachment.error) && <div className="inline-error">{(markRead.error ?? remove.error ?? raw.error ?? attachment.error)?.message}</div>}<div className="recipient-line">收件人：{detail.data.recipients.join(', ') || '—'}{detail.data.cc.length ? ` · 抄送：${detail.data.cc.join(', ')}` : ''}</div>{detail.data.attachments.length > 0 && <div className="attachment-list"><strong>附件</strong>{detail.data.attachments.map((item) => <button type="button" disabled={attachment.isPending} onClick={() => attachment.mutate(item)} key={item.id}>{item.name} · {Math.ceil(item.size / 1024)} KB</button>)}</div>}<pre>{detail.data.body}</pre></article> : <Empty>{detail.isLoading ? '正在加载详情…' : '选择一封邮件查看详情'}</Empty>}</section>
    </main>
  )
}


export function CodesView({ accounts }: { accounts: Account[] }) {
  const [accountId, setAccountId] = useState('')
  const [recentMinutes, setRecentMinutes] = useState(30)
  const codes = useMutation({
    mutationFn: () => accountId
      ? api.verificationCodes(accountId, recentMinutes)
      : api.queryVerificationCodes([], recentMinutes, 100),
  })

  return (
    <main className="codes-workspace">
      <section className="workspace-card codes-toolbar">
        <div className="panel-header"><div><div className="eyebrow">OUTLOOK VERIFICATION CODES</div><h2>验证码中心</h2></div></div>
        <div className="codes-controls">
          <label>查询范围<select value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="">全部启用邮箱（最多 100 个）</option>{accounts.map((account) => <option value={account.id} key={account.id}>{account.email}</option>)}</select></label>
          <label>最近时间<select value={recentMinutes} onChange={(event) => setRecentMinutes(Number(event.target.value))}><option value={10}>10 分钟</option><option value={30}>30 分钟</option><option value={60}>1 小时</option><option value={360}>6 小时</option><option value={1440}>24 小时</option></select></label>
          <button type="button" disabled={codes.isPending} onClick={() => codes.mutate()}>{codes.isPending ? '正在查询…' : '获取验证码'}</button>
        </div>
        <p className="muted-copy">只读查询收件箱和垃圾邮件，不会自动标记已读或删除邮件。</p>
      </section>
      {codes.error && <div className="inline-error">{codes.error.message}</div>}
      {codes.data && <div className="codes-summary">已检查 {codes.data.checked_accounts} 个邮箱 · 找到 {codes.data.items.length} 个验证码{codes.data.failed_accounts ? ` · ${codes.data.failed_accounts} 个失败` : ''}</div>}
      <section className="codes-grid">
        {codes.data?.items.map((item) => <article className="workspace-card code-card" key={`${item.account_id}:${item.folder}:${item.message_id}:${item.code}`}>
          <div className="code-value">{item.code}</div>
          <button type="button" onClick={() => void navigator.clipboard.writeText(item.code)}>复制验证码</button>
          <strong>{item.email}</strong>
          <span>{item.subject || '无主题'}</span>
          <small>{item.sender} · {new Date(item.received_at).toLocaleString()}</small>
          <small>{item.folder === 'junkemail' ? '垃圾邮件' : '收件箱'} · {item.method.toUpperCase()} · {item.confidence === 'high' ? '高置信度' : '中置信度'}</small>
        </article>)}
        {codes.data && !codes.data.items.length && <Empty>最近时间范围内没有识别到验证码邮件。</Empty>}
      </section>
    </main>
  )
}
