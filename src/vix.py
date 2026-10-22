from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import datetime, timezone

import requests
import yfinance as yf

CBOE_VIX_HISTORY_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"


@dataclass(frozen=True)
class VixSnapshot:
    value: float | None
    interpretation: str
    as_of: str = ""
    source: str = ""


def get_vix_snapshot() -> VixSnapshot:
    try:
        history = yf.Ticker("^VIX").history(period="5d", interval="1d")
        closes = history["Close"].dropna()
        value = float(closes.iloc[-1])
        if math.isfinite(value) and value > 0:
            return VixSnapshot(
                value=value,
                interpretation=_interpret_vix(value),
                as_of=closes.index[-1].date().isoformat(),
                source="Yahoo Finance（收盘）",
            )
    except Exception:
        pass

    # Yahoo may rate-limit requests. Cboe publishes the official daily close.
    try:
        response = requests.get(CBOE_VIX_HISTORY_URL, timeout=20)
        response.raise_for_status()
        rows = csv.DictReader(io.StringIO(response.text.lstrip("\ufeff")))
        available = []
        today = datetime.now(timezone.utc).date()
        for row in rows:
            try:
                data_date = datetime.strptime(row["DATE"], "%m/%d/%Y").date()
                value = float(row["CLOSE"])
            except (KeyError, TypeError, ValueError):
                continue
            if data_date <= today and math.isfinite(value) and value > 0:
                available.append((data_date, value))
        if available:
            data_date, value = max(available)
            return VixSnapshot(
                value=value,
                interpretation=_interpret_vix(value),
                as_of=data_date.isoformat(),
                source="Cboe（收盘）",
            )
    except requests.RequestException:
        pass

    return VixSnapshot(value=None, interpretation="VIX 暂无可用数据，无法判断当前市场波动情绪。")


def _interpret_vix(value: float) -> str:
    if value < 15:
        return "市场波动预期偏低，投资者情绪相对平稳。"
    if value < 20:
        return "市场波动预期处于正常区间，风险偏好整体中性。"
    if value < 30:
        return "市场波动预期升高，投资者对风险事件更敏感。"
    return "市场波动预期处于高位，市场避险情绪明显。"
