export type ApprovalScalar = string | number | boolean
export type ApprovalField = {
  name: string
  type: 'string' | 'number' | 'integer' | 'boolean'
  title: string
  description?: string
  required: boolean
  phrase?: string
  default?: ApprovalScalar
  enum?: ApprovalScalar[]
  const?: ApprovalScalar
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
  pattern?: string
  format?: 'email' | 'uri'
}

const isObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const metadata = ['title', 'description', '$schema']
const fieldKeys = [...metadata, 'type', 'default', 'enum', 'const', 'minLength', 'maxLength', 'minimum', 'maximum', 'pattern', 'format']
const unsupported = 'This confirmation form is not supported. Decline this request and ask Mirage for a supported form.'

/** Only accept constraints we can enforce; unknown schemas never enable approval. */
export function readApprovalSchema(schema: Record<string, unknown>): { fields: ApprovalField[]; error?: string } {
  if (schema.type !== 'object' || !isObject(schema.properties) ||
      Object.keys(schema).some(key => ![...metadata, 'type', 'properties', 'required', 'additionalProperties'].includes(key)) ||
      (schema.additionalProperties !== undefined && schema.additionalProperties !== false)) return { fields: [], error: unsupported }
  const required = schema.required ?? []
  if (!Array.isArray(required) || required.some(key => typeof key !== 'string' || !Object.hasOwn(schema.properties as object, key))) return { fields: [], error: unsupported }
  const fields: ApprovalField[] = []
  for (const [name, definition] of Object.entries(schema.properties)) {
    if (!isObject(definition) || Object.keys(definition).some(key => !fieldKeys.includes(key)) ||
        !['string', 'number', 'integer', 'boolean'].includes(String(definition.type))) return { fields: [], error: unsupported }
    const type = definition.type as ApprovalField['type']
    const scalar = (value: unknown) => type === 'string' ? typeof value === 'string' : type === 'boolean' ? typeof value === 'boolean' : typeof value === 'number' && Number.isFinite(value) && (type !== 'integer' || Number.isInteger(value))
    if (['title', 'description', 'pattern'].some(key => definition[key] !== undefined && typeof definition[key] !== 'string') ||
        ['default', 'const'].some(key => definition[key] !== undefined && !scalar(definition[key])) ||
        (definition.enum !== undefined && (!Array.isArray(definition.enum) || !definition.enum.length || definition.enum.some(value => !scalar(value)))) ||
        ['minLength', 'maxLength'].some(key => definition[key] !== undefined && (type !== 'string' || !Number.isInteger(definition[key]) || Number(definition[key]) < 0)) ||
        ['minimum', 'maximum'].some(key => definition[key] !== undefined && (!['number', 'integer'].includes(type) || typeof definition[key] !== 'number' || !Number.isFinite(definition[key]))) ||
        (definition.pattern !== undefined && type !== 'string') ||
        (definition.format !== undefined && (type !== 'string' || !['email', 'uri'].includes(String(definition.format))))) return { fields: [], error: unsupported }
    try { if (definition.pattern) new RegExp(String(definition.pattern)) } catch { return { fields: [], error: unsupported } }
    const title = String(definition.title ?? name)
    const phrase = title.match(/^Type "(.+)" to confirm$/)?.[1]
    fields.push({ ...definition, name, type, title, required: required.includes(name) || !!phrase, phrase } as ApprovalField)
  }
  return { fields }
}

export function validateApproval(fields: ApprovalField[], values: Record<string, ApprovalScalar>): string | undefined {
  for (const field of fields) {
    const value = values[field.name]
    const empty = value === undefined || (typeof value === 'string' && !value.trim())
    if (empty) { if (field.required) return `Enter ${field.title}.`; continue }
    if (field.phrase !== undefined && value !== field.phrase) return `Type "${field.phrase}" exactly to confirm.`
    if (field.const !== undefined && value !== field.const) return `${field.title} must match the requested value.`
    if (field.enum && !field.enum.includes(value)) return `Choose a listed value for ${field.title}.`
    if (field.type === 'string') {
      if (typeof value !== 'string') return `Enter text for ${field.title}.`
      if ((field.minLength !== undefined && value.length < field.minLength) || (field.maxLength !== undefined && value.length > field.maxLength) || (field.pattern && !new RegExp(field.pattern).test(value))) return `Check the requested format for ${field.title}.`
      if (field.format === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return `Enter a valid email for ${field.title}.`
      if (field.format === 'uri') { try { new URL(value) } catch { return `Enter a valid URL for ${field.title}.` } }
    } else if (field.type === 'boolean') {
      if (typeof value !== 'boolean') return `Choose a value for ${field.title}.`
    } else if (typeof value !== 'number' || !Number.isFinite(value) || (field.type === 'integer' && !Number.isInteger(value)) || (field.minimum !== undefined && value < field.minimum) || (field.maximum !== undefined && value > field.maximum)) return `Enter a valid number for ${field.title}.`
  }
}

export function approvalDefaults(fields: ApprovalField[]): Record<string, ApprovalScalar> {
  return Object.fromEntries(fields.filter(field => !field.phrase && field.default !== undefined).map(field => [field.name, field.default as ApprovalScalar]))
}
