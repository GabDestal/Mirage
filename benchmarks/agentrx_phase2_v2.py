"""Separate provenance-only correction; v1 source/prompts/outcomes stay intact."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from benchmarks import agentrx_phase2 as lane

V1_OUTPUT = lane.OUTPUT
OUTPUT = V1_OUTPUT / 'v2/families'
VERSION = 'within_seen_domain_unseen_task_families_provenance_v2'
DYNAMIC_SOURCES = ('instruction', 'trace', 'policy', 'tool_schema')
STATIC_SOURCES = ('policy', 'tool_schema')
EXPECTED_CASES = {
    'magentic:557e78eceec08ca8b0da5f9fdaca6e1c7ec6140a8ce600983ee716327dab005e',
    'magentic:56137764-b4e0-45b8-9c52-1866420c3df5',
    'magentic:57d9dc6935e8a40b02e7f8ec81768fe70e68a0c05f6866927c9fda38db38a486',
    'magentic:5d0080cb-90d7-4712-bc33-848150e917d3',
    'magentic:6b06d186921b8b390c65aebd0d16f09f60a47d2f1288ebe36953f734e84c0a3c',
    'magentic:6e3be83d1949fa52cba03fb1ce4b5b3bf7e37a83fd7d67694b10b2e439d90cf8',
}
LEDGER_SHA = 'fbcf19608a74e9387510d43431a6f7a65f2cc998ba0f07e61f88c8fefb5b49aa'
STATIC_SYSTEM = lane.STATIC_SYSTEM.replace('source (policy or tool_schema)',
    'source (nonempty array of unique exact enum literals policy or tool_schema)')
DYNAMIC_SYSTEM = lane.DYNAMIC_SYSTEM.replace('source (instruction or trace)',
    'source (nonempty array of unique exact enum literals instruction, trace, policy, or tool_schema)')
V1_CONSTRAINTS = lane.constraints


def constraints(text: str, kind: str, steps: int) -> list[dict]:
    value = lane.json_object(text)
    if set(value) != {'constraints'} or not isinstance(value['constraints'], list) or len(value['constraints']) > 4:
        raise ValueError('invalid_constraint_output')
    result = value['constraints']
    for i, item in enumerate(result, 1):
        expected = {'id', 'criterion', 'source'} | ({'source_steps'} if kind == 'dynamic' else set())
        if not isinstance(item, dict) or set(item) != expected or item['id'] != ('D' if kind == 'dynamic' else 'S') + str(i):
            raise ValueError('invalid_constraint_fields_or_id')
        if not isinstance(item['criterion'], str) or not item['criterion'].strip():
            raise ValueError('missing_constraint_criterion')
        sources = DYNAMIC_SOURCES if kind == 'dynamic' else STATIC_SOURCES
        source = item['source']
        members = (source,) if type(source) is str else source
        if not isinstance(members, (list, tuple)) or not members or any(type(s) is not str or s not in sources for s in members):
            raise ValueError('invalid_constraint_source')
        if len(set(members)) != len(members):
            raise ValueError('invalid_constraint_source')
        if kind == 'dynamic':
            lane.indices(item['source_steps'], steps)
    return result


def activate():
    lane.OUTPUT = OUTPUT
    lane.CODE_FILES = (*lane.CODE_FILES, 'benchmarks/agentrx_phase2_v2.py')
    lane.constraints = constraints


def v1_pins() -> dict:
    paths = [Path(p) for p in lane.CODE_FILES if 'phase2_v2' not in p]
    for folder in (V1_OUTPUT, V1_OUTPUT / 'families'):
        paths.extend(folder / name for name in ('manifest.json', 'selection-frozen.json', 'eligibility-ledger.json', 'rows.jsonl', 'report.json'))
        paths.extend((folder / 'stages').glob('*/*.json'))
        paths.extend((folder / 'native_scores').glob('*.json'))
    paths.extend((V1_OUTPUT / 'opus-reference') / name for name in ('manifest.json', 'selection-frozen.json', 'eligibility-ledger.json'))
    return lane.hashes(paths)


def prepare(native: Path, cohort: str):
    if (OUTPUT / 'manifest.json').exists():
        raise ValueError('v2_protocol_already_frozen')
    predecessor = V1_OUTPUT / 'families/eligibility-ledger.json'
    if lane.base.digest(predecessor.read_bytes()) != LEDGER_SHA:
        raise ValueError('blind_predecessor_ledger_mismatch')
    previous = lane.base.read_json(V1_OUTPUT / 'families/manifest.json')
    for field in ('native_pins', 'code_pins', 'phase1_pins'):
        lane.verify_hashes(previous[field])
    if lane.base.revision(native) != lane.base.SOURCE_SHA:
        raise ValueError('source_revision_mismatch')
    ledger = copy.deepcopy(lane.base.read_json(predecessor))
    old_groups = {r['family_id'] for r in previous['rows']}
    candidates = {}
    for item in ledger['records']:
        item['selected'] = False
        item['phase2_v1_exposed_family'] = item['family_id'] in old_groups
        item['exclusion_reasons'] = [r for r in item['exclusion_reasons'] if r != 'nonrepresentative_variant_or_fixed_family_cap']
        if item['phase2_v1_exposed_family']:
            item['eligible'] = False
            item['exclusion_reasons'].append('phase2_v1_exposed_family')
        if item['eligible']:
            candidates.setdefault(item['family_id'], []).append(item)
    representatives = sorted((min(items, key=lambda r: r['case_id']) for items in candidates.values()), key=lambda r: r['case_id'])[:6]
    if len(candidates) != 20 or {r['case_id'] for r in representatives} != EXPECTED_CASES:
        raise ValueError('C2_next_six_independent_selection_mismatch')
    selected_cases = EXPECTED_CASES
    split = 'within_seen_domain_heldout_task_families_v2'
    if cohort == 'development':
        ledger = copy.deepcopy(lane.base.read_json(V1_OUTPUT / 'eligibility-ledger.json'))
        selected_cases = {'tau:2', 'tau:3'}
        representatives = [r for r in ledger['records'] if r['case_id'] in selected_cases]
        split = 'development_same_case_v2'
    for item in ledger['records']:
        item['selected'] = item['case_id'] in selected_cases
        item['split'] = split if item['selected'] else 'exposed_or_ineligible'
        if item.get('eligible') and not item['selected']:
            item['exclusion_reasons'].append('nonrepresentative_variant_or_fixed_family_cap')
    ledger.update(created_at=lane.now(), cohort=VERSION + '_' + cohort, selected_cases=sorted(selected_cases),
                  selected_families=sorted(r['family_id'] for r in representatives),
                  predecessor_ledger_sha=LEDGER_SHA, excluded_v1_family_ids=sorted(old_groups),
                  annotation_metric_values='NOT_OPENED_BY_SELECTION', remaining_eligible_families=20)
    # Complete immutable structural/availability ledger precedes every v2 model output.
    lane.base.write_json(OUTPUT / 'selection-frozen.json', ledger)
    lane.base.write_json(OUTPUT / 'eligibility-ledger.json', ledger)
    preservation = v1_pins()
    lane.base.write_json(OUTPUT / 'v1-preservation.json', preservation)
    models = list(dict.fromkeys(r['model_id'] for r in previous['rows']))
    rows = []
    for item in representatives:
        data = lane.payload(native, item)
        if lane.base.digest(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()) != item['payload_sha']:
            raise ValueError('released_payload_mismatch')
        for model in models:
            for arm in lane.STAGES:
                rows.append({**dict.fromkeys(lane.base.FIELDS),
                    **{k: item[k] for k in ('native_id', 'domain', 'case_id', 'trace_path', 'label_path', 'policy_path', 'payload_sha', 'family_id', 'trace_messages', 'annotation_record_present')},
                    'benchmark': 'AgentRx', 'split': split, 'cohort': VERSION + '_' + cohort,
                    'policy_version': VERSION, 'model_id': model, 'parameters': lane.base.parameters(model),
                    'arm': arm, 'source_sha': lane.base.SOURCE_SHA, 'code_sha': lane.base.revision(Path.cwd()),
                    'calls': 0, 'evidence_refs': [], 'status': 'not_run', 'native_scores': {},
                    'unknown_reason': 'awaiting_explicit_root_lease'})
    systems = {**previous['systems'], 'static': STATIC_SYSTEM, 'dynamic': DYNAMIC_SYSTEM}
    manifest = {**previous, 'created_at': lane.now(), 'code_sha': lane.base.revision(Path.cwd()),
        'rows': rows, 'fixed_cells': len(rows), 'maximum_calls': len(representatives) * len(models) * 5,
        'fresh_heldout_cases': 0 if cohort == 'development' else 6,
        'cohort_limitation': 'same-case development re-evaluation only' if cohort == 'development' else previous['cohort_limitation'],
        'code_pins': lane.hashes([Path(p) for p in (*lane.CODE_FILES, 'benchmarks/agentrx_phase2_v2.py')]),
        'systems': systems, 'system_hashes': {k: lane.base.digest(v.encode()) for k, v in systems.items()},
        'selection_sha': lane.base.digest((OUTPUT / 'selection-frozen.json').read_bytes()),
        'eligibility_sha': lane.base.digest((OUTPUT / 'eligibility-ledger.json').read_bytes()),
        'v1_preservation_sha': lane.base.digest((OUTPUT / 'v1-preservation.json').read_bytes()),
        'predecessor_ledger_sha': LEDGER_SHA,
        'change': 'Canonical single literal or nonempty unique source array; static policy/schema and dynamic all four supplied inputs. No free-text splitting/coercion/rescoring.'}
    manifest.pop('family_freeze_sha', None)
    lane.base.write_json(OUTPUT / 'manifest.json', manifest)
    lane.verify_hashes(preservation)
    print(json.dumps({'fixed_cells': len(rows), 'maximum_calls': manifest['maximum_calls'], 'selected_cases': sorted(selected_cases),
                      'manifest_sha': lane.base.digest((OUTPUT / 'manifest.json').read_bytes())}))


def report():
    original = lane.base.write_json
    def write(path, value):
        if Path(path) in (Path('docs/BENCHMARKMAXXING_PHASE2_AGENTRX.json'), Path('docs/BENCHMARKMAXXING_PHASE2_AGENTRX_FAMILIES.json')):
            suffix = 'DEV' if OUTPUT.name == 'development' else 'FAMILIES'
            path = Path('docs/BENCHMARKMAXXING_PHASE2_AGENTRX_V2_' + suffix + '.json')
        original(path, value)
    lane.base.write_json = write
    try:
        lane.report()  # Same metric/bounds logic; only the document destination differs.
    finally:
        lane.base.write_json = original
    lane.verify_hashes(lane.base.read_json(OUTPUT / 'v1-preservation.json'))


def self_check():
    def rejects(text, kind, steps):
        try:
            constraints(text, kind, steps)
        except ValueError:
            return
        raise AssertionError('invalid source or citation admitted')
    saved_dynamic = lane.base.read_json(V1_OUTPUT / 'stages/1d129f77b07abb08/dynamic.json')
    result = constraints(saved_dynamic['raw_model_text'], 'dynamic', len(saved_dynamic['user_payload']['trace']))
    assert any(item['source'] == 'policy' for item in result)
    saved_static = next(lane.base.read_json(p) for p in sorted((V1_OUTPUT / 'families/stages').glob('*/static.json'))
                        if 'haiku' in lane.base.read_json(p)['model_id'])
    rejects(saved_static['raw_model_text'], 'static', 1)
    synthetic = copy.deepcopy(lane.json_object(saved_static['raw_model_text']))
    for item in synthetic['constraints']:
        if item['source'] == 'policy and tool_schema':
            item['source'] = ['policy', 'tool_schema']  # Test fixture only, never runtime coercion.
    result = constraints(json.dumps(synthetic), 'static', 1)
    assert any(item['source'] == ['policy', 'tool_schema'] for item in result)
    for source in ('label', 'unknown', 'policy & tool_schema', 'policy and tool_schema', [], ['policy', 'policy'], ['policy', 'label'], None):
        rejects(json.dumps({'constraints': [{'id': 'S1', 'criterion': 'x', 'source': source}]}), 'static', 1)
    for source in ('label', 'expected_answer', 'policy and tool_schema'):
        rejects(json.dumps({'constraints': [{'id': 'D1', 'criterion': 'x', 'source': source, 'source_steps': [1]}]}), 'dynamic', 1)
    rejects('{"constraints":[{"id":"D1","criterion":"x","source":"policy","source_steps":[0]}]}', 'dynamic', 1)
    assert lane.base.SYSTEM_PROMPT == lane.base.read_json(V1_OUTPUT / 'families/manifest.json')['systems']['diagnosis']
    development = lane.base.read_json(V1_OUTPUT / 'eligibility-ledger.json')
    assert all('annotation_record_present' in r for r in development['records'] if r['case_id'] in {'tau:2', 'tau:3'})
    print('v2 saved-development provenance compatibility and strict source/citation checks passed; no rescoring')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'self-check', 'verify', 'report', 'run'))
    parser.add_argument('--native', type=Path, default=lane.ROOT / 'agentrx/native')
    parser.add_argument('--env', type=Path, default=Path('/Users/liamszefner/Business/hacks/Mirage/.env'))
    parser.add_argument('--lease', type=Path)
    parser.add_argument('--cohort', choices=('development', 'families'), default='families')
    args = parser.parse_args()
    OUTPUT = V1_OUTPUT / 'v2' / args.cohort
    if args.command == 'prepare':
        prepare(args.native, args.cohort)
    elif args.command == 'self-check':
        self_check()
    else:
        activate()
        if args.command == 'run':
            lane.run(args.native, args.lease, args.env)
        elif args.command == 'report':
            report()
        else:
            lane.validate_protocol(args.native, lane.base.read_json(OUTPUT / 'manifest.json'))
            lane.verify_hashes(lane.base.read_json(OUTPUT / 'v1-preservation.json'))
            print('v2/source/selection/phase1/v1 preservation pins verified')
