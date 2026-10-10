// shortcut: browser-only demo metadata, replace with authenticated REST issuance before production use.
export type KeyEnvironment = 'Production' | 'Development'
export type ApiKey = {
  id: string
  name: string
  environment: KeyEnvironment
  maskedKey: string
  createdAt: string
  lastUsedAt: string | null
}

export const API_KEYS_STORAGE = 'mirage-api-keys-v1'
type KeyStorage = Pick<Storage, 'getItem' | 'setItem'>
const isDate = (value: unknown): value is string =>
  typeof value === 'string' && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value

export function listApiKeys(storage: KeyStorage = localStorage): ApiKey[] {
  const raw = storage.getItem(API_KEYS_STORAGE)
  if (raw === null) return []
  const data = JSON.parse(raw)
  if (data?.version !== 1 || !Array.isArray(data.keys)) throw new Error('Saved API key metadata is invalid. Restore or clear this site’s API key storage to continue.')
  const keys: ApiKey[] = data.keys.map((key: unknown) => {
    if (!key || typeof key !== 'object') throw new Error('Saved API key metadata is invalid.')
    const record = key as Record<string, unknown>
    if (typeof record.id !== 'string' || !/^[\da-f-]{36}$/.test(record.id)
      || typeof record.name !== 'string' || !record.name.trim() || record.name.length > 100
      || !['Production', 'Development'].includes(record.environment as string)
      || typeof record.maskedKey !== 'string' || !/^mirage_live_••••••[\da-f]{4}$/.test(record.maskedKey)
      || !isDate(record.createdAt) || (record.lastUsedAt !== null && !isDate(record.lastUsedAt))) {
      throw new Error('Saved API key metadata is invalid. Restore or clear this site’s API key storage to continue.')
    }
    return { id: record.id, name: record.name, environment: record.environment as KeyEnvironment,
      maskedKey: record.maskedKey, createdAt: record.createdAt, lastUsedAt: record.lastUsedAt as string | null }
  })
  if (new Set(keys.map((key) => key.id)).size !== keys.length) throw new Error('Saved API key metadata contains duplicate IDs.')
  return keys
}

export function createApiKey(name: string, environment: KeyEnvironment, storage: KeyStorage = localStorage) {
  name = name.trim()
  if (!name || name.length > 100) throw new Error('Enter a key name between 1 and 100 characters.')
  if (environment !== 'Production' && environment !== 'Development') throw new Error('Choose Production or Development.')
  const keys = listApiKeys(storage)
  const bytes = crypto.getRandomValues(new Uint8Array(32))
  const secret = 'mirage_live_' + Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  const key: ApiKey = { id: crypto.randomUUID(), name, environment,
    maskedKey: `mirage_live_••••••${secret.slice(-4)}`, createdAt: new Date().toISOString(), lastUsedAt: null }
  // The full key exists only in the creation dialog; never persist it.
  storage.setItem(API_KEYS_STORAGE, JSON.stringify({ version: 1, keys: [key, ...keys] }))
  return { key, secret }
}

export function revokeApiKey(id: string, storage: KeyStorage = localStorage) {
  const keys = listApiKeys(storage)
  storage.setItem(API_KEYS_STORAGE, JSON.stringify({ version: 1, keys: keys.filter((key) => key.id !== id) }))
}
