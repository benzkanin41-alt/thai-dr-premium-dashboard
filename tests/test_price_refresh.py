import unittest
from unittest.mock import patch

import app


class PriceRefreshTests(unittest.TestCase):
    def test_retries_a_missing_yahoo_quote(self):
        quote = {"regularMarketPrice": 73.92, "currency": "USD"}
        with (
            patch.object(app, "http_get", return_value='{"quoteResponse":{"result":[]}}'),
            patch.object(app, "fetch_yahoo_chart_quote", side_effect=[None, quote]) as fetch_chart,
            patch.object(app.time, "sleep"),
        ):
            result = app.fetch_yahoo_quotes(["RKLB"])

        self.assertEqual(result["RKLB"]["regularMarketPrice"], 73.92)
        self.assertEqual(fetch_chart.call_count, 2)

    def test_incomplete_refresh_keeps_previous_dashboard_cache(self):
        profile = {
            "symbol": "RKLB01",
            "underlying": "RKLB",
            "underlying_exchange": "The Nasdaq Stock Market",
            "dr_per_underlying": 100,
        }
        with (
            patch.object(app, "ensure_dirs"),
            patch.object(app, "read_json", return_value={"rows": [{"symbol": "RKLB01"}]}),
            patch.object(app, "discover_dr_price_rows", return_value=[{"symbol": "RKLB01", "dr_last": 2.4}]),
            patch.object(app, "refresh_set_profiles", return_value={"RKLB01": profile}),
            patch.object(app, "load_manual_map", return_value={}),
            patch.object(app, "fetch_yahoo_quotes", return_value={}),
            patch.object(app, "write_json") as write_cache,
        ):
            with self.assertRaisesRegex(RuntimeError, "RKLB01"):
                app.build_dashboard(refresh=True, update_dr_prices=True)

        write_cache.assert_not_called()


if __name__ == "__main__":
    unittest.main()
