#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║     🏆 بوت تحليل الذهب XAUUSD المتقدم - Advanced XAUUSD Gold Analyzer       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  نظام تحليل فني احترافي للذهب باستخدام 12 مؤشر فني ونظام تصويت ذكي        ║
║  Professional Gold Technical Analysis System with 12 Indicators            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  المؤشرات: SMA, EMA, RSI, MACD, Bollinger, ATR, Stochastic, ADX,         ║
║           Ichimoku, Fibonacci, OBV, Support/Resistance                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  المميزات:                                                                  ║
║  ✅ Multi-Indicator Voting مع أوزان مختلفة                                  ║
║  ✅ إدارة مخاطر احترافية (Position Sizing, Trailing Stop, Multiple TP)      ║
║  ✅ تتبع أداء متكامل مع SQLite + تقارير أسبوعية                             ║
║  ✅ إشعارات تليجرام متقدمة مع أزرار تفاعلية ورسوم بيانية                    ║
║  ✅ نظام Logging كامل و Recovery تلقائي                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ═══════════════════════════════════════════════════════════
# الواردات | Imports
# ═══════════════════════════════════════════════════════════
from __future__ import annotations

import os
import sys
import json
import time
import math
import logging
import sqlite3
import hashlib
import signal
import asyncio
import aiohttp
import traceback
from pathlib import Path
from enum import Enum, auto
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import (
    Dict, List, Optional, Tuple, Union, Any,
    Callable, NamedTuple
)
from collections import deque
from logging.handlers import RotatingFileHandler

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch
from matplotlib.lines import Line2D
from dotenv import load_dotenv

from config import (
    DATA_CONFIG, INDICATOR_CONFIG, INDICATOR_WEIGHTS,
    RISK_CONFIG, SIGNAL_CONFIG, TELEGRAM_CONFIG,
    PERFORMANCE_CONFIG, LOGGING_CONFIG, CHART_CONFIG,
    TRADING_HOURS_CONFIG, CHARTS_DIR
)

# ═══════════════════════════════════════════════════════════
# تحميل المتغيرات البيئية | Load Environment Variables
# ═══════════════════════════════════════════════════════════
load_dotenv()

# ═══════════════════════════════════════════════════════════
# الإنومز | Enums
# ═══════════════════════════════════════════════════════════
class SignalType(Enum):
    """أنواع الإشارات | Signal Types"""
    STRONG_BUY = "🟢🟢 STRONG BUY"
    BUY = "🟢 BUY"
    NEUTRAL = "⚪ NEUTRAL"
    SELL = "🔴 SELL"
    STRONG_SELL = "🔴🔴 STRONG SELL"


class TrendDirection(Enum):
    """اتجاهات السوق | Trend Directions"""
    STRONG_UPTREND = "UPTREND_STRONG"
    UPTREND = "UPTREND"
    SIDEWAYS = "SIDEWAYS"
    DOWNTREND = "DOWNTREND"
    STRONG_DOWNTREND = "DOWNTREND_STRONG"


class VoteDirection(Enum):
    """اتجاه التصويت | Vote Direction"""
    BUY = 1
    NEUTRAL = 0
    SELL = -1


# ═══════════════════════════════════════════════════════════
# Dataclasses | هياكل البيانات
# ═══════════════════════════════════════════════════════════
@dataclass
class PriceData:
    """بيانات السعر | Price Data"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_dataframe_row(cls, row: pd.Series) -> PriceData:
        """إنشاء PriceData من صف DataFrame"""
        return cls(
            timestamp=row.name if isinstance(row.name, datetime) else pd.Timestamp(row.name).to_pydatetime(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=float(row["Volume"])
        )


@dataclass
class TechnicalIndicators:
    """المؤشرات الفنية | Technical Indicators"""
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None

    rsi: Optional[float] = None
    rsi_signal: Optional[str] = None

    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    macd_trend: Optional[str] = None

    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_position: Optional[str] = None

    atr: Optional[float] = None

    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    stoch_signal: Optional[str] = None

    adx: Optional[float] = None
    di_plus: Optional[float] = None
    di_minus: Optional[float] = None
    adx_trend_strength: Optional[str] = None

    tenkan_sen: Optional[float] = None
    kijun_sen: Optional[float] = None
    senkou_span_a: Optional[float] = None
    senkou_span_b: Optional[float] = None
    chikou_span: Optional[float] = None
    ichimoku_cloud: Optional[str] = None

    fib_0: Optional[float] = None
    fib_236: Optional[float] = None
    fib_382: Optional[float] = None
    fib_500: Optional[float] = None
    fib_618: Optional[float] = None
    fib_786: Optional[float] = None
    fib_1000: Optional[float] = None

    obv: Optional[float] = None
    avg_volume: Optional[float] = None
    volume_trend: Optional[str] = None

    support_level: Optional[float] = None
    resistance_level: Optional[float] = None


@dataclass
class IndicatorVote:
    """نتيجة تصويت مؤشر | Indicator Vote Result"""
    indicator_name: str
    vote: VoteDirection
    weight: float
    confidence: float
    details: str = ""


@dataclass
class SignalData:
    """بيانات الإشارة | Signal Data"""
    signal_type: SignalType
    confidence: float
    votes: List[IndicatorVote]
    entry_price: float
    stop_loss: float
    take_profits: List[Dict[str, Any]]
    risk_reward: float
    position_size: float
    leverage: float
    timestamp: datetime
    trend: TrendDirection
    notes: List[str] = field(default_factory=list)

    @property
    def direction(self) -> str:
        if self.signal_type in (SignalType.STRONG_BUY, SignalType.BUY):
            return "BUY"
        elif self.signal_type in (SignalType.STRONG_SELL, SignalType.SELL):
            return "SELL"
        return "NEUTRAL"

    @property
    def is_buy(self) -> bool:
        return self.direction == "BUY"

    @property
    def is_sell(self) -> bool:
        return self.direction == "SELL"


@dataclass
class TradeRecord:
    """سجل صفقة | Trade Record"""
    id: Optional[int]
    signal_type: str
    entry_price: float
    stop_loss: float
    take_profits: str
    position_size: float
    leverage: float
    confidence: float
    result: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════
# نظام Logging | Logging System
# ═══════════════════════════════════════════════════════════
class ColoredFormatter(logging.Formatter):
    """منسق ألوان للـ Logging"""
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging() -> logging.Logger:
    """إعداد نظام Logging"""
    logger = logging.getLogger("XAUUSDBot")
    logger.setLevel(getattr(logging, LOGGING_CONFIG["level"].upper()))

    if not logger.handlers:
        file_handler = RotatingFileHandler(
            LOGGING_CONFIG["file"],
            maxBytes=LOGGING_CONFIG["max_bytes"],
            backupCount=LOGGING_CONFIG["backup_count"],
            encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(
            LOGGING_CONFIG["format"],
            datefmt=LOGGING_CONFIG["date_format"]
        ))
        logger.addHandler(file_handler)

        if LOGGING_CONFIG["console"]:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(ColoredFormatter(
                LOGGING_CONFIG["format"],
                datefmt=LOGGING_CONFIG["date_format"]
            ))
            logger.addHandler(console_handler)

    return logger


logger = setup_logging()


# ═══════════════════════════════════════════════════════════
# جلب البيانات | Data Fetcher
# ═══════════════════════════════════════════════════════════
class DataFetcher:
    """جلب بيانات السعر من مصادر متعددة مع fallback"""

    def __init__(self):
        self.symbol = DATA_CONFIG["symbol"]
        self.symbol_display = DATA_CONFIG["symbol_display"]
        self.lookback_days = DATA_CONFIG["lookback_days"]
        self.retry_attempts = DATA_CONFIG["retry_attempts"]
        self.retry_delay = DATA_CONFIG["retry_delay"]
        self._last_data: Optional[pd.DataFrame] = None
        self._last_fetch: Optional[datetime] = None

    async def fetch_data(self) -> Optional[pd.DataFrame]:
        """جلب البيانات مع cache و fallback"""
        if (self._last_data is not None and self._last_fetch is not None and
            (datetime.now() - self._last_fetch).total_seconds() < 30):
            logger.debug("🔄 استخدام البيانات المخزنة")
            return self._last_data

        for attempt in range(1, self.retry_attempts + 1):
            try:
                logger.info(f"📡 جلب البيانات... محاولة {attempt}/{self.retry_attempts}")
                data = await self._fetch_yahoo()
                if data is not None and self._validate_data(data):
                    self._last_data = data
                    self._last_fetch = datetime.now()
                    logger.info(f"✅ تم جلب {len(data)} شمعة")
                    return data
            except Exception as e:
                logger.warning(f"⚠️ محاولة {attempt} فشلت: {e}")
                if attempt < self.retry_attempts:
                    await asyncio.sleep(self.retry_delay * attempt)

        if self._last_data is not None:
            logger.warning("⚠️ استخدام البيانات القديمة")
            return self._last_data

        logger.error("❌ فشل جلب البيانات من جميع المصادر")
        return None

    async def _fetch_yahoo(self) -> Optional[pd.DataFrame]:
        """جلب البيانات من Yahoo Finance"""
        try:
            loop = asyncio.get_event_loop()
            ticker = yf.Ticker(self.symbol)
            data = await loop.run_in_executor(
                None,
                lambda: ticker.history(
                    period=f"{self.lookback_days}d",
                    interval=DATA_CONFIG["timeframe"]
                )
            )
            if data is not None and len(data) > 0:
                return data
        except Exception as e:
            logger.error(f"Yahoo Finance error: {e}")
        return None

    def _validate_data(self, data: pd.DataFrame) -> bool:
        """التحقق من صحة البيانات"""
        if data is None or len(data) < 50:
            return False
        required_cols = ["Open", "High", "Low", "Close", "Volume"]
        if not all(col in data.columns for col in required_cols):
            return False
        if data.isnull().sum().sum() > len(data) * 0.1:
            return False
        return True

    def get_current_price(self, data: pd.DataFrame) -> float:
        return float(data["Close"].iloc[-1])


# ═══════════════════════════════════════════════════════════
# المحلل الفني | Technical Analyzer
# ═══════════════════════════════════════════════════════════
class TechnicalAnalyzer:
    """محلل فني متقدم - يحسب 12+ مؤشر فني"""

    def __init__(self):
        self.config = INDICATOR_CONFIG

    def analyze(self, data: pd.DataFrame) -> TechnicalIndicators:
        """تحليل شامل لجميع المؤشرات"""
        indicators = TechnicalIndicators()

        try:
            self._calculate_moving_averages(data, indicators)
            self._calculate_rsi(data, indicators)
            self._calculate_macd(data, indicators)
            self._calculate_bollinger(data, indicators)
            self._calculate_atr(data, indicators)
            self._calculate_stochastic(data, indicators)
            self._calculate_adx(data, indicators)
            self._calculate_ichimoku(data, indicators)
            self._calculate_fibonacci(data, indicators)
            self._calculate_volume(data, indicators)
            self._calculate_support_resistance(data, indicators)
        except Exception as e:
            logger.error(f"❌ خطأ في التحليل الفني: {e}")
            logger.debug(traceback.format_exc())

        return indicators

    def _calculate_moving_averages(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب SMA و EMA"""
        for period in self.config["sma_periods"]:
            data[f"SMA_{period}"] = data["Close"].rolling(window=period).mean()

        ind.sma_20 = self._safe_value(data, "SMA_20")
        ind.sma_50 = self._safe_value(data, "SMA_50")
        ind.sma_200 = self._safe_value(data, "SMA_200")

        for period in self.config["ema_periods"]:
            data[f"EMA_{period}"] = data["Close"].ewm(span=period, adjust=False).mean()

        ind.ema_12 = self._safe_value(data, "EMA_12")
        ind.ema_26 = self._safe_value(data, "EMA_26")

    def _calculate_rsi(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب RSI"""
        period = self.config["rsi_period"]
        delta = data["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        data["RSI"] = 100 - (100 / (1 + rs))

        ind.rsi = self._safe_value(data, "RSI")
        if ind.rsi is not None:
            if ind.rsi > self.config["rsi_overbought"]:
                ind.rsi_signal = "OVERBOUGHT"
            elif ind.rsi < self.config["rsi_oversold"]:
                ind.rsi_signal = "OVERSOLD"
            else:
                ind.rsi_signal = "NEUTRAL"

    def _calculate_macd(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب MACD"""
        ema_fast = data["Close"].ewm(span=self.config["macd_fast"], adjust=False).mean()
        ema_slow = data["Close"].ewm(span=self.config["macd_slow"], adjust=False).mean()
        data["MACD_Line"] = ema_fast - ema_slow
        data["MACD_Signal"] = data["MACD_Line"].ewm(span=self.config["macd_signal"], adjust=False).mean()
        data["MACD_Histogram"] = data["MACD_Line"] - data["MACD_Signal"]

        ind.macd_line = self._safe_value(data, "MACD_Line")
        ind.macd_signal = self._safe_value(data, "MACD_Signal")
        ind.macd_histogram = self._safe_value(data, "MACD_Histogram")

        if ind.macd_line is not None and ind.macd_signal is not None:
            ind.macd_trend = "BULLISH" if ind.macd_line > ind.macd_signal else "BEARISH"

    def _calculate_bollinger(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب Bollinger Bands"""
        period = self.config["bb_period"]
        std_dev = self.config["bb_std"]
        sma = data["Close"].rolling(window=period).mean()
        std = data["Close"].rolling(window=period).std()
        data["BB_Upper"] = sma + (std * std_dev)
        data["BB_Middle"] = sma
        data["BB_Lower"] = sma - (std * std_dev)

        ind.bb_upper = self._safe_value(data, "BB_Upper")
        ind.bb_middle = self._safe_value(data, "BB_Middle")
        ind.bb_lower = self._safe_value(data, "BB_Lower")

        close = data["Close"].iloc[-1]
        if ind.bb_upper and ind.bb_lower:
            if close >= ind.bb_upper * 0.998:
                ind.bb_position = "upper"
            elif close <= ind.bb_lower * 1.002:
                ind.bb_position = "lower"
            else:
                ind.bb_position = "middle"

    def _calculate_atr(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب Average True Range"""
        period = self.config["atr_period"]
        high_low = data["High"] - data["Low"]
        high_close = abs(data["High"] - data["Close"].shift())
        low_close = abs(data["Low"] - data["Close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        data["ATR"] = tr.rolling(window=period).mean()
        ind.atr = self._safe_value(data, "ATR")

    def _calculate_stochastic(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب Stochastic Oscillator"""
        k_period = self.config["stoch_k"]
        d_period = self.config["stoch_d"]
        smooth = self.config["stoch_smooth"]

        lowest_low = data["Low"].rolling(window=k_period).min()
        highest_high = data["High"].rolling(window=k_period).max()
        stoch_range = highest_high - lowest_low
        stoch_range = stoch_range.replace(0, np.nan)
        data["Stoch_K"] = 100 * ((data["Close"] - lowest_low) / stoch_range)
        data["Stoch_K"] = data["Stoch_K"].fillna(50)
        data["Stoch_D"] = data["Stoch_K"].rolling(window=d_period).mean()
        data["Stoch_K_Smooth"] = data["Stoch_K"].rolling(window=smooth).mean()

        ind.stoch_k = self._safe_value(data, "Stoch_K")
        ind.stoch_d = self._safe_value(data, "Stoch_D")

        if ind.stoch_k is not None:
            if ind.stoch_k > self.config["stoch_overbought"]:
                ind.stoch_signal = "OVERBOUGHT"
            elif ind.stoch_k < self.config["stoch_oversold"]:
                ind.stoch_signal = "OVERSOLD"
            else:
                ind.stoch_signal = "NEUTRAL"

    def _calculate_adx(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب Average Directional Index"""
        period = self.config["adx_period"]

        plus_dm = data["High"].diff()
        minus_dm = data["Low"].diff().abs()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr = pd.concat([
            data["High"] - data["Low"],
            abs(data["High"] - data["Close"].shift()),
            abs(data["Low"] - data["Close"].shift())
        ], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean()
        atr_safe = atr.replace(0, np.nan)
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_safe)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_safe)
        di_sum = plus_di + minus_di
        di_sum_safe = di_sum.replace(0, np.nan)
        dx = 100 * abs(plus_di - minus_di) / di_sum_safe
        dx = dx.fillna(0)
        data["ADX"] = dx.rolling(window=period).mean()

        ind.adx = self._safe_value(data, "ADX")
        ind.di_plus = plus_di.iloc[-1] if len(plus_di) > 0 else None
        ind.di_minus = minus_di.iloc[-1] if len(minus_di) > 0 else None

        if ind.adx is not None:
            if ind.adx > self.config["adx_strong"]:
                ind.adx_trend_strength = "STRONG"
            elif ind.adx > self.config["adx_weak"]:
                ind.adx_trend_strength = "MODERATE"
            else:
                ind.adx_trend_strength = "WEAK"

    def _calculate_ichimoku(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب Ichimoku Cloud"""
        tenkan = self.config["ichi_tenkan"]
        kijun = self.config["ichi_kijun"]
        senkou_b = self.config["ichi_senkou_b"]
        displacement = self.config["ichi_displacement"]

        tenkan_sen = (data["High"].rolling(window=tenkan).max() +
                      data["Low"].rolling(window=tenkan).min()) / 2
        kijun_sen = (data["High"].rolling(window=kijun).max() +
                     data["Low"].rolling(window=kijun).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(displacement)
        senkou_span_b = ((data["High"].rolling(window=senkou_b).max() +
                         data["Low"].rolling(window=senkou_b).min()) / 2).shift(displacement)
        chikou_span = data["Close"].shift(-displacement)

        data["Tenkan"] = tenkan_sen
        data["Kijun"] = kijun_sen
        data["Senkou_A"] = senkou_span_a
        data["Senkou_B"] = senkou_span_b
        data["Chikou"] = chikou_span

        ind.tenkan_sen = self._safe_value(data, "Tenkan")
        ind.kijun_sen = self._safe_value(data, "Kijun")
        ind.senkou_span_a = self._safe_value(data, "Senkou_A")
        ind.senkou_span_b = self._safe_value(data, "Senkou_B")
        ind.chikou_span = self._safe_value(data, "Chikou")

        close = data["Close"].iloc[-1]
        if ind.senkou_span_a and ind.senkou_span_b:
            cloud_top = max(ind.senkou_span_a, ind.senkou_span_b)
            cloud_bottom = min(ind.senkou_span_a, ind.senkou_span_b)
            if close > cloud_top:
                ind.ichimoku_cloud = "above"
            elif close < cloud_bottom:
                ind.ichimoku_cloud = "below"
            else:
                ind.ichimoku_cloud = "inside"

    def _calculate_fibonacci(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب مستويات فيبوناتشي"""
        high = data["High"].max()
        low = data["Low"].min()
        diff = high - low

        ind.fib_0 = low
        ind.fib_236 = low + 0.236 * diff
        ind.fib_382 = low + 0.382 * diff
        ind.fib_500 = low + 0.5 * diff
        ind.fib_618 = low + 0.618 * diff
        ind.fib_786 = low + 0.786 * diff
        ind.fib_1000 = high

    def _calculate_volume(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """تحليل الحجم (OBV)"""
        obv = [0]
        for i in range(1, len(data)):
            if data["Close"].iloc[i] > data["Close"].iloc[i - 1]:
                obv.append(obv[-1] + data["Volume"].iloc[i])
            elif data["Close"].iloc[i] < data["Close"].iloc[i - 1]:
                obv.append(obv[-1] - data["Volume"].iloc[i])
            else:
                obv.append(obv[-1])
        data["OBV"] = obv

        ind.obv = obv[-1] if len(obv) > 0 else None
        ind.avg_volume = data["Volume"].rolling(window=20).mean().iloc[-1]

        if len(data) >= 5:
            recent_vol = data["Volume"].iloc[-5:].mean()
            if ind.avg_volume and recent_vol > ind.avg_volume * 1.3:
                ind.volume_trend = "HIGH"
            elif ind.avg_volume and recent_vol < ind.avg_volume * 0.7:
                ind.volume_trend = "LOW"
            else:
                ind.volume_trend = "NORMAL"

    def _calculate_support_resistance(self, data: pd.DataFrame, ind: TechnicalIndicators) -> None:
        """حساب مستويات الدعم والمقاومة الديناميكية"""
        lookback = self.config["sr_lookback"]
        if len(data) < lookback:
            return

        recent = data.iloc[-lookback:]
        ind.support_level = recent["Low"].min()
        ind.resistance_level = recent["High"].max()

    @staticmethod
    def _safe_value(data: pd.DataFrame, column: str) -> Optional[float]:
        """الحصول على آخر قيمة آمنة"""
        if column in data.columns:
            val = data[column].iloc[-1]
            return float(val) if pd.notna(val) else None
        return None


# ═══════════════════════════════════════════════════════════
# مولد الإشارات | Signal Generator
# ═══════════════════════════════════════════════════════════
class SignalGenerator:
    """مولد الإشارات الذكي بنظام Multi-Indicator Voting"""

    def __init__(self):
        self.weights = INDICATOR_WEIGHTS
        self.config = SIGNAL_CONFIG
        self.risk_config = RISK_CONFIG
        self._last_signal_time: Optional[datetime] = None
        self._last_signal_type: Optional[SignalType] = None

    def generate_signal(self, data: pd.DataFrame, indicators: TechnicalIndicators) -> Optional[SignalData]:
        """توليد إشارة بناءً على تصويت المؤشرات"""
        current_price = float(data["Close"].iloc[-1])

        # جمع الأصوات
        votes: List[IndicatorVote] = []
        votes.append(self._vote_sma(indicators))
        votes.append(self._vote_ema(indicators))
        votes.append(self._vote_rsi(indicators))
        votes.append(self._vote_macd(indicators))
        votes.append(self._vote_bollinger(indicators, current_price))
        votes.append(self._vote_stochastic(indicators))
        votes.append(self._vote_adx(indicators))
        votes.append(self._vote_ichimoku(indicators, current_price))
        votes.append(self._vote_volume(indicators))
        votes.append(self._vote_support_resistance(indicators, current_price))

        # حساب النتيجة المرجحة
        total_score = 0.0
        total_weight = 0.0
        buy_votes = 0
        sell_votes = 0

        for vote in votes:
            total_score += vote.vote.value * vote.weight
            total_weight += vote.weight
            if vote.vote == VoteDirection.BUY:
                buy_votes += 1
            elif vote.vote == VoteDirection.SELL:
                sell_votes += 1

        normalized_score = (total_score / total_weight) if total_weight > 0 else 0
        confidence = abs(normalized_score) * 100

        signal_type = self._determine_signal_type(normalized_score, confidence, buy_votes, sell_votes)

        if not self._check_cooldown(signal_type):
            return None

        if confidence < self.config["min_confidence"]:
            logger.debug(f"⏸️ الثقة منخفضة ({confidence:.1f}%)")
            return None

        confirming = max(buy_votes, sell_votes)
        if confirming < self.config["min_confirming_indicators"]:
            logger.debug(f"⏸️ مؤشرات قليلة متفقة ({confirming})")
            return None

        trend = self._determine_trend(indicators)

        if self.config["trend_alignment_required"]:
            if signal_type in (SignalType.BUY, SignalType.STRONG_BUY) and "DOWN" in trend.value:
                logger.debug("⏸️ إشارة شراء في اتجاه هابط - تم تجاهلها")
                return None
            if signal_type in (SignalType.SELL, SignalType.STRONG_SELL) and "UP" in trend.value:
                logger.debug("⏸️ إشارة بيع في اتجاه صاعد - تم تجاهلها")
                return None

        atr = indicators.atr or (current_price * 0.001)
        sl_tp_data = self._calculate_risk_management(current_price, atr, signal_type, indicators)

        signal = SignalData(
            signal_type=signal_type,
            confidence=confidence,
            votes=votes,
            entry_price=current_price,
            stop_loss=sl_tp_data["stop_loss"],
            take_profits=sl_tp_data["take_profits"],
            risk_reward=sl_tp_data["risk_reward"],
            position_size=sl_tp_data["position_size"],
            leverage=sl_tp_data["leverage"],
            timestamp=datetime.now(),
            trend=trend,
            notes=sl_tp_data["notes"]
        )

        self._last_signal_time = datetime.now()
        self._last_signal_type = signal_type

        return signal

    def _vote_sma(self, ind: TechnicalIndicators) -> IndicatorVote:
        if ind.sma_20 is None or ind.sma_50 is None:
            return IndicatorVote("trend_sma", VoteDirection.NEUTRAL, self.weights["trend_sma"], 50, "بيانات ناقصة")
        if ind.sma_20 > ind.sma_50:
            conf = 70 if (ind.sma_50 > (ind.sma_200 or 0)) else 60
            return IndicatorVote("trend_sma", VoteDirection.BUY, self.weights["trend_sma"], conf, "SMA20 > SMA50")
        else:
            conf = 70 if (ind.sma_200 and ind.sma_50 < ind.sma_200) else 60
            return IndicatorVote("trend_sma", VoteDirection.SELL, self.weights["trend_sma"], conf, "SMA20 < SMA50")

    def _vote_ema(self, ind: TechnicalIndicators) -> IndicatorVote:
        if ind.ema_12 is None or ind.ema_26 is None:
            return IndicatorVote("trend_ema", VoteDirection.NEUTRAL, self.weights["trend_ema"], 50, "بيانات ناقصة")
        if ind.ema_12 > ind.ema_26:
            return IndicatorVote("trend_ema", VoteDirection.BUY, self.weights["trend_ema"], 65, "EMA12 > EMA26")
        else:
            return IndicatorVote("trend_ema", VoteDirection.SELL, self.weights["trend_ema"], 65, "EMA12 < EMA26")

    def _vote_rsi(self, ind: TechnicalIndicators) -> IndicatorVote:
        if ind.rsi is None:
            return IndicatorVote("rsi", VoteDirection.NEUTRAL, self.weights["rsi"], 50, "بيانات ناقصة")
        if ind.rsi < self.config["rsi_oversold"]:
            return IndicatorVote("rsi", VoteDirection.BUY, self.weights["rsi"], 80, f"RSI={ind.rsi:.1f} تشبع بيعي")
        elif ind.rsi > self.config["rsi_overbought"]:
            return IndicatorVote("rsi", VoteDirection.SELL, self.weights["rsi"], 80, f"RSI={ind.rsi:.1f} تشبع شرائي")
        elif ind.rsi < 45:
            return IndicatorVote("rsi", VoteDirection.BUY, self.weights["rsi"], 55, f"RSI={ind.rsi:.1f}")
        elif ind.rsi > 55:
            return IndicatorVote("rsi", VoteDirection.SELL, self.weights["rsi"], 55, f"RSI={ind.rsi:.1f}")
        else:
            return IndicatorVote("rsi", VoteDirection.NEUTRAL, self.weights["rsi"], 40, f"RSI={ind.rsi:.1f} محايد")

    def _vote_macd(self, ind: TechnicalIndicators) -> IndicatorVote:
        if ind.macd_line is None or ind.macd_signal is None:
            return IndicatorVote("macd", VoteDirection.NEUTRAL, self.weights["macd"], 50, "بيانات ناقصة")
        if ind.macd_line > ind.macd_signal:
            conf = 75 if (ind.macd_histogram or 0) > 0 else 60
            return IndicatorVote("macd", VoteDirection.BUY, self.weights["macd"], conf, "MACD صاعد")
        else:
            conf = 75 if (ind.macd_histogram or 0) < 0 else 60
            return IndicatorVote("macd", VoteDirection.SELL, self.weights["macd"], conf, "MACD هابط")

    def _vote_bollinger(self, ind: TechnicalIndicators, price: float) -> IndicatorVote:
        if ind.bb_upper is None or ind.bb_lower is None:
            return IndicatorVote("bollinger", VoteDirection.NEUTRAL, self.weights["bollinger"], 50, "بيانات ناقصة")
        if price >= ind.bb_upper * 0.999:
            return IndicatorVote("bollinger", VoteDirection.SELL, self.weights["bollinger"], 70, "عند الحد العلوي")
        elif price <= ind.bb_lower * 1.001:
            return IndicatorVote("bollinger", VoteDirection.BUY, self.weights["bollinger"], 70, "عند الحد السفلي")
        else:
            return IndicatorVote("bollinger", VoteDirection.NEUTRAL, self.weights["bollinger"], 40, "داخل القناة")

    def _vote_stochastic(self, ind: TechnicalIndicators) -> IndicatorVote:
        if ind.stoch_k is None:
            return IndicatorVote("stochastic", VoteDirection.NEUTRAL, self.weights["stochastic"], 50, "بيانات ناقصة")
        if ind.stoch_k < 20:
            return IndicatorVote("stochastic", VoteDirection.BUY, self.weights["stochastic"], 75, f"Stoch K={ind.stoch_k:.1f}")
        elif ind.stoch_k > 80:
            return IndicatorVote("stochastic", VoteDirection.SELL, self.weights["stochastic"], 75, f"Stoch K={ind.stoch_k:.1f}")
        else:
            return IndicatorVote("stochastic", VoteDirection.NEUTRAL, self.weights["stochastic"], 40, f"Stoch K={ind.stoch_k:.1f}")

    def _vote_adx(self, ind: TechnicalIndicators) -> IndicatorVote:
        if ind.adx is None or ind.di_plus is None or ind.di_minus is None:
            return IndicatorVote("adx", VoteDirection.NEUTRAL, self.weights["adx"], 50, "بيانات ناقصة")
        if ind.adx < 20:
            return IndicatorVote("adx", VoteDirection.NEUTRAL, self.weights["adx"], 30, f"ADX={ind.adx:.1f} ضعيف")
        if ind.di_plus > ind.di_minus:
            return IndicatorVote("adx", VoteDirection.BUY, self.weights["adx"], 70, f"DI+ > DI-")
        else:
            return IndicatorVote("adx", VoteDirection.SELL, self.weights["adx"], 70, f"DI- > DI+")

    def _vote_ichimoku(self, ind: TechnicalIndicators, price: float) -> IndicatorVote:
        if ind.tenkan_sen is None or ind.kijun_sen is None:
            return IndicatorVote("ichimoku", VoteDirection.NEUTRAL, self.weights["ichimoku"], 50, "بيانات ناقصة")
        if ind.tenkan_sen > ind.kijun_sen and price > ind.senkou_span_a:
            return IndicatorVote("ichimoku", VoteDirection.BUY, self.weights["ichimoku"], 75, "Tenkan > Kijun | فوق السحابة")
        elif ind.tenkan_sen < ind.kijun_sen and price < ind.senkou_span_a:
            return IndicatorVote("ichimoku", VoteDirection.SELL, self.weights["ichimoku"], 75, "Tenkan < Kijun | تحت السحابة")
        else:
            return IndicatorVote("ichimoku", VoteDirection.NEUTRAL, self.weights["ichimoku"], 45, "غير واضح")

    def _vote_volume(self, ind: TechnicalIndicators) -> IndicatorVote:
        if ind.volume_trend is None:
            return IndicatorVote("volume_obv", VoteDirection.NEUTRAL, self.weights["volume_obv"], 50, "بيانات ناقصة")
        if ind.volume_trend == "HIGH":
            return IndicatorVote("volume_obv", VoteDirection.BUY, self.weights["volume_obv"], 65, "حجم مرتفع")
        elif ind.volume_trend == "LOW":
            return IndicatorVote("volume_obv", VoteDirection.SELL, self.weights["volume_obv"], 55, "حجم منخفض")
        else:
            return IndicatorVote("volume_obv", VoteDirection.NEUTRAL, self.weights["volume_obv"], 45, "حجم عادي")

    def _vote_support_resistance(self, ind: TechnicalIndicators, price: float) -> IndicatorVote:
        if ind.support_level is None or ind.resistance_level is None:
            return IndicatorVote("support_resistance", VoteDirection.NEUTRAL, self.weights["support_resistance"], 50, "بيانات ناقصة")
        support_dist = abs(price - ind.support_level) / price
        resistance_dist = abs(price - ind.resistance_level) / price
        if support_dist < 0.002:
            return IndicatorVote("support_resistance", VoteDirection.BUY, self.weights["support_resistance"], 70, f"قرب الدعم")
        elif resistance_dist < 0.002:
            return IndicatorVote("support_resistance", VoteDirection.SELL, self.weights["support_resistance"], 70, f"قرب المقاومة")
        else:
            return IndicatorVote("support_resistance", VoteDirection.NEUTRAL, self.weights["support_resistance"], 40, "بعيد")

    def _determine_signal_type(self, score: float, confidence: float, buy_votes: int, sell_votes: int) -> SignalType:
        if score > 0.3 and confidence > 75 and buy_votes >= 4:
            return SignalType.STRONG_BUY
        elif score > 0.1:
            return SignalType.BUY
        elif score < -0.3 and confidence > 75 and sell_votes >= 4:
            return SignalType.STRONG_SELL
        elif score < -0.1:
            return SignalType.SELL
        else:
            return SignalType.NEUTRAL

    def _determine_trend(self, ind: TechnicalIndicators) -> TrendDirection:
        score = 0
        if ind.sma_20 and ind.sma_50:
            score += 1 if ind.sma_20 > ind.sma_50 else -1
        if ind.ema_12 and ind.ema_26:
            score += 1 if ind.ema_12 > ind.ema_26 else -1
        if ind.macd_histogram:
            score += 1 if ind.macd_histogram > 0 else -1
        if ind.adx and ind.adx > 25:
            score += 1 if ind.di_plus and ind.di_minus and ind.di_plus > ind.di_minus else -1

        if score >= 3:
            return TrendDirection.STRONG_UPTREND
        elif score >= 1:
            return TrendDirection.UPTREND
        elif score <= -3:
            return TrendDirection.STRONG_DOWNTREND
        elif score <= -1:
            return TrendDirection.DOWNTREND
        return TrendDirection.SIDEWAYS

    def _check_cooldown(self, signal_type: SignalType) -> bool:
        if self._last_signal_time is None:
            return True
        elapsed = (datetime.now() - self._last_signal_time).total_seconds()
        if elapsed < self.config["signal_cooldown"]:
            if self._last_signal_type == signal_type:
                return False
        return True

    def _calculate_risk_management(self, entry: float, atr: float, signal_type: SignalType,
                                    indicators: TechnicalIndicators) -> Dict[str, Any]:
        """حساب إدارة المخاطر: SL, TP, Position Size, Leverage"""
        account = self.risk_config["account_balance"]
        risk_pct = self.risk_config["risk_per_trade"]
        sl_multiplier = self.risk_config["sl_atr_multiplier"]

        is_buy = signal_type in (SignalType.BUY, SignalType.STRONG_BUY)

        sl_distance = atr * sl_multiplier
        stop_loss = entry - sl_distance if is_buy else entry + sl_distance

        # Take Profits
        tp_levels = []
        risk = abs(entry - stop_loss)
        for tp_cfg in self.risk_config["tp_levels"]:
            tp_price = entry + (risk * tp_cfg["ratio"]) if is_buy else entry - (risk * tp_cfg["ratio"])
            tp_levels.append({
                "level": f"TP{len(tp_levels) + 1}",
                "price": round(tp_price, 2),
                "ratio": tp_cfg["ratio"],
                "size_pct": tp_cfg["size"],
                "distance_pct": abs(tp_price - entry) / entry * 100
            })

        total_reward = sum(tp["price"] - entry if is_buy else entry - tp["price"] for tp in tp_levels)
        avg_reward = total_reward / len(tp_levels)
        risk_reward = round(avg_reward / risk, 2) if risk > 0 else 0

        # Position Size مع Spread
        spread = self.risk_config.get("spread_pips", 0.5)
        effective_sl = sl_distance + spread
        risk_amount = account * risk_pct
        position_size = risk_amount / effective_sl if effective_sl > 0 else 0

        max_size = self.risk_config.get("max_position_size", 10.0)
        min_size = self.risk_config.get("min_position_size", 0.01)
        position_size = max(min_size, min(position_size, max_size))

        # Leverage
        max_pos_value = account * self.risk_config["max_leverage"]
        suggested_leverage = min(
            self.risk_config["max_leverage"],
            max(1, int(max_pos_value / (position_size * entry)))
        ) if position_size > 0 else 1

        notes = []
        notes.append(f"📊 ATR(14) = {atr:.2f}")
        if indicators.adx:
            notes.append(f"📈 ADX = {indicators.adx:.1f}")
        if risk_reward < self.risk_config["min_risk_reward"]:
            notes.append(f"⚠️ R:R منخفض ({risk_reward})")

        return {
            "stop_loss": round(stop_loss, 2),
            "take_profits": tp_levels,
            "risk_reward": risk_reward,
            "position_size": round(position_size, 4),
            "leverage": suggested_leverage,
            "notes": notes
        }


# ═══════════════════════════════════════════════════════════
# إدارة المخاطر | Risk Manager
# ═══════════════════════════════════════════════════════════
class RiskManager:
    """مدير المخاطر - يتابع المراكز المفتوحة ويحدث الـ Trailing Stop"""

    def __init__(self, performance_tracker: Optional['PerformanceTracker'] = None):
        self.config = RISK_CONFIG
        self.performance = performance_tracker
        self._active_trades: List[Dict[str, Any]] = []

    def add_trade(self, signal: SignalData) -> Dict[str, Any]:
        """إضافة صفقة جديدة"""
        trade = {
            "id": hashlib.md5(f"{signal.timestamp}{signal.entry_price}".encode()).hexdigest()[:8],
            "signal_type": signal.signal_type.value,
            "direction": signal.direction,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profits": signal.take_profits,
            "position_size": signal.position_size,
            "leverage": signal.leverage,
            "confidence": signal.confidence,
            "opened_at": signal.timestamp.isoformat(),
            "status": "open",
            "current_sl": signal.stop_loss,
            "breakeven_set": False,
            "highest_profit": 0.0,
        }
        self._active_trades.append(trade)
        logger.info(f"💼 صفقة جديدة [{trade['id']}] {signal.signal_type.value}")
        return trade

    def update_trailing_stop(self, current_price: float) -> List[Dict[str, Any]]:
        """تحديث Trailing Stop"""
        closed_trades = []
        if not self.config["trailing_stop_enabled"]:
            return closed_trades

        for trade in self._active_trades[:]:
            if trade["status"] != "open":
                continue

            is_buy = trade["direction"] == "BUY"
            entry = trade["entry_price"]
            current_sl = trade["current_sl"]
            sl_distance = abs(entry - trade["stop_loss"])

            if is_buy:
                current_pnl_pct = (current_price - entry) / entry * 100
            else:
                current_pnl_pct = (entry - current_price) / entry * 100

            if current_pnl_pct > trade["highest_profit"]:
                trade["highest_profit"] = current_pnl_pct

            # Breakeven عند TP1
            tp1_distance_pct = trade["take_profits"][0]["distance_pct"] if trade["take_profits"] else 0.5
            if (self.config["breakeven_enabled"] and not trade["breakeven_set"] and
                current_pnl_pct >= tp1_distance_pct):
                trade["current_sl"] = entry
                trade["breakeven_set"] = True
                logger.info(f"🛡️ [{trade['id']}] SL → Breakeven")

            # Trailing Stop
            if current_pnl_pct > 1.0:
                trail_distance = sl_distance * 0.8
                if is_buy:
                    new_sl = current_price - trail_distance
                    if new_sl > current_sl:
                        trade["current_sl"] = round(new_sl, 2)
                        logger.info(f"📈 [{trade['id']}] Trailing Stop ↑ {trade['current_sl']}")
                else:
                    new_sl = current_price + trail_distance
                    if new_sl < current_sl:
                        trade["current_sl"] = round(new_sl, 2)
                        logger.info(f"📉 [{trade['id']}] Trailing Stop ↓ {trade['current_sl']}")

            # فحص الإغلاق
            if (is_buy and current_price <= trade["current_sl"]) or \
               (not is_buy and current_price >= trade["current_sl"]):
                trade["status"] = "closed_sl"
                trade["exit_price"] = current_price
                trade["closed_at"] = datetime.now().isoformat()
                closed_trades.append(trade)
                self._active_trades.remove(trade)
                logger.info(f"❌ [{trade['id']}] صفقة مغلقة على SL")

                pnl = (current_price - entry) if is_buy else (entry - current_price)
                pnl_pct = (pnl / entry) * 100
                result = "win" if pnl > 0 else "loss"
                if self.performance:
                    self.performance.update_last_signal(result, current_price, pnl, pnl_pct)

        return closed_trades

    @property
    def active_trades_count(self) -> int:
        return sum(1 for t in self._active_trades if t["status"] == "open")


# ═══════════════════════════════════════════════════════════
# تتبع الأداء | Performance Tracker
# ═══════════════════════════════════════════════════════════
class PerformanceTracker:
    """متتبع الأداء مع SQLite database"""

    def __init__(self):
        self.db_path = PERFORMANCE_CONFIG["db_path"]
        self._init_database()

    def _init_database(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL,
                    take_profits TEXT,
                    confidence REAL,
                    risk_reward REAL,
                    position_size REAL,
                    leverage REAL,
                    result TEXT,
                    pnl REAL,
                    pnl_percent REAL,
                    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP,
                    notes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    price REAL NOT NULL,
                    indicators TEXT
                )
            """)
            conn.commit()

    def record_signal(self, signal: SignalData) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    INSERT INTO signals (signal_type, direction, entry_price, stop_loss,
                        take_profits, confidence, risk_reward, position_size, leverage, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (signal.signal_type.value, signal.direction, signal.entry_price,
                    signal.stop_loss, json.dumps(signal.take_profits), signal.confidence,
                    signal.risk_reward, signal.position_size, signal.leverage, json.dumps(signal.notes)))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ خطأ في تسجيل الإشارة: {e}")
            return -1

    def record_price(self, price: float, indicators: Optional[str] = None) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT INTO price_history (price, indicators) VALUES (?, ?)", (price, indicators))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")

    def update_last_signal(self, result: str, exit_price: float, pnl: float, pnl_percent: float) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE signals SET result = ?, exit_price = ?, pnl = ?, pnl_percent = ?, closed_at = ?
                    WHERE id = (SELECT MAX(id) FROM signals WHERE result IS NULL)
                """, (result, exit_price, pnl, pnl_percent, datetime.now()))
                conn.commit()
                logger.info(f"📝 نتيجة الإشارة الأخيرة: {result} ({pnl:+.2f}$)")
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        try:
            since = datetime.now() - timedelta(days=days)
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM signals WHERE opened_at >= ? AND result IS NOT NULL",
                                    (since.isoformat(),))
                rows = cursor.fetchall()

                if not rows:
                    return {"message": "لا توجد بيانات كافية", "total": 0}

                total = len(rows)
                wins = sum(1 for r in rows if r["result"] == "win")
                losses = sum(1 for r in rows if r["result"] == "loss")
                win_rate = (wins / total * 100) if total > 0 else 0

                pnls = [r["pnl"] or 0 for r in rows]
                avg_win = np.mean([p for p in pnls if p > 0]) if any(p > 0 for p in pnls) else 0
                avg_loss = np.mean([p for p in pnls if p < 0]) if any(p < 0 for p in pnls) else 0

                total_profit = sum(p for p in pnls if p > 0)
                total_loss = abs(sum(p for p in pnls if p < 0))
                profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

                returns = [r["pnl_percent"] or 0 for r in rows]
                if len(returns) > 1 and np.std(returns, ddof=1) > 0:
                    sharpe = (np.mean(returns) / np.std(returns, ddof=1)) * np.sqrt(252)
                else:
                    sharpe = 0.0

                return {
                    "period_days": days,
                    "total_signals": total,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": round(win_rate, 2),
                    "avg_win": round(avg_win, 2),
                    "avg_loss": round(avg_loss, 2),
                    "profit_factor": round(profit_factor, 2),
                    "sharpe_ratio": round(sharpe, 2),
                    "total_pnl": round(sum(pnls), 2),
                    "total_pnl_percent": round(sum(returns), 2),
                }
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# إرسال تليجرام | Telegram Notifier
# ═══════════════════════════════════════════════════════════
class TelegramNotifier:
    """مرسل إشعارات تليجرام متقدم مع أزرار تفاعلية"""

    def __init__(self):
        self.token = TELEGRAM_CONFIG["bot_token"]
        self.chat_id = TELEGRAM_CONFIG["chat_id"]
        self.parse_mode = TELEGRAM_CONFIG["parse_mode"]
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_send_time: float = 0
        self._min_interval: float = 0.05

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def send_signal(self, signal: SignalData, indicators: TechnicalIndicators,
                          data: pd.DataFrame) -> bool:
        try:
            message = self._format_signal_message(signal, indicators)
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📊 تفاصيل المؤشرات", "callback_data": "details"},
                     {"text": "📈 رسم بياني", "callback_data": "chart"}],
                    [{"text": "📋 تقرير الأداء", "callback_data": "performance"}]
                ]
            }
            await self._send_message(message, reply_markup=keyboard)

            chart_path = await self._generate_chart(data, indicators, signal)
            if chart_path:
                await self._send_photo(chart_path, caption=f"📈 {DATA_CONFIG['symbol_display']} - {signal.signal_type.value}")
            return True
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال الإشارة: {e}")
            return False

    async def send_summary(self, indicators: TechnicalIndicators, current_price: float) -> bool:
        try:
            message = self._format_daily_summary(indicators, current_price)
            await self._send_message(message)
            return True
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")
            return False

    async def send_performance_report(self, stats: Dict[str, Any]) -> bool:
        try:
            message = self._format_performance_message(stats)
            await self._send_message(message)
            return True
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")
            return False

    async def send_alert(self, title: str, message: str, level: str = "info") -> bool:
        try:
            emoji = {"info": "ℹ️", "warning": "⚠️", "error": "🚨", "success": "✅"}.get(level, "ℹ️")
            formatted = f"{emoji} *{self._escape_markdown(title)}*\n\n{self._escape_markdown(message)}"
            await self._send_message(formatted)
            return True
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")
            return False

    def _format_signal_message(self, signal: SignalData, ind: TechnicalIndicators) -> str:
        direction_emoji = "🟢" if signal.is_buy else "🔴" if signal.is_sell else "⚪"
        tp_lines = "\n".join([
            f"    `{tp['level']}`: `{tp['price']}` ({tp['ratio']}:1) - {int(tp['size_pct'] * 100)}%"
            for tp in signal.take_profits
        ])
        return f"""
{direction_emoji} *إشارة جديدة - {self._escape_markdown(signal.signal_type.value)}*

💰 *الدخول:* `{signal.entry_price}`
🛑 *SL:* `{signal.stop_loss}`
📈 *TPs:*
{tp_lines}

📊 *الثقة:* `{signal.confidence:.1f}%`
📈 *R:R:* `{signal.risk_reward}`
📐 *الحجم:* `{signal.position_size}` lots
⚡ *الرافعة:* `{signal.leverage}x`
🧭 *الاتجاه:* `{self._escape_markdown(signal.trend.value)}`

⏰ `{self._escape_markdown(signal.timestamp.strftime('%Y-%m-%d %H:%M:%S'))}`
"""

    def _format_daily_summary(self, ind: TechnicalIndicators, price: float) -> str:
        rsi_emoji = "🟢" if ind.rsi and ind.rsi < 30 else "🔴" if ind.rsi and ind.rsi > 70 else "⚪"
        return f"""
📋 *ملخص يومي - {self._escape_markdown(DATA_CONFIG['symbol_display'])}*

💰 *السعر:* `{price}`
📊 *RSI:* `{ind.rsi:.1f}` {rsi_emoji}
📈 *MACD:* `{ind.macd_trend or 'N/A'}`
📈 *ADX:* `{ind.adx:.1f if ind.adx else 'N/A'}`
📐 *SMA20/50:* `{ind.sma_20}` / `{ind.sma_50}`

⏰ `{self._escape_markdown(datetime.now().strftime('%Y-%m-%d %H:%M'))}`
"""

    def _format_performance_message(self, stats: Dict[str, Any]) -> str:
        if "message" in stats:
            return f"📊 *تقرير الأداء*\n\n_{stats['message']}_"
        return f"""
📊 *تقرير الأداء - آخر {stats['period_days']} أيام*

📈 *الإحصائيات:*
• الإجمالي: `{stats['total_signals']}`
✅ الفوز: `{stats['wins']}` | ❌ الخسارة: `{stats['losses']}`
• نسبة الفوز: `{stats['win_rate']}%`

💰 *الأرباح:*
• متوسط الربح: `{stats['avg_win']}$`
• متوسط الخسارة: `{stats['avg_loss']}$`
• Profit Factor: `{stats['profit_factor']}`
• Sharpe Ratio: `{stats['sharpe_ratio']}`

🏆 *الصافي:* `{stats['total_pnl']}$` ({stats['total_pnl_percent']}%)
"""

    async def _send_message(self, text: str, reply_markup: Optional[Dict] = None) -> None:
        elapsed = time.time() - self._last_send_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)

        if not self.token or not self.chat_id:
            logger.warning("⚠️ إعدادات تليجرام غير مكتملة")
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": self.parse_mode,
                   "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        session = await self._get_session()
        try:
            async with session.post(url, json=payload, timeout=30) as resp:
                self._last_send_time = time.time()
                if resp.status == 429:
                    retry_after = (await resp.json()).get("parameters", {}).get("retry_after", 30)
                    await asyncio.sleep(retry_after)
                elif resp.status != 200:
                    text_resp = await resp.text()
                    logger.warning(f"⚠️ Telegram API: {resp.status} - {text_resp[:200]}")
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال رسالة: {e}")

    async def _send_photo(self, photo_path: str, caption: str = "") -> None:
        if not self.token or not self.chat_id:
            return
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        try:
            session = await self._get_session()
            with open(photo_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("chat_id", self.chat_id)
                data.add_field("photo", f, filename=Path(photo_path).name)
                data.add_field("caption", caption[:1024])
                data.add_field("parse_mode", self.parse_mode)
                async with session.post(url, data=data, timeout=60) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ فشل إرسال الصورة: {resp.status}")
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")

    async def _generate_chart(self, data: pd.DataFrame, indicators: TechnicalIndicators,
                               signal: Optional[SignalData] = None) -> Optional[str]:
        """إنشاء رسم بياني متقدم"""
        try:
            plt.style.use(CHART_CONFIG["style"])
            fig, axes = plt.subplots(4, 1, figsize=CHART_CONFIG["figsize"],
                                      gridspec_kw={"height_ratios": [3, 1, 1, 1]})

            lookback = CHART_CONFIG["candle_lookback"]
            plot_data = data.iloc[-lookback:].copy() if len(data) > lookback else data.copy()

            dates = range(len(plot_data))
            close = plot_data["Close"].values
            high = plot_data["High"].values
            low = plot_data["Low"].values
            open_p = plot_data["Open"].values

            # الشارت الرئيسي
            ax1 = axes[0]
            for i, (o, h, l, c) in enumerate(zip(open_p, high, low, close)):
                color = "#26a69a" if c >= o else "#ef5350"
                ax1.plot([i, i], [l, h], color=color, linewidth=0.8)
                ax1.bar(i, c - o, bottom=o, color=color, width=0.7, edgecolor=color)

            if indicators.sma_20:
                ax1.plot(dates, plot_data["Close"].rolling(20).mean().values,
                        color="#2196F3", linewidth=1, label="SMA20", alpha=0.9)
            if indicators.sma_50:
                ax1.plot(dates, plot_data["Close"].rolling(50).mean().values,
                        color="#FF9800", linewidth=1, label="SMA50", alpha=0.9)
            if indicators.ema_12:
                ax1.plot(dates, plot_data["Close"].ewm(span=12).mean().values,
                        color="#9C27B0", linewidth=1, label="EMA12", alpha=0.9)

            if indicators.bb_upper and indicators.bb_lower:
                bb_up = plot_data["Close"].rolling(20).mean().values + 2 * plot_data["Close"].rolling(20).std().values
                bb_low = plot_data["Close"].rolling(20).mean().values - 2 * plot_data["Close"].rolling(20).std().values
                ax1.fill_between(dates, bb_up, bb_low, alpha=0.1, color="#2196F3")

            if signal:
                color = "green" if signal.is_buy else "red"
                ax1.axhline(y=signal.entry_price, color=color, linestyle="-", alpha=0.5, linewidth=1)
                ax1.axhline(y=signal.stop_loss, color="red", linestyle="--", alpha=0.5, linewidth=0.8)
                for tp in signal.take_profits:
                    ax1.axhline(y=tp["price"], color="green", linestyle="--", alpha=0.5, linewidth=0.8)

            ax1.set_title(f"📊 {DATA_CONFIG['symbol_display']} - {signal.signal_type.value if signal else 'Analysis'}",
                          fontsize=12, fontweight="bold", color="white")
            ax1.legend(loc="upper left", fontsize=7)
            ax1.grid(True, alpha=0.2)

            # RSI
            ax2 = axes[1]
            rsi_vals = self._calculate_rsi_series(plot_data)
            ax2.plot(dates, rsi_vals, color="#673AB7", linewidth=1)
            ax2.axhline(y=70, color="red", linestyle="--", alpha=0.5)
            ax2.axhline(y=30, color="green", linestyle="--", alpha=0.5)
            ax2.fill_between(dates, 30, 70, alpha=0.05, color="gray")
            ax2.set_ylabel("RSI(14)", fontsize=8)
            ax2.set_ylim(0, 100)
            ax2.grid(True, alpha=0.2)

            # MACD
            ax3 = axes[2]
            macd_line, macd_signal, macd_hist = self._calculate_macd_series(plot_data)
            colors = ["#26a69a" if h >= 0 else "#ef5350" for h in macd_hist]
            ax3.bar(dates, macd_hist, color=colors, width=0.7, alpha=0.8)
            ax3.plot(dates, macd_line, color="#2196F3", linewidth=1, label="MACD")
            ax3.plot(dates, macd_signal, color="#FF9800", linewidth=1, label="Signal")
            ax3.axhline(y=0, color="white", linestyle="-", alpha=0.3)
            ax3.set_ylabel("MACD", fontsize=8)
            ax3.legend(fontsize=7)
            ax3.grid(True, alpha=0.2)

            # Volume
            ax4 = axes[3]
            vol_colors = ["#26a69a" if close[i] >= open_p[i] else "#ef5350"
                          for i in range(len(plot_data))]
            ax4.bar(dates, plot_data["Volume"].values, color=vol_colors, width=0.7, alpha=0.6)
            ax4.set_ylabel("Volume", fontsize=8)
            ax4.set_xlabel("الشموع", fontsize=8)
            ax4.grid(True, alpha=0.2)

            plt.tight_layout()
            chart_path = str(CHARTS_DIR / f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            plt.savefig(chart_path, dpi=CHART_CONFIG["dpi"], bbox_inches="tight",
                        facecolor="auto", edgecolor="none")
            plt.close(fig)
            return chart_path
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء الرسم البياني: {e}")
            logger.debug(traceback.format_exc())
            return None

    def _calculate_rsi_series(self, data: pd.DataFrame, period: int = 14) -> np.ndarray:
        delta = data["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50).values

    def _calculate_macd_series(self, data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        ema12 = data["Close"].ewm(span=12, adjust=False).mean()
        ema26 = data["Close"].ewm(span=26, adjust=False).mean()
        macd_line = (ema12 - ema26).fillna(0).values
        signal_line = pd.Series(macd_line).ewm(span=9, adjust=False).mean().fillna(0).values
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def _escape_markdown(text: str) -> str:
        if not isinstance(text, str):
            text = str(text)
        chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars:
            text = text.replace(char, f'\\{char}')
        return text

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# ═══════════════════════════════════════════════════════════
# البوت الرئيسي | Main Bot
# ═══════════════════════════════════════════════════════════
class XAUUSDBot:
    """البوت الرئيسي - يدير جميع المكونات"""

    def __init__(self):
        logger.info("🚀 بدء تشغيل بوت XAUUSD المتقدم...")

        self.data_fetcher = DataFetcher()
        self.analyzer = TechnicalAnalyzer()
        self.signal_generator = SignalGenerator()
        self.performance = PerformanceTracker()
        self.risk_manager = RiskManager(self.performance)
        self.notifier = TelegramNotifier()

        self._running = False
        self._last_signal: Optional[SignalData] = None
        self._last_daily_summary: Optional[datetime] = None
        self._last_weekly_report: Optional[datetime] = None
        self._health_check_time: Optional[datetime] = None

        self._setup_signal_handlers()

    async def start(self) -> None:
        self._running = True

        await self.notifier.send_alert(
            "بوت XAUUSD يعمل الآن",
            f"التحديث كل {DATA_CONFIG['update_interval']} ثانية\nالمؤشرات: 12 مؤشر فني\nنظام التصويت: Weighted Voting",
            level="success"
        )

        logger.info("✅ البوت يعمل الآن")

        while self._running:
            try:
                await self._run_cycle()
                await asyncio.sleep(DATA_CONFIG["update_interval"])
            except KeyboardInterrupt:
                logger.info("🛑 إيقاف البوت...")
                self._running = False
            except Exception as e:
                logger.error(f"❌ خطأ: {e}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(DATA_CONFIG["retry_delay"])

        await self.notifier.close()
        logger.info("👋 تم إيقاف البوت")

    async def _run_cycle(self) -> None:
        cycle_start = time.time()

        if not self.is_market_open():
            logger.debug("⏸️ السوق مغلق")
            return

        # 1. جلب البيانات
        data = await self.data_fetcher.fetch_data()
        if data is None:
            logger.warning("⚠️ لم يتم جلب البيانات")
            return

        current_price = self.data_fetcher.get_current_price(data)

        # 2. التحليل الفني
        indicators = self.analyzer.analyze(data)

        # 3. تسجيل السعر
        self.performance.record_price(current_price)

        # 4. تحديث Trailing Stop
        closed_trades = self.risk_manager.update_trailing_stop(current_price)
        for trade in closed_trades:
            pnl = (trade["exit_price"] - trade["entry_price"]) if trade["direction"] == "BUY" else \
                  (trade["entry_price"] - trade["exit_price"])
            logger.info(f"💰 صفقة مغلقة [{trade['id']}] P&L: {pnl:.2f}")

        # 5. توليد الإشارة
        signal = self.signal_generator.generate_signal(data, indicators)

        if signal and signal.signal_type != SignalType.NEUTRAL:
            logger.info(f"🎯 إشارة: {signal.signal_type.value} (ثقة: {signal.confidence:.1f}%)")
            signal_id = self.performance.record_signal(signal)
            self.risk_manager.add_trade(signal)
            await self.notifier.send_signal(signal, indicators, data)
            self._last_signal = signal
        else:
            logger.debug("⏸️ لا توجد إشارة")

        # 6. الملخص اليومي
        await self._check_daily_summary(indicators, current_price)

        # 7. التقرير الأسبوعي
        await self._check_weekly_report()

        # 8. Health Check
        self._health_check_time = datetime.now()

        cycle_time = time.time() - cycle_start
        logger.debug(f"⏱️ الدورة استغرقت {cycle_time:.2f} ثانية")

    async def _check_daily_summary(self, indicators: TechnicalIndicators, price: float) -> None:
        now = datetime.now()
        if (self._last_daily_summary is None or
            (now - self._last_daily_summary).total_seconds() > 86400):
            if now.hour >= TELEGRAM_CONFIG["daily_summary_hour"]:
                await self.notifier.send_summary(indicators, price)
                self._last_daily_summary = now
                logger.info("📋 تم إرسال الملخص اليومي")

    async def _check_weekly_report(self) -> None:
        if not PERFORMANCE_CONFIG["auto_report"]:
            return
        now = datetime.now()
        if (self._last_weekly_report is None or
            (now - self._last_weekly_report).total_seconds() > 604800):
            if now.weekday() == 6 and now.hour >= 20:
                stats = self.performance.get_stats(days=7)
                await self.notifier.send_performance_report(stats)
                self._last_weekly_report = now
                logger.info("📊 تم إرسال التقرير الأسبوعي")

    def stop(self) -> None:
        self._running = False

    def _setup_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._signal_handler)
        except (NotImplementedError, ValueError):
            signal.signal(signal.SIGINT, self._sync_signal_handler)

    def _signal_handler(self) -> None:
        logger.info("🛑 استلام إشارة إيقاف...")
        self.stop()

    def _sync_signal_handler(self, signum, frame) -> None:
        logger.info("🛑 استلام إشارة إيقاف...")
        self.stop()

    @property
    def is_healthy(self) -> bool:
        if self._health_check_time is None:
            return False
        return (datetime.now() - self._health_check_time).total_seconds() < 300

    @staticmethod
    def is_market_open() -> bool:
        if not TRADING_HOURS_CONFIG["check_trading_hours"]:
            return True

        now = datetime.utcnow()
        weekday = now.weekday()
        hour = now.hour

        open_day = TRADING_HOURS_CONFIG["market_open_day"]
        open_hour = TRADING_HOURS_CONFIG["market_open_hour"]
        close_day = TRADING_HOURS_CONFIG["market_close_day"]
        close_hour = TRADING_HOURS_CONFIG["market_close_hour"]

        adjusted_weekday = (weekday + 1) % 7

        if adjusted_weekday == 5:
            return False
        if adjusted_weekday == open_day and hour < open_hour:
            return False
        if adjusted_weekday == close_day and hour >= close_hour:
            return False
        return True


# ═══════════════════════════════════════════════════════════
# نقطة الدخول | Entry Point
# ═══════════════════════════════════════════════════════════
async def main():
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║           🏆 بوت تحليل الذهب XAUUSD المتقدم 🏆              ║
    ╠══════════════════════════════════════════════════════════════╣
    ║   Professional Gold Technical Analysis Bot                 ║
    ║   12 Technical Indicators | Smart Voting | Risk Management ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    bot = XAUUSDBot()
    await bot.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 تم الإيقاف")
