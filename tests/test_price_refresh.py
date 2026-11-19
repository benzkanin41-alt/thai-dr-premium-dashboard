import unittest
from unittest.mock import patch
from urllib.error import URLError

import app


class PriceRefreshTests(unittest.TestCase):
    def test_one_digit_hong_kong_underlying_maps_to_yahoo_symbol(self):
        record = {
            "symbol": "HSBC11",
            "underlying": "HSBC",
            "underlying_name": "HSBC HOLDINGS PLC (5)",
            "underlying_exchange": "The Stock Exchange of Hong Kong Limited",
        }

        self.assertEqual(
            app.resolve_yahoo_symbol(record, {}),
            ("0005.HK", "exchange_rule_hk"),
        )

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

    def test_refresh_uses_vnd_cross_rate_when_google_is_unavailable(self):
        profile = {
            "symbol": "VCB11",
            "underlying": "VCB",
            "underlying_exchange": "Ho Chi Minh Stock Exchange",
            "dr_per_underlying": 25,
        }
        fx_quotes = {
            "USDTHB=X": {"regularMarketPrice": 33.91},
            "USDVND=X": {"regularMarketPrice": 25705},
            "VNDTHB=X": {"regularMarketPrice": 0.0013},
        }
        with (
            patch.object(app, "ensure_dirs"),
            patch.object(app, "discover_dr_price_rows", return_value=[{"symbol": "VCB11", "dr_last": 2.8}]),
            patch.object(app, "refresh_set_profiles", return_value={"VCB11": profile}),
            patch.object(app, "load_manual_map", return_value={}),
            patch.object(
                app,
                "fetch_yahoo_quotes",
                side_effect=[{"VCB.VN": {"regularMarketPrice": 54000, "currency": "VND"}}, fx_quotes],
            ) as fetch_quotes,
            patch.object(app, "fetch_google_finance_fx", side_effect=URLError("DNS unavailable")),
            patch.object(app, "write_json"),
        ):
            payload = app.build_dashboard(refresh=True, update_dr_prices=True)

        self.assertEqual(set(fetch_quotes.call_args.args[0]), set(fx_quotes))
        row = payload["rows"][0]
        self.assertEqual(row["fx_source_symbol"], "USDTHB=X / USDVND=X")
        self.assertAlmostEqual(row["fx_to_thb"], 33.91 / 25705)
        self.assertAlmostEqual(row["fair_dr"], 54000 * (33.91 / 25705) / 25)
        self.assertEqual(payload["counts"]["with_diff"], 1)

    def test_vnd_fx_skips_invalid_cross_rate(self):
        specs = app.currency_to_thb_specs(["VND"])["VND"]
        quotes = {
            "USDTHB=X": {"regularMarketPrice": 33.91},
            "USDVND=X": {"regularMarketPrice": 0},
            "VNDTHB=X": {"regularMarketPrice": 0.0013},
        }
        with patch.object(app, "fetch_google_finance_fx", return_value=None):
            self.assertEqual(app.resolve_fx_to_thb("VND", specs, quotes), (0.0013, "VNDTHB=X"))

    def test_manual_refresh_never_returns_stale_dashboard_if_set_fails(self):
        with (
            patch.object(app, "ensure_dirs"),
            patch.object(app, "DASHBOARD_CACHE") as cache,
            patch.object(app, "read_json", return_value={"rows": [{"symbol": "HSBC11"}]}),
            patch.object(app, "discover_dr_price_rows", side_effect=RuntimeError("SET unavailable")),
            patch.object(app, "write_json") as write_cache,
        ):
            cache.exists.return_value = True
            with self.assertRaisesRegex(RuntimeError, "SET unavailable"):
                app.build_dashboard(refresh=True, update_dr_prices=True)

        write_cache.assert_not_called()

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
