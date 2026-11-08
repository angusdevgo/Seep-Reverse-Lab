"""Configurable JSON API collector. Run: python collect.py --config job.json.

For custom signatures, import collect_to_jsonl and supply fetch_page directly;
see references/general-collection.md in the Skill repository.
"""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from utils.collector import collect_to_jsonl
from utils.request import RequestClient


def at_path(value, path):
    for key in path.split('.') if path else []:
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def _nonnegative_number(value, name):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(name + ' must be a finite non-negative number')
    return value


def _payload_value(payload, path, name):
    try:
        return at_path(payload, path)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError(name + ' is missing or invalid in the API response') from error


def run(config, output, resume=False, *, checkpoint_path=None, max_pages_per_run=None):
    """Collect using the legacy total config.max_pages and an optional run bound.

    The run bound overrides config.max_pages_per_run when supplied. Top-level
    stop_on_empty/max_cursor_repeats/cursor_retry_delay mirror collect_to_jsonl.
    has_more_path (also accepted inside pagination) must resolve to a bool on
    every successful response and controls termination, including empty pages.
    A true flag requires a usable next cursor or page/offset progression.

    retryable_path=True marks an unaccepted business response, even if it has
    items. Missing retryable flags mean no retry; present flags must be bools.
    max_business_retries (default 0) bounds additional requests per fetch call.
    Enabling either retry budget requires an explicitly configured GET method. Business
    retries also require retryable_path. retry_after_ms_path, when configured,
    must provide a finite non-negative wait on a retryable response. Without
    that path the wait is zero. A wait above max_retry_wait_ms (default 60000)
    raises without sleeping/replaying; the last committed checkpoint survives.
    """
    if not isinstance(config, dict):
        raise ValueError('config must be an object')
    pagination = config.get('pagination', {})
    if not isinstance(pagination, dict):
        raise ValueError('pagination must be an object')
    mode = pagination.get('mode', 'page')
    if mode not in ('page', 'offset', 'cursor', 'none'):
        raise ValueError('pagination.mode must be page/offset/cursor/none')
    if mode == 'cursor' and not pagination.get('next_path'):
        raise ValueError('cursor pagination requires next_path')
    for source, fields in ((config, ('items_path', 'item_key', 'success_path', 'has_more_path',
                                    'retryable_path', 'retry_after_ms_path')),
                           (pagination, ('next_path', 'has_more_path'))):
        for field in fields:
            if field in source:
                path = source[field]
                if (not isinstance(path, str) or (path and any(not key for key in path.split('.'))) or
                        (field in ('has_more_path', 'retryable_path', 'retry_after_ms_path', 'next_path') and not path)):
                    raise ValueError(field + ' must be a valid dot-separated path')
    if ('has_more_path' in config and 'has_more_path' in pagination and
            config['has_more_path'] != pagination['has_more_path']):
        raise ValueError('conflicting has_more_path settings')
    has_more_path = config.get('has_more_path', pagination.get('has_more_path'))
    if 'success_path' in config and 'success_value' not in config:
        raise ValueError('success_path requires success_value')
    method = config.get('method', 'GET')
    if not isinstance(method, str) or not method or method != method.strip():
        raise ValueError('method must be a non-empty HTTP method')
    method = method.upper()
    if not isinstance(config.get('url'), str) or not config['url']:
        raise ValueError('url must be a non-empty string')
    if pagination.get('in', 'params') not in ('params', 'body'):
        raise ValueError('pagination.in must be params/body')
    if mode in ('page', 'offset'):
        step = pagination.get('step', 1)
        start = pagination.get('start', 0 if mode == 'offset' else 1)
        if type(step) is not int or step < 1 or type(start) is not int or start < 0:
            raise ValueError('page/offset pagination requires a non-negative integer start and positive integer step')
    for field in ('params', 'body'):
        if field in config and not isinstance(config[field], dict):
            raise ValueError(field + ' must be an object')
    if 'param' in pagination and (not isinstance(pagination['param'], str) or not pagination['param']):
        raise ValueError('pagination.param must be a non-empty string')
    retries = config.get('max_business_retries', 0)
    if type(retries) is not int or retries < 0:
        raise ValueError('max_business_retries must be a non-negative integer')
    max_wait = _nonnegative_number(config.get('max_retry_wait_ms', 60000), 'max_retry_wait_ms')
    if retries and 'retryable_path' not in config:
        raise ValueError('max_business_retries requires retryable_path')
    if 'retry_after_ms_path' in config and 'retryable_path' not in config:
        raise ValueError('retry_after_ms_path requires retryable_path')
    if (retries or config.get('max_cursor_repeats', 0)) and ('method' not in config or method != 'GET'):
        raise ValueError('retries require an explicitly configured GET method')
    if type(config.get('stop_on_empty', True)) is not bool:
        raise ValueError('stop_on_empty must be a bool')
    # Keep endpoint/query semantics in the identity, excluding credentials and
    # operational bounds so a resume may adjust its page/retry/wait budgets.
    identity = {k:v for k,v in config.items() if k not in (
        'headers', 'cookies', 'max_pages', 'timeout', 'max_pages_per_run',
        'max_cursor_repeats', 'cursor_retry_delay', 'max_business_retries', 'max_retry_wait_ms')}
    job_key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    client = RequestClient(headers=config.get('headers'), cookies=config.get('cookies'),
                           timeout=config.get('timeout', 30))
    def fetch(cursor):
        params, body = dict(config.get('params', {})), dict(config.get('body', {}))
        target = body if pagination.get('in') == 'body' else params
        if mode != 'none' and cursor is not None:
            target[pagination.get('param', 'page' if mode == 'page' else mode)] = cursor
        kwargs = {'params': params}
        if method != 'GET':
            kwargs['json'] = body
        for attempt in range(retries + 1):
            payload = client.request(method, config['url'], **kwargs).json()
            retryable = False
            if 'retryable_path' in config:
                try:
                    retryable = at_path(payload, config['retryable_path'])
                except (KeyError, IndexError):
                    pass  # An absent business marker never authorizes a retry.
                except (TypeError, ValueError) as error:
                    raise ValueError('retryable_path is invalid in the API response') from error
                if type(retryable) is not bool:
                    raise ValueError('retryable_path must resolve to a bool')
            success = not retryable and ('success_path' not in config or
                       _payload_value(payload, config['success_path'], 'success_path') == config['success_value'])
            if success:
                if has_more_path is not None:
                    has_more = _payload_value(payload, has_more_path, 'has_more_path')
                    if type(has_more) is not bool:
                        raise ValueError('has_more_path must resolve to a bool')
                return payload
            if not retryable or attempt == retries:
                raise ValueError('API business status failed; checkpoint was not advanced (retry unavailable or exhausted)')
            wait_ms = (_payload_value(payload, config['retry_after_ms_path'], 'retry_after_ms_path')
                       if 'retry_after_ms_path' in config else 0)
            _nonnegative_number(wait_ms, 'retry_after_ms_path')
            if wait_ms > max_wait:
                raise ValueError('API retry wait exceeds max_retry_wait_ms; checkpoint was not advanced')
            if wait_ms:
                time.sleep(wait_ms / 1000.0)
    def following(payload, cursor):
        if has_more_path is not None:
            if not at_path(payload, has_more_path):
                return None
            if mode == 'none':
                raise ValueError('has_more=True requires pagination and a next cursor')
        if mode == 'none':
            return None
        if mode == 'cursor':
            token = _payload_value(payload, pagination['next_path'], 'pagination.next_path')
            if has_more_path is not None and (token is None or token == ''):
                raise ValueError('has_more=True requires a next cursor')
            return None if token is None or token == '' else token
        return cursor + pagination.get('step', 1)
    try:
        return collect_to_jsonl(fetch, lambda value: at_path(value, config.get('items_path', 'data')),
            following, output_path=output, job_key=job_key,
            start_cursor=pagination.get('start', None if mode == 'cursor' else 0 if mode == 'offset' else 1),
            max_pages=config.get('max_pages', 100), resume=resume,
            checkpoint_path=checkpoint_path,
            max_pages_per_run=(config.get('max_pages_per_run') if max_pages_per_run is None else max_pages_per_run),
            stop_on_empty=False if has_more_path is not None else config.get('stop_on_empty', True),
            max_cursor_repeats=config.get('max_cursor_repeats', 0),
            cursor_retry_delay=config.get('cursor_retry_delay', 0.0),
            item_key=(lambda item: at_path(item, config['item_key'])) if config.get('item_key') else None)
    finally:
        client.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Collect a configured JSON API into resumable JSONL')
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', default='artifacts/data.jsonl')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--checkpoint', help='checkpoint file (default: OUTPUT.checkpoint.json)')
    parser.add_argument('--max-pages', type=int, help='successful pages in this run, including 0; config.max_pages is the job total')
    args = parser.parse_args(argv)
    if args.max_pages is not None and args.max_pages < 0:
        parser.error('--max-pages must be non-negative')
    result = run(json.loads(Path(args.config).read_text(encoding='utf-8')), args.output, args.resume,
                 checkpoint_path=args.checkpoint, max_pages_per_run=args.max_pages)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
