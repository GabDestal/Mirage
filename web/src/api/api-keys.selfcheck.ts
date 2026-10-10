import { API_KEYS_STORAGE, createApiKey, listApiKeys, revokeApiKey } from './api-keys.ts'

function check(condition: boolean, message: string) { if (!condition) throw new Error(message) }
function rejects(action: () => unknown, message: string) {
  let rejected = false
  try { action() } catch { rejected = true }
  check(rejected, message)
}
const values = new Map<string, string>()
const storage = {
  getItem: (key: string) => values.get(key) ?? null,
  setItem: (key: string, value: string) => { values.set(key, value) },
}

check(listApiKeys(storage).length === 0, 'New storage starts empty')
const first = createApiKey('  Meeting assistant  ', storage)
check(/^mirage_live_[\da-f]{64}$/.test(first.secret), 'Key has the expected format and 256 random bits')
check(first.key.name === 'Meeting assistant', 'Names are trimmed')
check(first.key.maskedKey === `mirage_live_••••••${first.secret.slice(-4)}`, 'Only suffix appears in metadata')
check(!values.get(API_KEYS_STORAGE)!.includes(first.secret), 'Full secret is never persisted')
check(listApiKeys(storage)[0].id === first.key.id, 'Metadata survives a reload')
const second = createApiKey('Development assistant', storage)
check(first.secret !== second.secret && first.key.id !== second.key.id, 'Repeated creation generates unique keys and IDs')
check(!('environment' in second.key) && !('lastUsedAt' in second.key), 'Creation stores only name, masked key, ID and creation date')
revokeApiKey(first.key.id, storage)
check(listApiKeys(storage).length === 1 && listApiKeys(storage)[0].id === second.key.id, 'Revocation preserves other keys')
revokeApiKey(first.key.id, storage)
check(listApiKeys(storage).length === 1, 'Repeated revocation is harmless')
values.set(API_KEYS_STORAGE, JSON.stringify({ version: 1, keys: [{ ...second.key, environment: 'Development', lastUsedAt: null }] }))
check(listApiKeys(storage)[0].id === second.key.id, 'Previously valid v1 metadata remains readable')
const third = createApiKey('x'.repeat(100), storage)
check(listApiKeys(storage).some((key) => key.id === second.key.id), 'Creation preserves previously saved keys')
check(third.key.name.length === 100, 'Maximum name length is accepted')
revokeApiKey(third.key.id, storage)
const saved = values.get(API_KEYS_STORAGE)!
rejects(() => createApiKey('  ', storage), 'Blank names rejected')
rejects(() => createApiKey('x'.repeat(101), storage), 'Oversized names rejected')
check(values.get(API_KEYS_STORAGE) === saved, 'Invalid creation leaves metadata unchanged')

for (const raw of ['{', 'null', '{}', '{"version":2,"keys":[]}', JSON.stringify({ version: 1, keys: [{ ...second.key, createdAt: 'yesterday' }] }),
  JSON.stringify({ version: 1, keys: [{ ...second.key, maskedKey: second.secret }] }),
  JSON.stringify({ version: 1, keys: [second.key, second.key] })]) {
  values.set(API_KEYS_STORAGE, raw)
  rejects(() => listApiKeys(storage), 'Malformed storage fails visibly')
  rejects(() => createApiKey('New key', storage), 'Creation never overwrites malformed storage')
  rejects(() => revokeApiKey(second.key.id, storage), 'Revocation never overwrites malformed storage')
  check(values.get(API_KEYS_STORAGE) === raw, 'Malformed metadata is preserved for recovery')
}
const blockedStorage = {
  getItem: () => { throw new Error('Storage disabled') },
  setItem: () => { throw new Error('Storage disabled') },
}
rejects(() => listApiKeys(blockedStorage), 'Blocked reads surface failure')
rejects(() => createApiKey('New key', blockedStorage), 'Blocked storage cannot issue a key')
values.set(API_KEYS_STORAGE, saved)
rejects(() => createApiKey('New key', { ...storage, setItem: () => { throw new Error('Quota exceeded') } }), 'Failed persistence never returns a new secret')
rejects(() => revokeApiKey(second.key.id, { ...storage, setItem: () => { throw new Error('Quota exceeded') } }), 'Failed revocation surfaces failure')
check(values.get(API_KEYS_STORAGE) === saved, 'Failed writes preserve existing metadata')
console.log('API key selfcheck passed: lifecycle, secret handling, validation, and storage failures')
