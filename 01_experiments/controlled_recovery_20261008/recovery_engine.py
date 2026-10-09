"""Separate V8.8 research adapter. Does not alter frozen V5 measurements.

Snapshots contain regular-file bytes only. Proposals abort atomically. No shell,
AST, symlink, database, concurrent writer, or external-service semantics.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import PurePosixPath

OPS = {'write', 'delete', 'rename', 'copy', 'append', 'replace', 'assert_bytes'}

class Rejected(ValueError):
    pass

def path_ok(path):
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
        raise Rejected('path')
    p = PurePosixPath(path)
    if p.is_absolute() or path == '.' or p.as_posix() != path or any(x in {'..', '.git'} for x in p.parts):
        raise Rejected('path')
    return path

def schema(actions):
    if not isinstance(actions, list) or len(actions) > 64:
        raise Rejected('schema')
    for a in actions:
        if not isinstance(a, dict) or a.get('op') not in OPS:
            raise Rejected('operation')
        path_ok(a.get('path'))
        op = a['op']
        fields = {'op', 'path'}
        if op in {'copy', 'rename'}:
            path_ok(a.get('destination')); fields.add('destination')
            if a['path'] == a['destination']:
                raise Rejected('same_path')
        elif op in {'write', 'append'}:
            if not isinstance(a.get('content'), str): raise Rejected('content')
            fields.add('content')
        elif op == 'replace':
            if not isinstance(a.get('old'), str) or not a['old'] or not isinstance(a.get('new'), str):
                raise Rejected('replacement')
            if a['old'] == a['new']: raise Rejected('identical_arguments')
            fields.update({'old', 'new'})
        elif op == 'assert_bytes':
            if 'expected' not in a or a['expected'] is not None and not isinstance(a['expected'], str):
                raise Rejected('expected')
            fields.add('expected')
        if set(a) != fields: raise Rejected('unknown_field')
    return actions

def execute(state, actions):
    """No input mutation or successful-prefix exposure on any rejection."""
    schema(actions)
    out = dict(state)
    for p, v in out.items():
        path_ok(p)
        if not isinstance(v, bytes): raise Rejected('snapshot_value')
    for a in actions:
        p, op = a['path'], a['op']
        if op == 'write':
            out[p] = a['content'].replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
        elif op == 'delete':
            out.pop(p, None)
        elif op in {'rename', 'copy'}:
            if p not in out: raise Rejected('missing_path')
            value = out[p]
            if op == 'rename': del out[p]
            out[a['destination']] = value
        elif op == 'append':
            if p not in out: raise Rejected('missing_path')
            out[p] += a['content'].encode('utf-8')
        elif op == 'replace':
            if p not in out: raise Rejected('missing_path')
            old, new = a['old'].encode('utf-8'), a['new'].encode('utf-8')
            n = out[p].count(old)
            if n != 1: raise Rejected('old_text_absent' if not n else 'old_text_ambiguous')
            out[p] = out[p].replace(old, new, 1)
        elif op == 'assert_bytes':
            expected = None if a['expected'] is None else a['expected'].encode('utf-8')
            if out.get(p) != expected: raise Rejected('guard_failed')
    return out

def attempt(state, actions):
    try: return execute(state, actions), None
    except Rejected as e: return None, str(e)

def project(base, state, allowed, checkpoint=None):
    checkpoint = checkpoint or {}
    if set(checkpoint) - set(allowed): raise Rejected('checkpoint_scope')
    out = {}
    for p in set(base) | set(state) | set(checkpoint):
        value = checkpoint[p] if p in checkpoint else state.get(p) if p in allowed else base.get(p)
        if value is not None: out[p] = value
    return out

def is_constant(actions):
    try: schema(actions)
    except Rejected: return False
    return all(a['op'] in {'write', 'delete'} for a in actions)

def frontier(base, observed, allowed, checkpoint, actions, policy='csdvr'):
    clean = project(base, observed, allowed, checkpoint)
    if policy == 'post_identity' or policy == 'csdvr' and is_constant(actions): seeds = [observed]
    elif policy == 'pre_post': seeds = [clean]
    elif policy == 'reset_post': seeds = [project(base, base, allowed, checkpoint)]
    elif policy in {'csdvr', 'cached_exhaustive'}: seeds = [clean, observed]
    else: raise ValueError('unknown policy')
    out = []
    for seed in seeds:
        state, error = attempt(seed, actions)
        if error is None:
            candidate = project(base, state, allowed, checkpoint)
            if candidate not in out: out.append(candidate)
    return out

def fingerprint(state):
    h = hashlib.sha256()
    for path, value in sorted(state.items()):
        p = path.encode('utf-8')
        h.update(len(p).to_bytes(8, 'big')); h.update(p)
        h.update(len(value).to_bytes(8, 'big')); h.update(value)
    return h.hexdigest()

def recover(base, observed, allowed, proposals, validate, *, checkpoint=None,
            policy='csdvr', budget=8, request_cap=4, digest=fingerprint):
    """Validator receives only a copy; hidden audit never enters this interface.

    Hashes index buckets, then exact mapping comparison checks cache identity.
    Proposal streams must already have been frozen for a paired comparison.
    """
    if policy not in {'csdvr','post_identity','pre_post','reset_post','cached_exhaustive'}:
        raise ValueError('unknown policy')
    if budget < 1 or request_cap < 0: raise ValueError('budget')
    checkpoint = checkpoint or {}
    clean = project(base, observed, allowed, checkpoint)
    stopped = project(base, base, allowed, checkpoint)
    cache, events = {}, []
    calls = requests = 0
    def check(state, source):
        nonlocal calls
        if state != project(base, state, allowed, checkpoint):
            events.append({'kind':'contract_reject','source':source}); return False
        key = digest(state)
        for previous, result in cache.get(key, []):
            if state == previous:
                events.append({'kind':'cache','source':source,'pass':result}); return result
        if calls >= budget:
            events.append({'kind':'budget_exhausted','source':source}); return False
        calls += 1
        try: result, error = bool(validate(dict(state))), None
        except Exception as exc: result, error = False, type(exc).__name__
        cache.setdefault(key, []).append((dict(state), result))
        events.append({'kind':'validate','source':source,'pass':result,'error':error})
        return result
    def outcome(accepted, state, source):
        return {'accepted':accepted,'state':dict(state),'selected_source':source,
                'validator_calls':calls,'requests':requests,'events':events}
    for source, state in [('initial',observed),('identity',clean)]:
        if check(state,source): return outcome(True,state,source)
    for i, actions in enumerate(proposals):
        if calls >= budget or requests >= request_cap: break
        requests += 1
        for j, candidate in enumerate(frontier(base,observed,allowed,checkpoint,actions,policy)):
            source = f'proposal:{i}:candidate:{j}'
            if check(candidate,source): return outcome(True,candidate,source)
    return outcome(False,stopped,'stop')
