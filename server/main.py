from __future__ import annotations

from datetime import datetime, timezone

from server.alerts import alert
from server.bridge import Bridge
from server.config import load_config
from server.logging_utils import JsonlLogger
from server.models import BotState, RuntimeState
from server.position_engine import PositionEngine
from server.risk_engine import RiskEngine
from server.strategy_engine import StrategyEngine
from server.time_engine import TimeEngine
from server.watchdog import Watchdog


def run_once(config_path: str = "configs/eurusd.yaml") -> None:
    cfg = load_config(config_path)
    bridge = Bridge(cfg.bridge_dir)
    logger = JsonlLogger("server/logs/decisions.jsonl")
    time_engine = TimeEngine(cfg.session_start_vn, cfg.session_end_vn)
    risk_engine = RiskEngine(cfg)
    strategy = StrategyEngine()
    position_engine = PositionEngine(cfg)
    watchdog = Watchdog(cfg.heartbeat_stale_seconds)
    state = RuntimeState()

    now = datetime.now(timezone.utc)
    status = bridge.read_status()

    try:
        if watchdog.stale(status):
            state.disable_entries = True
            state.disable_dca = True
            reason = "stale_or_missing_ea_status"
            logger.log("watchdog", reason=reason)
            alert(reason)
            return

        spread_pips = float(status.get("spread_pips", 999))
        adx_h1 = float(status.get("adx_h1", 0))
        rsi_m15 = float(status.get("rsi_m15", 50))
        bid = float(status.get("bid", 0))
        ask = float(status.get("ask", 0))
        balance = float(status.get("balance", 0))

        if risk_engine.daily_loss_blocked(state, balance, now):
            logger.log("blocked", reason="daily_loss_limit")
            alert("Daily loss limit reached. Stop entries for day")
            return

        wr = time_engine.in_entry_window(now)
        if state.state == BotState.COOLDOWN and state.cooldown_until and now >= state.cooldown_until:
            state.state = BotState.IDLE

        if state.state == BotState.IDLE:
            if not time_engine.in_session(now) or not wr.in_window or state.disable_entries:
                logger.log("idle", reason="outside_session_or_window_or_disabled")
                return
            if state.last_window_id == wr.window_id:
                logger.log("idle", reason="already_traded_this_slot", window_id=wr.window_id)
                return
            if not risk_engine.check_spread(spread_pips):
                logger.log("guard", reason="spread_limit", spread_pips=spread_pips)
                return
            side = strategy.decide_side(rsi_m15)
            if side == "NONE":
                logger.log("signal", side=side)
                return
            px = ask if side == "BUY" else bid
            decision = position_engine.enter_basket(state, side, px, now, wr.window_id)
            bridge.write_intent(decision.__dict__)
            logger.log("intent", **decision.__dict__)
            return

        if state.state == BotState.IN_BASKET and state.current_basket:
            basket = state.current_basket
            basket.floating_pnl_usd = float(status.get("basket_pnl_usd", 0))
            basket.mae_pips = float(status.get("basket_mae_pips", 0))

            if position_engine.basket_profit_hit(basket):
                decision = position_engine.close_basket(state, "tp_usd")
                bridge.write_intent(decision.__dict__)
                logger.log("intent", **decision.__dict__)
                return

            if risk_engine.kill_switch_hit(basket.mae_pips):
                decision = position_engine.close_basket(state, "kill_switch_mae")
                risk_engine.set_cooldown(state, now)
                bridge.write_intent(decision.__dict__)
                logger.log("intent", **decision.__dict__, cooldown_until=state.cooldown_until.isoformat())
                alert("Kill switch hit, basket closed and cooldown started")
                return

            current_px = bid if basket.side == "BUY" else ask
            if risk_engine.dca_allowed(spread_pips, adx_h1, state) and position_engine.can_add_dca(basket, current_px):
                lot = position_engine.next_lot(basket)
                if lot > 0 and basket.total_lot + lot <= cfg.max_total_lot:
                    basket.order_count += 1
                    basket.total_lot += lot
                    basket.last_fill_price = current_px
                    decision_payload = {
                        "action": "DCA",
                        "reason": "spacing_hit",
                        "side": basket.side,
                        "lot": lot,
                        "basket_id": basket.basket_id,
                    }
                    bridge.write_intent(decision_payload)
                    logger.log("intent", **decision_payload)
                    return

            logger.log("manage", reason="hold")
            return

    except Exception as exc:  # fail-safe default
        state.disable_entries = True
        state.disable_dca = True
        state.fail_safe_reason = f"{type(exc).__name__}: {exc}"
        alert(f"FAIL_SAFE: {state.fail_safe_reason}")
        logger.log("fail_safe", reason=state.fail_safe_reason)


if __name__ == "__main__":
    run_once()
