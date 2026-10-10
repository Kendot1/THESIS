"""Date bounds must survive pagination and reach training before preprocessing."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from data.fetcher import DataFetcher, PRICE_COLUMNS
from main import _read_data, cmd_train


class PriceCutoffTests(unittest.TestCase):
    def fetcher(self):
        fetcher = object.__new__(DataFetcher)
        fetcher._client = MagicMock()
        fetcher._table = 'food_prices'
        return fetcher

    def test_price_projection_uses_existing_report_date(self):
        self.assertEqual(PRICE_COLUMNS, (
            "id,product_category,product_name,product_variant,origin,unit,"
            "report_date,price_index,source_pdf"))

    def test_bounds_and_projection_apply_to_every_cursor_page(self):
        fetcher = self.fetcher()
        pages = []
        batches = [
            [{'id': 1, 'report_date': '2025-09-11'},
             {'id': 2, 'report_date': '2025-09-11'}],
            [{'id': 3, 'report_date': '2025-09-12'}],
        ]
        for batch in batches:
            query = MagicMock()
            for method in ('select', 'gte', 'lte', 'or_', 'order', 'limit'):
                getattr(query, method).return_value = query
            query.execute.return_value = SimpleNamespace(data=batch)
            pages.append(query)
        fetcher._client.table.side_effect = pages
        rows = fetcher._paginated_fetch('2025-09-10', 2, '2025-09-12')
        self.assertEqual([row['id'] for row in rows], [1, 2, 3])
        for query in pages:
            query.select.assert_called_once_with(PRICE_COLUMNS)
            query.gte.assert_called_once_with('report_date', '2025-09-10')
            query.lte.assert_called_once_with('report_date', '2025-09-12')
        pages[0].or_.assert_not_called()
        pages[1].or_.assert_called_once_with(
            'report_date.gt.2025-09-11,and(report_date.eq.2025-09-11,id.gt.2)')

    def test_invalid_bounds_fail_before_any_database_request(self):
        fetcher = self.fetcher()
        for start, end in [('2025-09-13', '2025-09-12'),
                           (None, '20250912'), (None, '2025-02-30')]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                fetcher._paginated_fetch(since_date=start, through_date=end)
        fetcher._client.table.assert_not_called()

    def test_local_csv_and_json_cut_off_before_training(self):
        rows = [{'report_date': day, 'price_index': value} for day, value in
                [('2025-09-11', 40), ('2025-09-12', 41), ('2025-09-13', 999999)]]
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ('csv', 'json'):
                path = Path(tmp) / ('snapshot.' + suffix)
                if suffix == 'csv':
                    pd.DataFrame(rows).to_csv(path, index=False)
                else:
                    path.write_text(json.dumps({'rows': rows}), encoding='utf-8')
                bounded = _read_data(path, '2025-09-12')
                self.assertEqual(bounded.price_index.tolist(), [40, 41])
                self.assertEqual(len(_read_data(path)), 3)

    def test_cutoff_cli_passes_bounded_supabase_rows_to_each_training_mode(self):
        frame = pd.DataFrame({'report_date': ['2025-09-12'], 'price_index': [41]})
        for mode in ('full', 'incremental', 'daily'):
            args = SimpleNamespace(through='2025-09-12', data=None, mode=mode,
                                   resume=None, recalibrate=None, no_activate=True)
            with self.subTest(mode=mode), patch('data.fetcher.DataFetcher') as fetch, \
                    patch('pipeline.trainer.TrainingPipeline') as pipeline, \
                    contextlib.redirect_stdout(io.StringIO()):
                fetch.return_value.fetch_all.return_value = frame
                pipeline.return_value.run_full_training.return_value = {}
                pipeline.return_value.run_incremental_training.return_value = {}
                cmd_train(args)
                fetch.return_value.fetch_all.assert_called_once_with(through_date='2025-09-12')
                if mode == 'incremental':
                    call = pipeline.return_value.run_incremental_training.call_args
                    self.assertIs(call.kwargs['raw_df'], frame)
                else:
                    call = pipeline.return_value.run_full_training.call_args
                    self.assertIs(call.args[0], frame)
                self.assertFalse(call.kwargs['activate'])
                pipeline.return_value.run_daily.assert_not_called()

    def test_report_date_asof_cli_requests_full_training(self):
        frame = pd.DataFrame({'report_date': ['2025-09-12'], 'price_index': [41]})
        args = SimpleNamespace(through='2025-09-12', data=None, mode='full',
                               resume=None, recalibrate=None, no_activate=True,
                               report_date_as_of=True)
        with patch('data.fetcher.DataFetcher') as fetch, \
                patch('pipeline.trainer.TrainingPipeline') as pipeline, \
                contextlib.redirect_stdout(io.StringIO()):
            fetch.return_value.fetch_all.return_value = frame
            pipeline.return_value.run_full_training.return_value = {}
            cmd_train(args)

        fetch.return_value.fetch_all.assert_called_once_with(
            through_date='2025-09-12')
        pipeline.return_value.run_full_training.assert_called_once_with(
            frame, activate=False, source_as_of=True)

    def test_report_date_asof_cli_requires_bounded_input(self):
        args = SimpleNamespace(through=None, data=None, mode='full',
                               resume=None, recalibrate=None, no_activate=True,
                               report_date_as_of=True)
        with patch('data.fetcher.DataFetcher') as fetch, \
                patch('pipeline.trainer.TrainingPipeline') as pipeline, \
                self.assertRaisesRegex(ValueError, 'explicit --data snapshot or --through bound'):
            cmd_train(args)
        fetch.assert_not_called()
        pipeline.assert_not_called()

    def test_cutoff_cannot_relabel_a_resumed_or_recalibrated_run(self):
        for option in ('resume', 'recalibrate'):
            args = SimpleNamespace(through='2025-09-12', data='not-read.json',
                                   resume=None, recalibrate=None)
            setattr(args, option, 'existing-run')
            with self.subTest(option=option), patch('data.fetcher.DataFetcher') as fetch, \
                    patch('pipeline.trainer.TrainingPipeline') as pipeline, \
                    self.assertRaises(ValueError):
                cmd_train(args)
            fetch.assert_not_called()
            pipeline.assert_not_called()


if __name__ == '__main__':
    unittest.main()
