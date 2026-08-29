import { createClient } from '../../web/src/api/generated/client'
import { getFleetSummary, listAccounts } from '../../web/src/api/generated/sdk.gen'

function requiredElement<T extends Element>(selector: string): T {
  const node = document.querySelector<T>(selector)
  if (!node) throw new Error(`Extension popup is missing ${selector}`)
  return node
}

const apiUrl = requiredElement<HTMLInputElement>('#api-url')
const apiToken = requiredElement<HTMLInputElement>('#api-token')
const connect = requiredElement<HTMLButtonElement>('#connect')
const errorNode = requiredElement<HTMLParagraphElement>('#error')
const summaryNode = requiredElement<HTMLElement>('#summary')
const totalNode = requiredElement<HTMLElement>('#total')
const attentionNode = requiredElement<HTMLElement>('#attention')
const accountsNode = requiredElement<HTMLElement>('#accounts')

async function loadStoredSettings() {
  const local = await chrome.storage.local.get({ apiUrl: 'http://127.0.0.1:8000' })
  const session = await chrome.storage.session.get({ apiToken: '' })
  apiUrl.value = String(local.apiUrl)
  apiToken.value = String(session.apiToken)
}

async function requestOriginPermission(baseUrl: string): Promise<boolean> {
  const url = new URL(baseUrl)
  if (url.hostname === '127.0.0.1' || url.hostname === 'localhost') return true
  return chrome.permissions.request({ origins: [`${url.origin}/*`] })
}

function renderAccounts(items: Array<{ email: string; mail_health_status: string; token_status: string }>) {
  accountsNode.replaceChildren()
  if (!items.length) {
    accountsNode.textContent = '暂无账号'
    return
  }
  for (const account of items) {
    const row = document.createElement('div')
    row.className = 'account-row'
    const text = document.createElement('div')
    const email = document.createElement('strong')
    const status = document.createElement('span')
    email.textContent = account.email
    status.textContent = `${account.mail_health_status} · token ${account.token_status}`
    text.append(email, status)
    row.append(text)
    accountsNode.append(row)
  }
}

async function refresh() {
  errorNode.textContent = ''
  connect.disabled = true
  try {
    const baseUrl = apiUrl.value.trim().replace(/\/$/, '')
    const token = apiToken.value.trim()
    if (!(await requestOriginPermission(baseUrl))) throw new Error('未授予该 API 域名访问权限')
    await chrome.storage.local.set({ apiUrl: baseUrl })
    await chrome.storage.session.set({ apiToken: token })
    const client = createClient({
      baseUrl,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
    const [summary, accounts] = await Promise.all([
      getFleetSummary({ client, throwOnError: true }),
      listAccounts({ client, query: { limit: 8 }, throwOnError: true }),
    ])
    totalNode.textContent = String(summary.data.total_accounts)
    attentionNode.textContent = String(summary.data.needs_attention)
    summaryNode.hidden = false
    renderAccounts(accounts.data.items)
  } catch (error) {
    errorNode.textContent = error instanceof Error ? error.message : '连接 API 失败'
  } finally {
    connect.disabled = false
  }
}

connect.addEventListener('click', () => void refresh())
void loadStoredSettings()
