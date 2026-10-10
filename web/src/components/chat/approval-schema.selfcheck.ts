import { approvalDefaults, readApprovalSchema, validateApproval } from './approval-schema.ts'

function check(condition: boolean, message: string) { if (!condition) throw new Error(message) }
const schema = { type: 'object', properties: {
  confirm: { type: 'string', title: 'Type "unfreeze run_002" to confirm' },
  reason: { type: 'string', title: 'Reason (logged in the audit trail)', default: 'False positive' },
  count: { type: 'integer', minimum: 1, maximum: 3 },
  allowed: { type: 'boolean' },
}, required: ['confirm', 'reason'] }
const { fields, error } = readApprovalSchema(schema)
check(!error && fields.length === 4, 'Actual MCP-style schema is supported')
check(approvalDefaults(fields).confirm === undefined, 'Never prefill the confirmation phrase')
check(!!validateApproval(fields, { reason: 'False positive' }), 'Missing phrase is rejected')
check(!!validateApproval(fields, { confirm: 'unfreeze run_002 ', reason: 'False positive' }), 'Phrase must match exactly')
check(!!validateApproval(fields, { confirm: 'unfreeze run_002', reason: '  ' }), 'Blank audit reason is rejected')
check(!validateApproval(fields, { confirm: 'unfreeze run_002', reason: 'False positive', allowed: false, count: 2 }), 'Typed scalars survive acceptance')
check(!!validateApproval(fields, { confirm: 'unfreeze run_002', reason: 'False positive', count: 1.5 }), 'Fractional integers are rejected')
check(!!validateApproval(fields, { confirm: 'unfreeze run_002', reason: 'False positive', count: 4 }), 'Bounds are enforced')
check(!!readApprovalSchema({ ...schema, required: ['unknown'] }).error, 'Unknown required fields fail closed')
check(!!readApprovalSchema({ ...schema, properties: { nested: { type: 'object' } } }).error, 'Nested schema fails closed')
check(!!readApprovalSchema({ ...schema, allOf: [] }).error, 'Unknown schema constraints fail closed')
check(!!readApprovalSchema({ type: 'object', properties: { text: { type: 'string', pattern: '[' } } }).error, 'Invalid pattern fails closed')
const enumFields = readApprovalSchema({ type: 'object', properties: { risk: { type: 'number', enum: [1, 2] }, email: { type: 'string', format: 'email' } } }).fields
check(!!validateApproval(enumFields, { risk: 3 }), 'Enum is enforced')
check(!!validateApproval(enumFields, { email: 'invalid' }), 'Format is enforced')
check(!validateApproval(enumFields, { risk: 1, email: 'synthetic@example.com' }), 'Valid enum and format pass')
check(!!validateApproval([{ name: 'constructor', type: 'string', title: 'constructor', required: true }], {}), 'Inherited properties do not satisfy required fields')
console.log('Approval selfcheck: 16 checks passed')
