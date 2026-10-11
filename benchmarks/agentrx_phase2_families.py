"""Offline, label-value-blind family selection for a separate within-domain lane."""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import re

from benchmarks import agentrx_phase2 as lane

FAMILY_COHORT = 'within_seen_domain_unseen_task_families_v1'
MAX_CASES = 6
MAX_PAYLOAD_CHARACTERS = 100000


def structure(instruction: str) -> str:
    # Source attachments are not the task identity; runtime still receives the full trace.
    instruction = instruction.split('Here are the file', 1)[0]
    text = re.sub(r'https?://\S+', ' RESOURCE ', instruction)
    text = re.sub(r'\b[A-Z][A-Za-z]*(?:[ -][A-Z][A-Za-z]*)*\b', ' ENTITY ', text)
    text = re.sub(r'\d+(?:[./:%-]\d+)*', ' NUMBER ', text)
    text = re.sub(r'["“][^"”]+["”]', ' QUOTED ', text)
    return ' '.join(re.findall(r'[a-z]+', text.lower()))


def related(a: str, b: str) -> bool:
    if not a or not b:
        return False
    left, right = set(a.split()), set(b.split())
    overlap = len(left & right) / len(left | right)
    return a == b or overlap >= 0.48 or SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.72


def families(records: list[dict]) -> list[list[int]]:
    """Conservative transitive components, independent of annotations/outcomes."""
    parent = list(range(len(records)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, left in enumerate(records):
        for j, right in enumerate(records[:i]):
            if left['domain'] != right['domain']:
                continue
            # Tau first messages under-specify simulator intent: exclude whole domain.
            if left['domain'] == 'tau' or related(left['instruction_structure'], right['instruction_structure']):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(records)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def prepare(native: Path):
    development = lane.base.read_json(lane.OUTPUT / 'manifest.json')
    output = lane.OUTPUT / 'families'
    if (output / 'families-frozen.json').exists() or (output / 'manifest.json').exists():
        raise ValueError('family_protocol_already_frozen')
    lane.validate_protocol(native, development)
    original = lane.base.read_json(lane.OUTPUT / 'selection-frozen.json')
    exposed = {r['case_id'] for p in (lane.ROOT / 'agentrx').glob('**/manifest.json')
               if 'native' not in p.relative_to(lane.ROOT / 'agentrx').parts
               for r in lane.base.read_json(p).get('rows', [])}
    records = []
    for entry in original['records']:
        item = {**entry, 'selected': False, 'annotation_metric_values': 'NOT_OPENED'}
        try:
            data = lane.payload(native, item)
            item.update(instruction_structure=structure(data['instruction']),
                        payload_characters=len(json.dumps(data, ensure_ascii=False)),
                        structurally_eligible=bool(data['instruction']))
        except Exception as error:
            item.update(instruction_structure='', payload_characters=None, structurally_eligible=False,
                        structural_error=type(error).__name__ + ':' + str(error))
        records.append(item)
    group_ledger = []
    for members in families(records):
        ids = sorted(records[i]['case_id'] for i in members)
        family_id = lane.base.digest(json.dumps(ids).encode())[:16]
        seen = bool(set(ids) & exposed)
        group_ledger.append({'family_id': family_id, 'members': ids, 'phase1_exposed': seen})
        for i in members:
            records[i].update(family_id=family_id, phase1_exposed_family=seen)
    frozen = {'created_at': lane.now(), 'source_sha': lane.base.SOURCE_SHA,
              'cohort': FAMILY_COHORT, 'selection_maximum_families': MAX_CASES,
              'structural_eligibility': 'Nonempty released instruction and full raw payload <=100000 characters. No truncation; annotation record presence required, metric values unused.',
              'family_rule': 'Same domain; normalize capitalized spans, URLs, quoted spans and numbers; token-set Jaccard >=0.48 OR character SequenceMatcher >=0.72 OR exact match; transitive closure. Tau is one conservative family due underspecified initial simulator messages. Attachment contents excluded only from grouping.',
              'selection_rule': 'Exclude every component intersecting any phase1-selected case, unsupported/oversize/missing-record cases; one lexicographically first eligible case per family, then first six representatives by case_id. Fixed before any annotation values/outcomes; no replacements.',
              'independence_limit': 'Operational structural families within seen domains. Lexical grouping does not prove all semantic paraphrases independent; no unseen-domain or broad-generalization claim.',
              'phase1_exposed_cases': sorted(exposed), 'groups': group_ledger, 'records': records}
    lane.base.write_json(output / 'families-frozen.json', frozen)  # Family identity before annotation record access.
    annotation_ids = {p: set(str(json.loads(v)) for v in re.findall(r'"trajectory_id"\s*:\s*("[^"\\]*"|\d+)', (native / p).read_text()))
                      for p in {r['label_path'] for r in records}}
    candidates = {}
    for item in records:
        item['annotation_record_present'] = item['native_id'] in annotation_ids[item['label_path']]
        reasons = []
        if item['phase1_exposed_family']:
            reasons.append('phase1_exposed_family')
        if not item['structurally_eligible']:
            reasons.append('unsupported_structure')
        if item['payload_characters'] is not None and item['payload_characters'] > MAX_PAYLOAD_CHARACTERS:
            reasons.append('full_payload_exceeds_declared_character_cap')
        if not item['annotation_record_present']:
            reasons.append('missing_annotation_record')
        item.update(eligible=not reasons, exclusion_reasons=reasons, split='excluded' if reasons else 'within_seen_domain_heldout_task_families')
        if not reasons:
            candidates.setdefault(item['family_id'], []).append(item)
    representatives = sorted((min(members, key=lambda r: r['case_id']) for members in candidates.values()), key=lambda r: r['case_id'])[:MAX_CASES]
    chosen = {r['case_id'] for r in representatives}
    for item in records:
        item['selected'] = item['case_id'] in chosen
        if item['eligible'] and not item['selected']:
            item['exclusion_reasons'] = ['nonrepresentative_variant_or_fixed_family_cap']
    frozen['records'] = records
    frozen['selected_cases'] = sorted(chosen)
    frozen['selected_families'] = sorted(r['family_id'] for r in representatives)
    lane.base.write_json(output / 'eligibility-ledger.json', frozen)
    # Same runtime lane and stage settings; only case/cohort selection changes.
    models = list(dict.fromkeys(r['model_id'] for r in development['rows']))
    rows = []
    for item in representatives:
        for model in models:
            for arm in lane.STAGES:
                template = next(r for r in development['rows'] if r['model_id'] == model and r['arm'] == arm)
                rows.append({**dict.fromkeys(lane.base.FIELDS),
                             **{k: template[k] for k in ('benchmark', 'attack_id', 'model_id', 'parameters', 'policy_version', 'source_sha', 'arm')},
                             **{k: item[k] for k in ('native_id', 'domain', 'case_id', 'trace_path', 'label_path', 'policy_path', 'payload_sha', 'family_id', 'trace_messages', 'annotation_record_present')},
                             'split': 'within_seen_domain_heldout_task_families', 'cohort': FAMILY_COHORT,
                             'code_sha': lane.base.revision(Path.cwd()), 'calls': 0, 'evidence_refs': [],
                             'status': 'not_run', 'unknown_reason': 'awaiting_explicit_root_lease', 'native_scores': {}})
    manifest = {**development, 'created_at': lane.now(), 'code_sha': lane.base.revision(Path.cwd()),
                'rows': rows, 'fixed_cells': len(rows), 'maximum_calls': len(representatives) * len(models) * 5,
                'fresh_heldout_cases': len(representatives), 'cohort_limitation': frozen['independence_limit'],
                'family_freeze_sha': lane.base.digest((output / 'families-frozen.json').read_bytes()),
                'eligibility_sha': lane.base.digest((output / 'eligibility-ledger.json').read_bytes()),
                'selection_sha': lane.base.digest((output / 'families-frozen.json').read_bytes())}
    manifest.pop('supersedes_manifest_sha', None)
    lane.base.write_json(output / 'selection-frozen.json', lane.base.read_json(output / 'families-frozen.json'))
    lane.base.write_json(output / 'manifest.json', manifest)
    print(json.dumps({'fixed_cells': len(rows), 'maximum_calls': manifest['maximum_calls'],
                      'selected_cases': sorted(chosen), 'structural_groups': len(group_ledger),
                      'eligible_families': len(candidates), 'manifest': str(output / 'manifest.json')}))


def self_check():
    assert related(structure('How many shirts are available?'), structure('How many shirts are available?'))
    assert related(structure('Which gyms are within 5 miles of Mothman Museum?'), structure('Which gyms are within 3 miles of City Museum?'))
    assert related(structure('What is the highest rated Daniel Craig movie under 150 minutes?'), structure('What is the highest rated Isabelle Adjani movie under 120 minutes?'))
    rows = [{'domain': 'magentic', 'instruction_structure': 'alpha beta'},
            {'domain': 'magentic', 'instruction_structure': 'alpha beta gamma'},
            {'domain': 'magentic', 'instruction_structure': 'beta gamma'}]
    assert len(families(rows)) == 1
    assert len(families([{'domain': 'tau', 'instruction_structure': 'a'}, {'domain': 'tau', 'instruction_structure': 'b'}])) == 1
    print('structural variant normalization/transitive grouping self-check passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'self-check'))
    parser.add_argument('--native', type=Path, default=lane.ROOT / 'agentrx/native')
    args = parser.parse_args()
    if args.command == 'self-check':
        self_check()
    else:
        prepare(args.native)
