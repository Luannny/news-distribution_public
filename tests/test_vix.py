import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests

from src.vix import get_vix_snapshot


class VixAvailabilityTests(unittest.TestCase):
    @patch("src.vix.requests.get")
    @patch("src.vix.yf.Ticker")
    def test_yahoo_rate_limit_uses_latest_valid_official_close(self, ticker, get):
        ticker.return_value.history.side_effect = RuntimeError("Rate limited")
        get.return_value = Mock(text=(
            "DATE,OPEN,HIGH,LOW,CLOSE\n"
            "06/05/2026,17,18,16,17.31\n"
            "06/04/2026,17,18,16,18.42\n"
            "06/06/2026,17,18,16,nan\n"
            "01/01/2099,17,18,16,99\n"
        ))
        snapshot = get_vix_snapshot()
        self.assertEqual(snapshot.value, 17.31)
        self.assertEqual(snapshot.as_of, "2026-06-05")
        self.assertEqual(snapshot.source, "Cboe（收盘）")

    @patch("src.vix.requests.get")
    @patch("src.vix.yf.Ticker")
    def test_all_sources_unavailable_does_not_invent_a_value(self, ticker, get):
        ticker.return_value.history.side_effect = RuntimeError("Unavailable")
        get.side_effect = requests.Timeout("Unavailable")
        self.assertIsNone(get_vix_snapshot().value)

    @patch("src.vix.requests.get")
    @patch("src.vix.yf.Ticker")
    def test_valid_yahoo_close_retains_date_without_extra_request(self, ticker, get):
        ticker.return_value.history.return_value = pd.DataFrame(
            {"Close": [16.68]}, index=pd.to_datetime(["2026-06-05"])
        )
        snapshot = get_vix_snapshot()
        self.assertEqual(snapshot.value, 16.68)
        self.assertEqual(snapshot.as_of, "2026-06-05")
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
