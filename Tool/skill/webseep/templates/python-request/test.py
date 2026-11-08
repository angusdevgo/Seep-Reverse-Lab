import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch
import requests
from collect import main, run
from utils.collector import collect_to_jsonl
from utils.request import RequestClient


class RequestTests(unittest.TestCase):
    def test_cookie_defaults_and_no_retry_of_post(self):
        client=RequestClient()
        client.set_cookie('demo','value')
        self.assertEqual(client.session.cookies.get('demo'),'value')
        client.session.request=Mock(side_effect=requests.Timeout())
        with self.assertRaises(requests.Timeout): client.post('https://example.test')
        self.assertEqual(client.session.request.call_count,1)
        self.assertEqual(client.session.request.call_args.kwargs['timeout'],30)

    def test_get_retry_and_rejected_status(self):
        client=RequestClient(retry_delay=0)
        response=Mock(status_code=200)
        client.session.request=Mock(side_effect=[requests.ConnectionError(),response])
        with patch('utils.request.time.sleep'):
            self.assertIs(client.get('https://example.test'),response)
        response=Mock(status_code=403)
        response.raise_for_status.side_effect=requests.HTTPError('403')
        client.session.request=Mock(return_value=response)
        with self.assertRaises(requests.HTTPError): client.get('https://example.test')
        self.assertEqual(client.session.request.call_count,1)


class CollectorTests(unittest.TestCase):
    def test_resume_deduplicates_and_recovers_uncheckpointed_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'data.jsonl'
            calls=[]
            def fetch(cursor):
                calls.append(cursor)
                return {1:[{'id':1},{'id':2}],2:[{'id':2},{'id':3}]}[cursor]
            args=dict(fetch_page=fetch,extract_items=lambda p:p,
                      next_cursor=lambda p,c:c+1 if c==1 else None,
                      output_path=output,job_key='fixture',item_key=lambda x:x['id'])
            self.assertEqual(collect_to_jsonl(**args,max_pages=1)['status'],'limited')
            with output.open('ab') as stream: stream.write(b'{"partial":')
            result=collect_to_jsonl(**args,max_pages=2,resume=True)
            self.assertEqual(result['status'],'complete')
            self.assertEqual(calls,[1,2])
            self.assertEqual([json.loads(x)['id'] for x in output.read_text().splitlines()],[1,2,3])
            collect_to_jsonl(**args,resume=True)
            self.assertEqual(calls,[1,2])

    def test_jsonl_preserves_unicode_line_separator_inside_values(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'unicode.jsonl'
            items = [{'id':1,'text':'left\u2028right'}, {'id':2,'text':'next'}]
            collect_to_jsonl(lambda cursor: items, lambda page: page, lambda page, cursor: None,
                             output_path=output, job_key='unicode-fixture')
            with output.open(encoding='utf-8') as stream:
                actual = [json.loads(line) for line in stream]
            self.assertEqual(actual, items)


    def test_failed_fetch_and_schema_do_not_advance_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'data.jsonl'
            args=dict(extract_items=lambda p:p,next_cursor=lambda p,c:None,
                      output_path=output,job_key='fixture')
            with self.assertRaises(ValueError):
                collect_to_jsonl(lambda c: {'error':'not a list'},**args)
            state=json.loads(Path(str(output)+'.checkpoint.json').read_text())
            self.assertEqual(state['pages'],0)
            self.assertEqual(output.read_bytes(),b'')
            self.assertEqual(collect_to_jsonl(lambda c:[1],**args,resume=True)['items'],1)

    def test_cursor_loop_job_mismatch_and_modified_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'data.jsonl'
            args=dict(fetch_page=lambda c:[c],extract_items=lambda p:p,
                      next_cursor=lambda p,c:c,output_path=output,job_key='fixture')
            with self.assertRaises(ValueError): collect_to_jsonl(**args)
            args['next_cursor']=lambda p,c:c+1
            collect_to_jsonl(**args,resume=True,max_pages=1)
            args['job_key']='different'
            with self.assertRaises(ValueError): collect_to_jsonl(**args,resume=True)
            args['job_key']='fixture'
            output.write_bytes(b'x\n')
            with self.assertRaises(ValueError): collect_to_jsonl(**args,resume=True)

    def test_refuses_overwrite_and_concurrent_writer(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'data.jsonl'
            args=dict(fetch_page=lambda c:[],extract_items=lambda p:p,next_cursor=lambda p,c:None,
                      output_path=output,job_key='fixture')
            lock=Path(str(output)+'.lock');lock.touch()
            with self.assertRaises(FileExistsError): collect_to_jsonl(**args)
            lock.unlink();output.write_text('user data')
            with self.assertRaises(FileExistsError): collect_to_jsonl(**args)
            self.assertEqual(output.read_text(),'user data')


class CollectorOptionsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.output = Path(folder.name)/'data.jsonl'
        self.checkpoint = Path(str(self.output)+'.checkpoint.json')
        self.fetch = Mock()
        self.args = dict(fetch_page=self.fetch, extract_items=lambda p: p['items'],
                         next_cursor=lambda p, c: p['next'], output_path=self.output,
                         job_key='options', item_key=lambda item: item['id'])

    def page(self, ids, following):
        return {'items': [{'id': key} for key in ids], 'next': following}

    def state(self):
        return json.loads(self.checkpoint.read_text())

    def snapshot(self):
        return self.output.read_bytes(), self.checkpoint.read_bytes()

    def test_default_empty_page_stops_without_reading_next_cursor(self):
        self.fetch.return_value = {'items': []}
        self.args['next_cursor'] = Mock(side_effect=AssertionError('must not be called'))
        result = collect_to_jsonl(**self.args)
        self.assertEqual((result['status'], result['pages'], result['items']), ('complete', 1, 0))
        self.assertEqual(self.fetch.call_args_list, [call(1)])
        self.args['next_cursor'].assert_not_called()

    def test_empty_intermediate_and_terminal_pages_follow_next_cursor(self):
        self.fetch.side_effect = [self.page([], 2), self.page([1], 3), self.page([], None)]
        result = collect_to_jsonl(**self.args, stop_on_empty=False)
        self.assertEqual((result['status'], result['pages'], result['items']), ('complete', 3, 1))
        self.assertEqual(self.fetch.call_args_list, [call(1), call(2), call(3)])
        self.assertEqual(self.state()['seen_cursors'], ['1', '2', '3'])

    def test_repeated_current_cursor_retries_before_serializing_or_committing(self):
        snapshots = []
        responses = iter([{'items': [{'no_id': 'rejected'}], 'next': 1},
                          self.page([1], 2), self.page([999], 2), self.page([1, 2], None)])
        def fetch(cursor):
            snapshots.append(self.snapshot())
            return next(responses)
        self.fetch.side_effect = fetch
        with patch('utils.collector.time.sleep') as sleep:
            result = collect_to_jsonl(**self.args, max_cursor_repeats=1, cursor_retry_delay=0.25)
        self.assertEqual(self.fetch.call_args_list, [call(1), call(1), call(2), call(2)])
        self.assertEqual(sleep.call_args_list, [call(0.25), call(0.25)])
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[2], snapshots[3])
        self.assertEqual((result['pages'], result['items']), (2, 2))
        self.assertEqual(self.state()['seen_keys'], ['1', '2'])
        self.assertEqual([json.loads(line)['id'] for line in self.output.read_text().splitlines()], [1, 2])

    def test_repeat_exhaustion_preserves_previous_page_and_can_resume(self):
        self.fetch.return_value = self.page([1], 2)
        collect_to_jsonl(**self.args, max_pages_per_run=1)
        before = self.snapshot()
        self.fetch.reset_mock()
        self.fetch.return_value = self.page([999], 2)
        with patch('utils.collector.time.sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'retry limit'):
                collect_to_jsonl(**self.args, resume=True, max_cursor_repeats=2, cursor_retry_delay=0.5)
        self.assertEqual(self.fetch.call_args_list, [call(2)] * 3)
        self.assertEqual(sleep.call_args_list, [call(0.5)] * 2)
        self.assertEqual(self.snapshot(), before)
        self.fetch.return_value = self.page([1, 2], None)
        result = collect_to_jsonl(**self.args, resume=True, max_pages_per_run=1)
        self.assertEqual((result['status'], result['pages'], result['items']), ('complete', 2, 2))

    def test_retry_does_not_consume_run_or_total_page_budget(self):
        self.fetch.side_effect = [self.page([999], 1), self.page([1], 2)]
        result = collect_to_jsonl(**self.args, max_pages=1, max_pages_per_run=1, max_cursor_repeats=1)
        self.assertEqual((result['status'], result['pages'], result['items']), ('limited', 1, 1))
        self.assertEqual(self.state()['next_cursor'], 2)
        self.assertEqual(self.fetch.call_count, 2)

    def test_empty_repeat_is_rejected_when_empty_stopping_is_disabled(self):
        self.fetch.return_value = self.page([], 1)
        with self.assertRaisesRegex(ValueError, 'cursor cycle'):
            collect_to_jsonl(**self.args, stop_on_empty=False, max_cursor_repeats=1)
        self.assertEqual(self.fetch.call_count, 2)
        self.assertEqual(self.state()['pages'], 0)
        self.assertEqual(self.output.read_bytes(), b'')

    def test_history_cycle_never_retries_even_after_resume(self):
        self.fetch.return_value = self.page([1], 2)
        collect_to_jsonl(**self.args, max_pages_per_run=1)
        before = self.snapshot()
        self.fetch.reset_mock()
        self.fetch.return_value = self.page([999], 1)
        with patch('utils.collector.time.sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'historical cursor'):
                collect_to_jsonl(**self.args, resume=True, max_cursor_repeats=3, cursor_retry_delay=1)
        self.fetch.assert_called_once_with(2)
        sleep.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_saved_current_cursor_in_history_fails_before_request(self):
        self.fetch.return_value = self.page([1], 2)
        collect_to_jsonl(**self.args, max_pages_per_run=1)
        state = self.state()
        state['next_cursor'] = 1
        self.checkpoint.write_text(json.dumps(state))
        self.fetch.reset_mock()
        with self.assertRaisesRegex(ValueError, 'no request was replayed'):
            collect_to_jsonl(**self.args, resume=True, max_cursor_repeats=3)
        self.fetch.assert_not_called()

    def test_zero_run_budget_creates_checkpoint_and_checks_existing_prefix(self):
        result = collect_to_jsonl(**self.args, max_pages_per_run=0)
        self.assertEqual((result['status'], result['pages'], result['items']), ('limited', 0, 0))
        self.assertEqual(self.state()['next_cursor'], 1)
        self.fetch.assert_not_called()
        before = self.snapshot()
        self.output.write_bytes(b'uncommitted tail')
        collect_to_jsonl(**self.args, max_pages_per_run=0, resume=True)
        self.assertEqual(self.snapshot(), before)
        self.fetch.assert_not_called()
        self.fetch.return_value = self.page([1], 2)
        collect_to_jsonl(**self.args, max_pages_per_run=1, resume=True)
        self.fetch.reset_mock()
        self.output.write_bytes(self.output.read_bytes().replace(b'1', b'9'))
        with self.assertRaisesRegex(ValueError, 'prefix has changed'):
            collect_to_jsonl(**self.args, max_pages_per_run=0, resume=True)
        self.fetch.assert_not_called()

    def test_run_budget_resets_but_total_budget_does_not(self):
        self.fetch.side_effect = lambda c: self.page([c], c+1 if c < 4 else None)
        for pages in (1, 2, 3):
            result = collect_to_jsonl(**self.args, max_pages=3, max_pages_per_run=1, resume=pages > 1)
            self.assertEqual((result['status'], result['pages']), ('limited', pages))
        result = collect_to_jsonl(**self.args, max_pages=3, max_pages_per_run=1, resume=True)
        self.assertEqual(result['pages'], 3)
        self.assertEqual(self.fetch.call_count, 3)
        result = collect_to_jsonl(**self.args, max_pages=4, max_pages_per_run=1, resume=True)
        self.assertEqual((result['status'], result['pages']), ('complete', 4))
        collect_to_jsonl(**self.args, max_pages_per_run=0, resume=True)
        self.assertEqual(self.fetch.call_count, 4)

    def test_whole_page_serialization_failure_writes_nothing(self):
        self.fetch.return_value = {'items': [{'id': 1}, {'id': 2, 'value': float('nan')}], 'next': None}
        with self.assertRaises(ValueError):
            collect_to_jsonl(**self.args)
        self.assertEqual(self.output.read_bytes(), b'')
        self.assertEqual((self.state()['pages'], self.state()['seen_keys']), (0, []))

    def test_invalid_collection_options_fail_before_creating_files(self):
        invalid = {
            'max_pages': [0, -1, True, 1.5, None],
            'max_pages_per_run': [-1, True, 1.5, '2'],
            'stop_on_empty': [0, 'false', None],
            'max_cursor_repeats': [-1, True, 1.5, '2', None],
            'cursor_retry_delay': [-1, True, '1', None, float('inf'), float('nan'), 10**400],
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    collect_to_jsonl(**self.args, **{field: value})
                self.assertFalse(self.output.exists())
                self.assertFalse(self.checkpoint.exists())
        self.fetch.assert_not_called()


class ConfigCollectorTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.output = Path(folder.name)/'data.jsonl'
        self.checkpoint = Path(str(self.output)+'.checkpoint.json')
        self.config = {'url': 'https://example.test/items', 'method': 'GET', 'item_key': 'id',
                       'pagination': {'mode': 'cursor', 'start': 'A', 'next_path': 'next'}}
        factory = patch('collect.RequestClient')
        self.client = factory.start().return_value
        self.addCleanup(factory.stop)
        sleeper = patch('collect.time.sleep')
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def responses(self, *payloads):
        self.client.request.reset_mock()
        self.client.request.side_effect = [Mock(json=Mock(return_value=p)) for p in payloads]

    def state(self):
        return json.loads(self.checkpoint.read_text())

    def snapshot(self):
        return self.output.read_bytes(), self.checkpoint.read_bytes()

    def enable_business_retries(self, **options):
        self.config.update(success_path='ok', success_value=True, retryable_path='retryable',
                           retry_after_ms_path='wait_ms', max_business_retries=2)
        self.config.update(options)

    def seed_checkpoint(self):
        self.responses({'ok': True, 'data': [{'id': 1}], 'next': 'B'})
        run(self.config, self.output, max_pages_per_run=1)
        return self.snapshot()

    def test_cli_checkpoint_run_limit_and_resume_keep_config_total(self):
        self.config['max_pages'] = 2
        config_file = self.output.parent/'job.json'
        config_file.write_text(json.dumps(self.config))
        self.checkpoint = self.output.parent/'state'/'custom.json'
        args = ['--config', str(config_file), '--output', str(self.output),
                '--checkpoint', str(self.checkpoint), '--max-pages']
        def cli(extra):
            with patch('sys.stdout', new_callable=io.StringIO) as stdout:
                main(args + extra)
            return json.loads(stdout.getvalue())
        self.assertEqual(cli(['0'])['pages'], 0)
        self.client.request.assert_not_called()
        self.responses({'data': [{'id': 1}], 'next': 'B'})
        self.assertEqual(cli(['1', '--resume'])['pages'], 1)
        self.responses({'data': [{'id': 2}], 'next': 'C'})
        self.assertEqual(cli(['1', '--resume'])['pages'], 2)
        self.responses()
        result = cli(['5', '--resume'])
        self.assertEqual((result['status'], result['pages']), ('limited', 2))
        self.client.request.assert_not_called()
        self.assertFalse(Path(str(self.output)+'.checkpoint.json').exists())
        self.assertEqual(result['checkpoint'], str(self.checkpoint.resolve()))

    def test_cli_rejects_negative_run_limit(self):
        with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
            main(['--config', 'unused.json', '--max-pages', '-1'])
        self.assertEqual(error.exception.code, 2)
        self.client.request.assert_not_called()

    def test_config_run_limit_and_larger_total_on_resume(self):
        self.config.update(max_pages=1, max_pages_per_run=0)
        self.assertEqual(run(self.config, self.output)['pages'], 0)
        self.client.request.assert_not_called()
        self.responses({'data': [{'id': 1}], 'next': 'B'})
        self.assertEqual(run(self.config, self.output, True, max_pages_per_run=1)['pages'], 1)
        self.responses()
        self.assertEqual(run(self.config, self.output, True, max_pages_per_run=2)['pages'], 1)
        self.client.request.assert_not_called()
        self.config.update(max_pages=2, max_pages_per_run=1)
        self.responses({'data': [{'id': 1}, {'id': 2}], 'next': None})
        result = run(self.config, self.output, True)
        self.assertEqual((result['status'], result['pages'], result['items']), ('complete', 2, 2))

    def test_has_more_controls_empty_pages_and_false_terminates(self):
        self.config.update(has_more_path='more', stop_on_empty=True)
        self.responses({'data': [], 'more': True, 'next': 'B'},
                       {'data': [{'id': 2}], 'more': False, 'next': 'B'})
        result = run(self.config, self.output)
        self.assertEqual((result['status'], result['pages'], result['items']), ('complete', 2, 1))
        self.assertEqual([c.kwargs['params']['cursor'] for c in self.client.request.call_args_list], ['A', 'B'])

    def test_nested_has_more_path_with_page_and_offset_modes(self):
        for mode, start, step in [('page', 1, 1), ('offset', 0, 20)]:
            with self.subTest(mode=mode):
                config = dict(self.config, pagination={'mode': mode, 'has_more_path': 'page.more', 'step': step})
                self.responses({'data': [], 'page': {'more': True}},
                               {'data': [], 'page': {'more': False}})
                result = run(config, self.output.with_name(mode+'.jsonl'))
                self.assertEqual((result['status'], result['pages']), ('complete', 2))
                self.assertEqual([c.kwargs['params'][mode] for c in self.client.request.call_args_list],
                                 [start, start+step])

    def test_has_more_must_be_present_and_strict_bool_even_on_empty_page(self):
        self.config['has_more_path'] = 'more'
        for index, value in enumerate([0, 1, 'true', 'false', None, [], {}]):
            output = self.output.with_name(str(index)+'.jsonl')
            with self.subTest(value=value):
                self.responses({'data': [], 'more': value, 'next': 'B'})
                with self.assertRaisesRegex(ValueError, 'bool'):
                    run(self.config, output)
                self.assertEqual(output.read_bytes(), b'')
                self.assertEqual(json.loads(Path(str(output)+'.checkpoint.json').read_text())['pages'], 0)
        self.responses({'data': [], 'next': 'B'})
        with self.assertRaisesRegex(ValueError, 'has_more_path'):
            run(self.config, self.output)
        self.assertFalse(self.state()['complete'])

    def test_has_more_true_without_next_never_commits_even_when_empty(self):
        self.config['has_more_path'] = 'more'
        index = 0
        for items in ([], [{'id': 999}]):
            for next_part in ({}, {'next': None}, {'next': ''}):
                with self.subTest(items=items, next_part=next_part):
                    output = self.output.with_name(str(index)+'.jsonl')
                    index += 1
                    self.responses(dict(data=items, more=True, **next_part))
                    with self.assertRaisesRegex(ValueError, 'next'):
                        run(self.config, output)
                    state = json.loads(Path(str(output)+'.checkpoint.json').read_text())
                    self.assertEqual((state['pages'], state['complete'], output.read_bytes()), (0, False, b''))
        self.config['pagination'] = {'mode': 'none'}
        self.responses({'data': [], 'more': True})
        with self.assertRaisesRegex(ValueError, 'requires pagination'):
            run(self.config, self.output)

    def test_stop_on_empty_config_without_has_more(self):
        self.config['stop_on_empty'] = False
        self.responses({'data': [], 'next': 'B'}, {'data': [{'id': 1}], 'next': None})
        result = run(self.config, self.output)
        self.assertEqual((result['status'], result['pages']), ('complete', 2))

    def test_empty_intermediate_page_can_be_limited_then_resumed(self):
        self.config['has_more_path'] = 'more'
        self.responses({'data': [], 'more': True, 'next': 'B'})
        result = run(self.config, self.output, max_pages_per_run=1)
        self.assertEqual((result['status'], result['pages']), ('limited', 1))
        self.assertEqual((self.state()['next_cursor'], self.state()['complete']), ('B', False))
        self.responses({'data': [{'id': 2}], 'more': False})
        result = run(self.config, self.output, True, max_pages_per_run=1)
        self.assertEqual((result['status'], result['pages'], result['items']), ('complete', 2, 1))
        self.client.request.assert_called_once_with('GET', self.config['url'], params={'cursor': 'B'})

    def test_cursor_retries_config_does_not_write_rejected_items(self):
        self.config.update(max_cursor_repeats=1, cursor_retry_delay=0.2)
        self.responses({'data': [{'id': 999}], 'next': 'A'}, {'data': [{'id': 1}], 'next': None})
        result = run(self.config, self.output, max_pages_per_run=1)
        self.assertEqual((result['status'], result['pages'], result['items']), ('complete', 1, 1))
        self.assertEqual(json.loads(self.output.read_text()), {'id': 1})
        self.sleep.assert_called_once_with(0.2)

    def test_business_retries_wait_exactly_and_commit_only_success(self):
        self.enable_business_retries()
        before = self.seed_checkpoint()
        payloads = iter([{'retryable': True, 'wait_ms': 1250, 'data': [{'id': 999}]},
                         {'ok': False, 'retryable': True, 'wait_ms': 2500, 'data': [{'id': 888}]},
                         {'ok': True, 'data': [{'id': 1}, {'id': 2}], 'next': None}])
        self.client.request.reset_mock()
        def request(*args, **kwargs):
            self.assertEqual(self.snapshot(), before)
            return Mock(json=Mock(return_value=next(payloads)))
        self.client.request.side_effect = request
        result = run(self.config, self.output, True, max_pages_per_run=1)
        self.assertEqual(self.sleep.call_args_list, [call(1.25), call(2.5)])
        self.assertEqual(self.client.request.call_args_list, [call('GET', self.config['url'], params={'cursor': 'B'})] * 3)
        self.assertEqual((result['status'], result['pages'], result['items']), ('complete', 2, 2))
        self.assertEqual([json.loads(line)['id'] for line in self.output.read_text().splitlines()], [1, 2])
        self.client.close.assert_called()

    def test_business_marker_alone_rejects_items_and_can_retry_without_wait_path(self):
        self.config.update(retryable_path='retryable', max_business_retries=1)
        self.responses({'data': [{'id': 999}], 'next': None, 'retryable': True},
                       {'data': [{'id': 1}], 'next': None})
        result = run(self.config, self.output)
        self.assertEqual((result['pages'], result['items']), (1, 1))
        self.assertEqual(json.loads(self.output.read_text()), {'id': 1})
        self.sleep.assert_not_called()

    def test_business_retry_exhaustion_preserves_checkpoint(self):
        self.enable_business_retries()
        before = self.seed_checkpoint()
        failure = {'ok': False, 'retryable': True, 'wait_ms': 100, 'data': [{'id': 999}], 'next': None}
        self.responses(failure, failure, failure)
        with self.assertRaisesRegex(ValueError, 'exhausted'):
            run(self.config, self.output, True)
        self.assertEqual(self.client.request.call_count, 3)
        self.assertEqual(self.sleep.call_args_list, [call(0.1), call(0.1)])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(Path(str(self.output)+'.lock').exists())
        self.client.close.assert_called()

    def test_wait_over_default_cap_stops_without_shortening_and_can_resume(self):
        self.enable_business_retries()
        before = self.seed_checkpoint()
        self.responses({'ok': False, 'retryable': True, 'wait_ms': 60001, 'data': [{'id': 999}]})
        with self.assertRaisesRegex(ValueError, 'max_retry_wait_ms'):
            run(self.config, self.output, True)
        self.client.request.assert_called_once()
        self.sleep.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.config.update(max_retry_wait_ms=60001, max_business_retries=1)
        self.responses({'ok': False, 'retryable': True, 'wait_ms': 60001},
                       {'ok': True, 'data': [{'id': 2}], 'next': None})
        self.assertEqual(run(self.config, self.output, True)['status'], 'complete')
        self.sleep.assert_called_once_with(60.001)

    def test_wait_equal_to_cap_is_honored_and_zero_wait_is_allowed(self):
        self.enable_business_retries(max_retry_wait_ms=250)
        self.responses({'ok': False, 'retryable': True, 'wait_ms': 250},
                       {'ok': False, 'retryable': True, 'wait_ms': 0},
                       {'ok': True, 'data': [], 'next': None})
        self.assertEqual(run(self.config, self.output)['status'], 'complete')
        self.sleep.assert_called_once_with(0.25)

    def test_business_retries_are_disabled_by_default(self):
        self.config.update(retryable_path='retryable', retry_after_ms_path='wait_ms')
        self.responses({'retryable': True, 'wait_ms': 100, 'data': [{'id': 999}], 'next': None})
        with self.assertRaisesRegex(ValueError, 'business status failed'):
            run(self.config, self.output)
        self.client.request.assert_called_once()
        self.sleep.assert_not_called()
        self.assertEqual((self.state()['pages'], self.output.read_bytes()), (0, b''))

    def test_unmarked_business_failure_never_retries_or_writes(self):
        self.enable_business_retries()
        before = self.seed_checkpoint()
        for marker in ({}, {'retryable': False}):
            with self.subTest(marker=marker):
                self.responses(dict(ok=False, data=[{'id': 999}], next=None, **marker))
                with self.assertRaisesRegex(ValueError, 'business status failed'):
                    run(self.config, self.output, True)
                self.client.request.assert_called_once()
                self.assertEqual(self.snapshot(), before)
        self.sleep.assert_not_called()

    def test_post_business_error_is_never_retried(self):
        self.config.update(method='POST', retryable_path='retryable', body={'query': 'demo'})
        self.config['pagination']['in'] = 'body'
        self.responses({'retryable': True, 'data': [{'id': 999}], 'next': None})
        with self.assertRaisesRegex(ValueError, 'business status failed'):
            run(self.config, self.output)
        self.client.request.assert_called_once_with('POST', self.config['url'], params={},
                                                    json={'query': 'demo', 'cursor': 'A'})
        self.sleep.assert_not_called()
        self.assertEqual(self.output.read_bytes(), b'')

    def test_retries_require_explicit_get_configuration(self):
        for method in (None, 'POST', 'PUT', 'HEAD'):
            for option in ('max_business_retries', 'max_cursor_repeats'):
                with self.subTest(method=method, option=option):
                    config = dict(self.config, retryable_path='retryable', **{option: 1})
                    if method is None:
                        config.pop('method')
                    else:
                        config['method'] = method
                    with self.assertRaisesRegex(ValueError, 'explicitly configured GET'):
                        run(config, self.output)
                    self.assertFalse(self.output.exists())
        self.client.request.assert_not_called()

    def test_invalid_runtime_retry_markers_and_waits_preserve_checkpoint(self):
        self.enable_business_retries()
        before = self.seed_checkpoint()
        invalid = [dict(retryable=value, wait_ms=0) for value in (1, 0, 'true', None, {})]
        invalid += [dict(retryable=True, wait_ms=value) for value in
                    (-1, True, '100', None, float('inf'), float('nan'), 10**400)]
        invalid += [{'retryable': True}]
        for fields in invalid:
            with self.subTest(fields=fields):
                self.responses(dict(ok=False, data=[{'id': 999}], **fields))
                with self.assertRaises(ValueError):
                    run(self.config, self.output, True)
                self.client.request.assert_called_once()
                self.assertEqual(self.snapshot(), before)
        self.sleep.assert_not_called()

    def test_invalid_configuration_fails_before_output(self):
        variants = [[], {'pagination': []}, {'pagination': {'mode': 'unknown'}},
                    {'pagination': {'mode': 'cursor'}}, {'pagination': {'mode': 'page', 'step': 0}},
                    {'pagination': {'mode': 'offset', 'start': True}}, {'method': None},
                    {'has_more_path': 1}, {'has_more_path': ''}, {'has_more_path': 'data..more'},
                    {'has_more_path': 'more', 'pagination': {'has_more_path': 'other'}},
                    {'retryable_path': None}, {'retry_after_ms_path': 'wait'},
                    {'max_business_retries': 1}, {'success_path': 'ok'}, {'stop_on_empty': 'false'},
                    {'pagination': {'in': 'header'}}, {'params': []}, {'body': None}]
        for field, values in {
                'max_business_retries': [-1, True, 1.5, '1', None],
                'max_retry_wait_ms': [-1, True, '100', None, float('inf'), float('nan'), 10**400],
                'max_pages': [0, True], 'max_pages_per_run': [-1, True],
                'max_cursor_repeats': [-1, True, 1.5], 'cursor_retry_delay': [-1, True, float('nan')],
        }.items():
            variants.extend({field: value} for value in values)
        for fields in variants:
            with self.subTest(fields=fields):
                config = dict(self.config, **fields) if isinstance(fields, dict) else fields
                with self.assertRaises(ValueError):
                    run(config, self.output)
                self.assertFalse(self.output.exists())
                self.assertFalse(self.checkpoint.exists())
        self.client.request.assert_not_called()


if __name__=='__main__': unittest.main()
