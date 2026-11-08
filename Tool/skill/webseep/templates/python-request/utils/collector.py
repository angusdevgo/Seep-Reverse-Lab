"""Generic bounded page/cursor collection with recoverable JSONL checkpoints.

fetch_page(cursor) owns HTTP, authentication and signing. extract_items(payload)
returns a list, and next_cursor(payload, cursor) returns the next token or None.
Only one process may write a job at a time. A stale .lock after a hard crash must
be removed by the operator after confirming that the previous writer is gone.
"""
import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path


def _token(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _atomic_json(path, data):
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name+'.', delete=False) as stream:
            temp_name = stream.name
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def collect_to_jsonl(fetch_page, extract_items, next_cursor, *, output_path,
                     job_key, start_cursor=1, max_pages=100, item_key=None,
                     checkpoint_path=None, resume=False, stop_on_empty=True,
                     max_cursor_repeats=0, cursor_retry_delay=0.0,
                     max_pages_per_run=None):
    """Write complete pages and checkpoint after durable output.

    max_pages is the total job bound, including resumed pages. item_key is an
    optional callable for deduplication across pages/runs; missing keys must be
    rejected by that callable. job_key identifies endpoint/query/signer semantics
    and must change when those change. Never put credentials in job_key.
    By default an empty list or next_cursor=None completes the job. With
    stop_on_empty=False, next_cursor decides completion even for empty pages.
    max_pages_per_run optionally bounds successful page commits in this call;
    zero only creates/validates the checkpoint (and recovers an uncommitted tail).
    Either page bound gives status=limited unless the job has completed.
    max_cursor_repeats permits that many additional fetches when the returned
    cursor equals the current cursor, waiting cursor_retry_delay seconds each
    time. Enable this only when the caller knows fetch_page is safe to retry.
    Rejected pages never write output, advance checkpoints or count as pages.
    A cursor pointing to any previously committed page always fails immediately.
    Seen cursors/keys are retained in the checkpoint, intended for bounded jobs.
    """
    if type(max_pages) is not int or max_pages < 1 or not job_key:
        raise ValueError('max_pages must be positive and job_key must be non-empty')
    if type(stop_on_empty) is not bool:
        raise ValueError('stop_on_empty must be a bool')
    if type(max_cursor_repeats) is not int or max_cursor_repeats < 0:
        raise ValueError('max_cursor_repeats must be a non-negative integer')
    try:
        valid_delay = (type(cursor_retry_delay) in (int, float) and
                       math.isfinite(cursor_retry_delay) and cursor_retry_delay >= 0)
    except OverflowError:
        valid_delay = False
    if not valid_delay:
        raise ValueError('cursor_retry_delay must be a finite non-negative number of seconds')
    if max_pages_per_run is not None and (type(max_pages_per_run) is not int or max_pages_per_run < 0):
        raise ValueError('max_pages_per_run must be None or a non-negative integer')
    output = Path(output_path).resolve()
    checkpoint = Path(checkpoint_path).resolve() if checkpoint_path else output.with_suffix(output.suffix+'.checkpoint.json')
    if output == checkpoint:
        raise ValueError('output and checkpoint must be different files')
    output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_suffix(output.suffix+'.lock')
    if checkpoint == lock:
        raise ValueError('checkpoint cannot use the writer lock path')
    with lock.open('x'):
        pass
    try:
        state = {'schema_version':1, 'job_key':job_key, 'output':str(output),
                 'next_cursor':start_cursor, 'pages':0, 'items':0, 'offset':0,
                 'sha256':hashlib.sha256(b'').hexdigest(), 'complete':False,
                 'seen_cursors':[], 'seen_keys':[], 'deduplicate':item_key is not None}
        digest = hashlib.sha256()
        if resume:
            saved = json.loads(checkpoint.read_text(encoding='utf-8'))
            for key in ('schema_version','job_key','output','deduplicate'):
                if saved.get(key) != state[key]:
                    raise ValueError('checkpoint does not match this job: '+key)
            state = saved
            with output.open('rb') as stream:
                remaining = state['offset']
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        raise ValueError('output is shorter than its checkpoint')
                    digest.update(chunk)
                    remaining -= len(chunk)
            if digest.hexdigest() != state['sha256']:
                raise ValueError('output prefix has changed since checkpoint')
            if state['complete']:
                return {'status':'complete','pages':state['pages'],'items':state['items'],'output':str(output)}
            mode = 'r+b'
        else:
            if checkpoint.exists():
                raise FileExistsError('checkpoint already exists; use resume or another output')
            mode = 'x+b'
        seen_cursors, seen_keys = set(state['seen_cursors']), set(state['seen_keys'])
        with output.open(mode) as stream:
            stream.truncate(state['offset'])
            stream.seek(state['offset'])
            if not resume:
                _atomic_json(checkpoint, state)
            run_pages = 0
            while (state['pages'] < max_pages and not state['complete'] and
                   (max_pages_per_run is None or run_pages < max_pages_per_run)):
                cursor = state['next_cursor']
                cursor_key = _token(cursor)
                if cursor_key in seen_cursors:
                    raise ValueError('pagination cursor repeated; no request was replayed')
                for attempt in range(max_cursor_repeats + 1):
                    payload = fetch_page(cursor)
                    items = extract_items(payload)
                    if not isinstance(items, list):
                        raise ValueError('extract_items must return a list; validate business errors before extraction')
                    following = next_cursor(payload, cursor) if items or not stop_on_empty else None
                    following_key = _token(following) if following is not None else None
                    if following_key in seen_cursors:
                        raise ValueError('pagination cursor cycle detected: historical cursor')
                    if following is None or following_key != cursor_key:
                        break
                    if attempt == max_cursor_repeats:
                        raise ValueError('pagination cursor cycle detected: current cursor retry limit reached')
                    if cursor_retry_delay:
                        time.sleep(cursor_retry_delay)
                # Validate/serialize a whole page before mutating its checkpoint.
                fresh, new_keys = [], set()
                for item in items:
                    if item_key:
                        key = _token(item_key(item))
                        if key in seen_keys or key in new_keys:
                            continue
                        new_keys.add(key)
                    fresh.append((_token(item)+'\n').encode('utf-8'))
                for line in fresh:
                    stream.write(line)
                    digest.update(line)
                stream.flush()
                os.fsync(stream.fileno())
                seen_cursors.add(cursor_key)
                seen_keys.update(new_keys)
                state.update(next_cursor=following, pages=state['pages']+1,
                             items=state['items']+len(fresh), offset=stream.tell(),
                             sha256=digest.hexdigest(), complete=following is None,
                             seen_cursors=sorted(seen_cursors), seen_keys=sorted(seen_keys))
                _atomic_json(checkpoint, state)
                run_pages += 1
        return {'status':'complete' if state['complete'] else 'limited',
                'pages':state['pages'],'items':state['items'],'output':str(output),
                'checkpoint':str(checkpoint)}
    finally:
        lock.unlink()
