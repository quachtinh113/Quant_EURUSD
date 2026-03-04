from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from nowtrading.basket_manager import NtBasketManager
from nowtrading.dca_engine import NtDcaEngine
from nowtrading.indicators import NtIndicators
from nowtrading.interfaces import NtAccountSource, NtBroker, NtIndicatorSource
from nowtrading.logger import NtLogger
from nowtrading.risk_guard import NtRiskGuard
from nowtrading.signal_gate import NtSignalGate
from nowtrading.time_engine import NtTimeEngine
from nowtrading.types import NtDirection, NtLogLevel, NtRiskSnapshot, NtSignalSnapshot, NtTpMode


@dataclass(slots=True)
class NtEaConfig:
    magic: int = 3001001
    base_lots_total: float = 0.20
    use_pending_limit: bool = True
    pending_lots: float = 0.10
    pending_offset_pips: float = 10.0
    dca_lots: float = 0.20
    spacing_pips: float = 30.0
    max_dca_levels: int = 3

    tp_mode: NtTpMode = NtTpMode.MONEY
    target_profit_usd: float = 20.0
    atr_multiplier_tp: float = 1.5
    emergency_hours: int = 12

    max_spread_points: int = 25
    deviation_points: int = 20
    safety_sl_pips: float = 0.0

    enable_london_ny_only: bool = True
    start_hour: int = 7
    end_hour: int = 23
    daily_max_baskets: int = 3

    max_daily_dd_percent: float = 8.0
    max_floating_dd_percent: float = 10.0
    min_free_margin_percent: float = 50.0
    max_consecutive_losing_baskets: int = 3

    enable_news_blackout: bool = False
    manual_high_impact_news_time: datetime | None = None
    news_window_minutes: int = 15
    enable_correlation_guard: bool = False

    log_level: NtLogLevel = NtLogLevel.INFO


class NowTradingBasketEA:
    def __init__(
        self,
        symbol: str,
        indicator_source: NtIndicatorSource,
        broker: NtBroker,
        account_source: NtAccountSource,
        config: NtEaConfig | None = None,
        log_dir: str = ".",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._symbol = symbol
        self._broker = broker
        self._account_source = account_source
        self._config = config or NtEaConfig()
        self._now_provider = now_provider or datetime.now

        self._logger = NtLogger(account_source)
        self._time = NtTimeEngine(now_provider=self._now_provider)
        self._ind = NtIndicators(indicator_source, symbol)
        self._signal = NtSignalGate()
        self._risk = NtRiskGuard(account_source, now_provider=self._now_provider)
        self._basket = NtBasketManager(
            broker=broker,
            symbol=symbol,
            magic=self._config.magic,
            deviation_points=self._config.deviation_points,
            retry_count=3,
        )
        self._dca = NtDcaEngine(
            source=indicator_source,
            symbol=symbol,
            digits=broker.digits(symbol),
        )
        self._log_dir = log_dir
        self._consecutive_losses = 0

    def init(self) -> None:
        self._time.init()
        self._risk.init()
        self._logger.init(
            log_level=int(self._config.log_level),
            symbol=self._symbol,
            digits=self._broker.digits(self._symbol),
            base_dir=self._log_dir,
        )

    def _basket_target_price(self, basket_price: float, direction: NtDirection, sig: NtSignalSnapshot) -> float:
        dist = self._config.atr_multiplier_tp * sig.atr_m15
        if direction == NtDirection.BUY:
            return basket_price + dist
        return basket_price - dist

    def _is_basket_tp_hit(self, floating_profit: float, basket_price: float, direction: NtDirection, sig: NtSignalSnapshot) -> bool:
        if self._config.tp_mode == NtTpMode.MONEY:
            return floating_profit >= self._config.target_profit_usd

        bid = self._broker.bid(self._symbol)
        ask = self._broker.ask(self._symbol)
        tp_price = self._basket_target_price(basket_price, direction, sig)
        if direction == NtDirection.BUY:
            return bid >= tp_price
        return ask <= tp_price

    def _emergency_exit_triggered(self, first_open_time: datetime | None, direction: NtDirection, sig: NtSignalSnapshot) -> bool:
        if first_open_time is None:
            return False
        if (self._now_provider() - first_open_time).total_seconds() < self._config.emergency_hours * 3600:
            return False
        if direction == NtDirection.BUY:
            return sig.rsi_h4 < 45.0 and sig.rsi_d1 < 50.0
        if direction == NtDirection.SELL:
            return sig.rsi_h4 > 55.0 and sig.rsi_d1 > 50.0
        return False

    def _evaluate_basket_lifecycle(self, sig: NtSignalSnapshot, risk: NtRiskSnapshot) -> None:
        basket = self._basket.get_active_basket()
        if not basket.active:
            return

        if self._is_basket_tp_hit(
            floating_profit=basket.floating_profit,
            basket_price=basket.weighted_avg_price,
            direction=basket.direction,
            sig=sig,
        ):
            ok = self._basket.close_basket(basket.basket_id)
            self._logger.log(
                NtLogLevel.INFO,
                "BASKET_TP",
                basket.basket_id,
                basket.direction,
                basket.total_lots,
                basket.weighted_avg_price,
                sig,
                risk,
                "tp_close_ok" if ok else "tp_close_fail",
            )
            self._consecutive_losses = self._consecutive_losses + 1 if basket.floating_profit < 0 else 0
            return

        if self._emergency_exit_triggered(basket.first_open_time, basket.direction, sig):
            ok = self._basket.close_basket(basket.basket_id)
            self._logger.log(
                NtLogLevel.INFO,
                "EMERGENCY_EXIT",
                basket.basket_id,
                basket.direction,
                basket.total_lots,
                basket.weighted_avg_price,
                sig,
                risk,
                "12h_rsi_exit_ok" if ok else "12h_rsi_exit_fail",
            )
            self._consecutive_losses = self._consecutive_losses + 1 if basket.floating_profit < 0 else 0
            return

        if (
            basket.dca_count < self._config.max_dca_levels
            and not risk.block_dca
            and not risk.block_new_entries
            and self._dca.should_add(basket, self._config.spacing_pips)
        ):
            dca_ok = self._basket.add_dca(
                basket_id=basket.basket_id,
                direction=basket.direction,
                lots=self._config.dca_lots,
                safety_sl_pips=self._config.safety_sl_pips,
            )
            self._logger.log(
                NtLogLevel.INFO,
                "DCA_ADD",
                basket.basket_id,
                basket.direction,
                self._config.dca_lots,
                basket.last_filled_price,
                sig,
                risk,
                "dca_ok" if dca_ok else "dca_fail",
            )

    def _evaluate_new_entry(self, sig: NtSignalSnapshot, risk: NtRiskSnapshot) -> None:
        if not self._time.is_entry_minute():
            return
        if not self._time.is_session_allowed(
            self._config.enable_london_ny_only, self._config.start_hour, self._config.end_hour
        ):
            return
        if not self._time.can_open_in_current_block(self._config.daily_max_baskets):
            return

        if risk.block_new_entries:
            self._logger.log(
                NtLogLevel.INFO,
                "ENTRY_BLOCKED_RISK",
                0,
                NtDirection.NONE,
                0.0,
                0.0,
                sig,
                risk,
                risk.reason,
            )
            return

        current = self._basket.get_active_basket()
        if current.active:
            return

        direction = self._signal.evaluate(sig, self._config.max_spread_points)
        self._logger.log(
            NtLogLevel.DEBUG,
            "SIGNAL_EVAL",
            0,
            direction,
            0.0,
            0.0,
            sig,
            risk,
            "h1_m30_m15_gate",
        )
        if direction == NtDirection.NONE:
            return

        basket_id = self._basket.build_basket_id()
        ok = self._basket.open_initial_basket(
            basket_id=basket_id,
            direction=direction,
            base_lots_total=self._config.base_lots_total,
            use_pending=self._config.use_pending_limit,
            pending_lots=self._config.pending_lots,
            pending_offset_pips=self._config.pending_offset_pips,
            safety_sl_pips=self._config.safety_sl_pips,
        )
        if ok:
            self._time.mark_basket_opened()
            self._logger.log(
                NtLogLevel.INFO,
                "BASKET_OPEN",
                basket_id,
                direction,
                self._config.base_lots_total,
                self._broker.bid(self._symbol),
                sig,
                risk,
                "opened_2_market_plus_optional_limit",
            )
        else:
            self._logger.log(
                NtLogLevel.ERROR,
                "BASKET_OPEN_FAIL",
                basket_id,
                direction,
                self._config.base_lots_total,
                0.0,
                sig,
                risk,
                "execution_failed",
            )

    def on_tick(self) -> None:
        self._time.on_tick_rollover_check()
        self._risk.on_tick_rollover_check()

        sig = self._ind.snapshot()
        if sig is None:
            return

        risk = self._risk.evaluate(
            max_daily_dd=self._config.max_daily_dd_percent,
            max_float_dd=self._config.max_floating_dd_percent,
            min_free_margin_pct=self._config.min_free_margin_percent,
            consecutive_losses=self._consecutive_losses,
            max_consecutive_losses=self._config.max_consecutive_losing_baskets,
            news_enabled=self._config.enable_news_blackout,
            news_window_minutes=self._config.news_window_minutes,
            manual_news_time=self._config.manual_high_impact_news_time,
            correlation_enabled=self._config.enable_correlation_guard,
        )

        self._evaluate_basket_lifecycle(sig, risk)
        self._evaluate_new_entry(sig, risk)
