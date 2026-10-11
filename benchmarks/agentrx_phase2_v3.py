"""AgentRx phase2 v3: evidence-stage parsing that lets assisted diagnosis finish.

v1/v2 code, prompts, manifests and outcomes stay untouched. The diagnosis system prompt
and the native grader are unchanged; only evidence parsing and degradation differ:
lenient JSON extraction, abstention scored wrong, partial checks marked UNKNOWN, invalid
constraints dropped with counts, failed evidence stages degrade instead of aborting.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import time

from benchmarks import agentrx_phase2 as lane
from benchmarks import agentrx_phase2_v2 as v2

base = lane.base
VERSION = 'agentrx-phase2-v3-lenient-evidence'
OUTPUT = Path('benchmarks/artifacts/agentrx_v3')
COHORTS = {'development': 'development', 'families': 'heldout_families'}
CODE_FILES = ('benchmarks/agentrx.py', 'benchmarks/agentrx_phase2.py',
              'benchmarks/agentrx_phase2_v2.py', 'benchmarks/agentrx_phase2_v3.py')
SOURCES = {'static': v2.STATIC_SOURCES, 'dynamic': v2.DYNAMIC_SOURCES}
STATUS = {'CLEAR_FAIL': 'FAIL', 'CLEAR_PASS': 'PASS', 'UNCLEAR': 'UNKNOWN'}
METRICS = (('critical_step_correct', 'critical_failure_step'), ('root_cause_correct', 'failure_category'))


def json_object(text: str) -> dict:
    start = text.find('{')
    if start < 0:
        raise ValueError('no_json_object')
    value, _ = json.JSONDecoder().raw_decode(text[start:])  # Ignores fences and trailing prose.
    if not isinstance(value, dict):
        raise ValueError('invalid_json_object')
    return value


def constraints(text: str, kind: str, steps: int):
    items = json_object(text).get('constraints')
    if not isinstance(items, list):
        raise ValueError('invalid_constraint_output')
    kept, dropped = [], Counter({'over_four_cap': max(0, len(items) - 4)} if len(items) > 4 else {})
    expected = {'id', 'criterion', 'source'} | ({'source_steps'} if kind == 'dynamic' else set())
    for item in items[:4]:
        try:
            if not isinstance(item, dict) or set(item) != expected or type(item['id']) is not str \
                    or not item['id'].startswith('D' if kind == 'dynamic' else 'S') or item['id'] in {k['id'] for k in kept}:
                raise ValueError('invalid_constraint_fields_or_id')
            if not isinstance(item['criterion'], str) or not item['criterion'].strip():
                raise ValueError('missing_constraint_criterion')
            members = (item['source'],) if type(item['source']) is str else item['source']
            if not isinstance(members, (list, tuple)) or not members or any(type(s) is not str or s not in SOURCES[kind] for s in members) \
                    or len(set(members)) != len(members):
                raise ValueError('invalid_constraint_source')
            if kind == 'dynamic':
                lane.indices(item['source_steps'], steps)
            kept.append(item)
        except (ValueError, TypeError) as error:
            dropped[str(error)] += 1
    return kept, dict(dropped)


def checks(text: str, rules: list[dict], steps: int):
    items = json_object(text).get('checks')
    if not isinstance(items, list):
        raise ValueError('invalid_checker_output')
    ids, valid = {r['id'] for r in rules}, {}
    for item in items:
        try:
            if not isinstance(item, dict) or set(item) != {'id', 'evaluation', 'evidence_steps', 'reasoning'} \
                    or item['id'] not in ids or item['id'] in valid or item['evaluation'] not in STATUS:
                raise ValueError('invalid_check')
            lane.indices(item['evidence_steps'], steps)
            if not isinstance(item['reasoning'], str) or not item['reasoning'].strip():
                raise ValueError('missing_checker_reasoning')
            valid[item['id']] = {**item, 'status': STATUS[item['evaluation']]}
        except (ValueError, TypeError):
            pass
    result = [valid.get(r['id']) or {'id': r['id'], 'evaluation': 'UNCLEAR', 'status': 'UNKNOWN', 'evidence_steps': [],
                                     'reasoning': 'missing_or_invalid_in_checker_output'} for r in rules]
    return result, sum(r['id'] not in valid for r in rules)


def diagnosis(text: str, steps: int) -> dict:
    result = base.parse_prediction(json.dumps(json_object(text)), steps)
    if set(result) != {'critical_failure_step', 'failure_category', 'explanation', 'evidence_steps'}:
        raise ValueError('invalid_diagnosis_fields')
    if not isinstance(result['explanation'], str) or not result['explanation'].strip():
        raise ValueError('missing_diagnosis_explanation')
    if not (result['critical_failure_step'] is None and result['evidence_steps'] == []):
        lane.indices(result['evidence_steps'], steps)
    return result


def score(native: Path, row: dict, final: dict, destination: Path) -> dict:
    scores = base.score(native, row, final, destination)
    with tempfile.TemporaryDirectory() as folder:  # Probe only reveals whether a native label exists.
        probe = base.score(native, row, {'critical_failure_step': 1, 'failure_category': 1}, Path(folder) / 'probe.json')
    for metric, field in METRICS:
        if final.get(field) is None and probe[metric] is not None:
            scores[metric] = False  # Abstaining against an existing native label is wrong, not UNKNOWN.
    return scores


def code_pins() -> dict:
    return {p: base.digest(Path(p).read_bytes()) for p in CODE_FILES}


def require_clean():
    if subprocess.check_output(['git', 'status', '--porcelain', '--', *CODE_FILES], text=True).strip():
        raise ValueError('uncommitted_diagnostic_code')


def prepare(native: Path, cohort: str, stop_at: str):
    out = OUTPUT / cohort
    if (out / 'manifest.json').exists():
        raise ValueError('v3_protocol_already_frozen')
    require_clean()
    if base.revision(native) != base.SOURCE_SHA:
        raise ValueError('source_revision_mismatch')
    v2_manifest = lane.OUTPUT / 'v2' / cohort / 'manifest.json'
    previous = base.read_json(v2_manifest)
    lane.verify_hashes(previous['native_pins'])
    assert previous['systems']['diagnosis'] == base.SYSTEM_PROMPT
    sha = base.revision(Path.cwd())
    rows = [{**r, 'split': COHORTS[cohort], 'cohort': VERSION + '_' + cohort, 'policy_version': VERSION,
             'code_sha': sha, 'v2_cohort': r['cohort']} for r in previous['rows']]
    manifest = {'created_at': lane.now(), 'source_sha': base.SOURCE_SHA, 'code_sha': sha, 'rows': rows,
                'fixed_cells': len(rows), 'maximum_calls': sum(len(lane.STAGES[r['arm']]) for r in rows),
                'stages': lane.STAGES, 'output_token_caps': lane.CAPS, 'stop_at': stop_at,
                'native_pins': previous['native_pins'], 'native_function_hashes': lane.function_pins(native),
                'code_pins': code_pins(), 'systems': previous['systems'],
                'system_hashes': {k: base.digest(v.encode()) for k, v in previous['systems'].items()},
                'rubric': lane.rubric(native), 'v2_manifest_sha': base.digest(v2_manifest.read_bytes()),
                'authorization': 'coordinator dispatch task_d7f79d308a97 (user-authorized Bedrock push)',
                'comparison': previous['comparison'],
                'changes': ['raw_decode JSON from first "{" for every stage', 'null step with [] evidence accepted; abstention scored wrong when a native label exists',
                            'missing/invalid checker entries become UNKNOWN checks (counted)', 'invalid or compound constraints dropped (counted by reason)',
                            'evidence-stage failure continues to diagnosis with available evidence, evidence_degraded=true',
                            'diagnosis prompt, native grader, caps, parameters and one call per stage unchanged; no retries']}
    base.write_json(out / 'manifest.json', manifest)
    print(json.dumps({'cohort': cohort, 'fixed_cells': len(rows), 'maximum_calls': manifest['maximum_calls'], 'stop_at': stop_at}))


def validate(native: Path, manifest: dict):
    if base.revision(native) != base.SOURCE_SHA or lane.function_pins(native) != manifest['native_function_hashes']:
        raise ValueError('native_source_mismatch')
    lane.verify_hashes(manifest['native_pins'])
    if code_pins() != manifest['code_pins']:
        raise ValueError('code_pin_mismatch')
    require_clean()


def run(native: Path, cohort: str, model: str, env: Path):
    out = OUTPUT / cohort
    manifest = base.read_json(out / 'manifest.json')
    validate(native, manifest)
    deadline = datetime.fromisoformat(manifest['stop_at'])
    result_file = out / ('rows-' + model.split('.')[1].split('-')[0] + '.jsonl')
    existing = [json.loads(line) for line in result_file.read_text().splitlines()] if result_file.exists() else []
    done = {(r['case_id'], r['arm']) for r in existing}
    from dotenv import load_dotenv
    load_dotenv(env)
    import boto3
    from botocore.config import Config
    client = boto3.client('bedrock-runtime', region_name='us-east-1',
                         config=Config(connect_timeout=10, read_timeout=120, retries={'total_max_attempts': 1}))
    for selected in manifest['rows']:
        if selected['model_id'] != model or (selected['case_id'], selected['arm']) in done:
            continue  # No retry-until-pass or overwrite of recorded outcomes.
        if datetime.now(timezone.utc) >= deadline:
            break  # Unrun cells stay in the fixed denominator as UNKNOWN.
        row = {**selected, 'code_sha': base.revision(Path.cwd()), 'calls': 0, 'stages': [], 'native_scores': {},
               'unknown_reason': None, 'evidence_degraded': False, 'degraded_reasons': [],
               'dropped_constraints': {}, 'missing_checks': 0, 'evidence_refs': []}
        data = lane.payload(native, row)
        if base.digest(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()) != row['payload_sha']:
            raise ValueError('payload_pin_mismatch')
        started, generated, checked, final = time.monotonic(), [], [], None
        stem = base.digest((row['case_id'] + row['model_id'] + row['arm']).encode())[:16]
        for stage in lane.STAGES[row['arm']]:
            if stage == 'checker' and not generated:
                row['evidence_degraded'] = True
                row['degraded_reasons'].append('checker_skipped:no_valid_constraints')
                continue
            artifact = out / 'stages' / stem / (stage + '.json')
            if artifact.exists():
                raise ValueError('existing_stage_no_retry:' + str(artifact))
            parameters = {**row['parameters'], 'inferenceConfig': {**row['parameters']['inferenceConfig'], 'maxTokens': lane.CAPS[stage]}}
            if stage == 'diagnosis':
                request = {**data, **({'invariant_evidence': {'constraints': generated, 'checks': checked}} if generated else {})}
            else:
                request = lane.stage_input(stage, data, native, row['domain'], generated, checked)
            system = manifest['systems'][stage]
            record = {'stage': stage, 'status': 'attempting', 'calls': 0, 'model_id': row['model_id'], 'case_id': row['case_id'],
                      'arm': row['arm'], 'parameters': parameters, 'system_prompt': system, 'user_payload': request,
                      'prompt_sha': base.digest((system + json.dumps(request, ensure_ascii=False)).encode()),
                      'code_sha': row['code_sha'], 'usage': None, 'stop_reason': None, 'error': None}
            base.write_json(artifact, record)
            call_started = time.monotonic()
            try:
                if datetime.now(timezone.utc) >= deadline:
                    raise TimeoutError('deadline_before_stage')
                record['calls'] = 1
                row['calls'] += 1
                response = client.converse(modelId=row['model_id'], system=[{'text': system}],
                    messages=[{'role': 'user', 'content': [{'text': json.dumps(request, ensure_ascii=False)}]}], **parameters)
                record.update(usage=response.get('usage'), stop_reason=response.get('stopReason'))
                text = record['raw_model_text'] = ''.join(b.get('text', '') for b in response['output']['message']['content'])
                if response.get('stopReason') not in ('end_turn', 'stop_sequence'):
                    raise ValueError('incomplete_stage_stop_reason:' + str(response.get('stopReason')))
                if stage in ('static', 'dynamic'):
                    parsed, record['dropped'] = constraints(text, stage, len(data['trace']))
                    generated.extend(parsed)
                    for reason, count in record['dropped'].items():
                        row['dropped_constraints'][reason] = row['dropped_constraints'].get(reason, 0) + count
                elif stage == 'checker':
                    checked, record['missing_checks'] = checks(text, generated, len(data['trace']))
                    row['missing_checks'] += record['missing_checks']
                    parsed = checked
                else:
                    parsed = final = diagnosis(text, len(data['trace']))
                record.update(parsed=parsed, status='completed')
            except Exception as error:
                record.update(status='unknown', error={'type': type(error).__name__, 'message': str(error)})
            record['latency_s'] = round(time.monotonic() - call_started, 3)
            base.write_json(artifact, record)
            row['stages'].append({k: record[k] for k in ('stage', 'status', 'calls', 'usage', 'latency_s', 'stop_reason', 'error')})
            row['evidence_refs'].append(str(artifact))
            if record['status'] != 'completed':
                if stage == 'diagnosis':
                    row.update(status='unknown', unknown_reason='stage_failure:diagnosis')
                else:  # Degrade, never fall back silently: flagged and reported separately.
                    row['evidence_degraded'] = True
                    row['degraded_reasons'].append('stage_failure:' + stage)
            time.sleep(1.1)
        if final is not None:
            row['prediction'] = final
            try:
                row['native_scores'] = score(native, row, final, out / 'native_scores' / (stem + '.json'))
                row['status'] = 'completed'
                row['validation_method'] = 'released_native_label_loader_and_analysis; scorer_only'
            except Exception as error:
                row.update(status='unknown', unknown_reason='native_scoring_failure:' + type(error).__name__, scoring_error=str(error))
        row['latency_s'] = round(time.monotonic() - started, 3)
        with result_file.open('a') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(json.dumps({'case_id': row['case_id'], 'arm': row['arm'], 'status': row['status'], 'calls': row['calls'],
                          'degraded': row['evidence_degraded'], 'scores': {k: row['native_scores'].get(k) for k, _ in METRICS}}), flush=True)
        time.sleep(1.1)


def report():
    summary = {'generated_at': lane.now(), 'policy_version': VERSION, 'bounds': '[S/N, (S+U)/N]; not confidence intervals', 'cohorts': {}}
    for cohort, split in COHORTS.items():
        out = OUTPUT / cohort
        if not (out / 'manifest.json').exists():
            continue
        manifest = base.read_json(out / 'manifest.json')
        observed = {(r['case_id'], r['model_id'], r['arm']): r for p in sorted(out.glob('rows-*.jsonl'))
                    for r in map(json.loads, p.read_text().splitlines())}
        tables = []
        for model in sorted({r['model_id'] for r in manifest['rows']}):
            for arm in lane.STAGES:
                cells = [observed.get((r['case_id'], model, arm), {'status': 'not_run'})
                         for r in manifest['rows'] if r['model_id'] == model and r['arm'] == arm]
                entry = {'model_id': model, 'arm': arm, 'N': len(cells), 'attempted': sum(c['status'] != 'not_run' for c in cells),
                         'completed': sum(c['status'] == 'completed' for c in cells),
                         'evidence_degraded': sum(bool(c.get('evidence_degraded')) for c in cells),
                         'dropped_constraints': sum(sum(c.get('dropped_constraints', {}).values()) for c in cells),
                         'missing_checks': sum(c.get('missing_checks', 0) for c in cells),
                         'calls': sum(c.get('calls', 0) for c in cells)}
                for metric, _ in METRICS:
                    values = [c.get('native_scores', {}).get(metric) if c['status'] == 'completed' else None for c in cells]
                    s, scored = sum(v is True for v in values), sum(v is not None for v in values)
                    entry[metric] = {'S': s, 'N': len(cells), 'scored': scored, 'U': len(cells) - scored,
                                     'bounds': [s / len(cells), (s + len(cells) - scored) / len(cells)]}
                tables.append(entry)
        summary['cohorts'][cohort] = {'split': split, 'fixed_cells': len(manifest['rows']), 'stop_at': manifest['stop_at'],
                                      'code_sha': manifest['code_sha'], 'tables': tables}
    base.write_json(OUTPUT / 'summary.json', summary)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'report'))
    parser.add_argument('--native', type=Path, default=lane.ROOT / 'agentrx/native')
    parser.add_argument('--env', type=Path, default=Path('.env'))
    parser.add_argument('--cohort', choices=tuple(COHORTS), default='development')
    parser.add_argument('--model')
    parser.add_argument('--stop-at', default='2026-10-11T08:45:00+00:00')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.native, args.cohort, args.stop_at)
    elif args.command == 'run':
        run(args.native, args.cohort, args.model, args.env)
    else:
        report()
