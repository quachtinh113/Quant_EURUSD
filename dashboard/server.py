from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import MetaTrader5 as mt5


ROOT_DIR = Path(__file__).resolve().parent.parent
LIVE_LOG_PATH = ROOT_DIR / "nowtrading" / "live_runner.log"
BASKET_LOG_PATH = ROOT_DIR / "NowTrading" / "EURUSDm_basket_log.csv"
STATE_FILE = ROOT_DIR / "dashboard" / "state.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


def _utc_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _tail_text(path: Path, max_lines: int = 120) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fp:
            lines = fp.readlines()
        return "".join(lines[-max_lines:])
    except Exception:
        return ""


def _read_basket_csv(path: Path, max_rows: int = 40) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fp:
            reader = csv.DictReader(fp)
            rows = list(reader)
        return rows[-max_rows:]
    except Exception:
        return []


class DashboardState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[str] | None = None
        self.config = _load_state().get("config", {})

    def _remember_config(self, cfg: dict[str, Any]) -> None:
        self.config = dict(cfg)
        _save_state({"config": self.config})

    def _popen_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "cwd": str(ROOT_DIR),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "text": True,
        }
        if os.name == "nt":
            creationflags = 0
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            kwargs["creationflags"] = creationflags
        return kwargs

    def _build_live_runner_cmd(self, cfg: dict[str, Any]) -> list[str]:
        cmd = [
            sys.executable,
            "-m",
            "nowtrading.live_runner",
            "--login",
            str(cfg["login"]),
            "--password",
            str(cfg["password"]),
            "--server",
            str(cfg["server"]),
            "--symbol",
            str(cfg["symbol"]),
            "--base-lots",
            str(cfg["base_lots"]),
            "--pending-lots",
            str(cfg["pending_lots"]),
            "--dca-lots",
            str(cfg["dca_lots"]),
            "--target-profit-usd",
            str(cfg["target_profit_usd"]),
            "--tp-mode",
            str(cfg["tp_mode"]),
            "--max-spread-points",
            str(cfg["max_spread_points"]),
            "--loop-seconds",
            str(cfg["loop_seconds"]),
            "--duration-minutes",
            "0",
            "--log-level",
            str(cfg["log_level"]),
            "--log-path",
            str(cfg["live_log_path"]),
            "--magic",
            str(cfg["magic"]),
        ]
        if cfg.get("disable_session_filter"):
            cmd.append("--disable-session-filter")
        if cfg.get("terminal_path"):
            cmd.extend(["--terminal-path", str(cfg["terminal_path"])])
        return cmd

    def start_bot(self, cfg: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return {"ok": False, "message": "Bot is already running"}
            self._remember_config(cfg)
            cmd = self._build_live_runner_cmd(cfg)
            self.proc = subprocess.Popen(cmd, **self._popen_kwargs())
            return {"ok": True, "message": f"Bot started with PID {self.proc.pid}", "pid": self.proc.pid}

    def stop_bot(self) -> dict[str, Any]:
        with self.lock:
            if not self.proc:
                return {"ok": False, "message": "No managed bot process in this dashboard session"}
            if self.proc.poll() is not None:
                return {"ok": False, "message": "Managed bot process is not running"}
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(self.proc.pid), "/F", "/T"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    self.proc.send_signal(signal.SIGTERM)
            finally:
                time.sleep(0.5)
            return {"ok": True, "message": f"Stop signal sent to PID {self.proc.pid}"}

    def restart_bot(self, cfg: dict[str, Any]) -> dict[str, Any]:
        _ = self.stop_bot()
        return self.start_bot(cfg)

    def process_status(self) -> dict[str, Any]:
        with self.lock:
            if not self.proc:
                return {"running": False, "pid": None, "managed": False}
            running = self.proc.poll() is None and _is_pid_running(self.proc.pid)
            return {"running": running, "pid": self.proc.pid, "managed": True}


APP_STATE = DashboardState()


def _mt5_snapshot(cfg: dict[str, Any]) -> dict[str, Any]:
    required_keys = ("login", "password", "server", "symbol")
    if any(not cfg.get(k) for k in required_keys):
        return {"ok": False, "error": "Missing MT5 credentials or symbol"}

    terminal_path = cfg.get("terminal_path") or r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
    initialized = mt5.initialize(
        path=terminal_path,
        login=int(cfg["login"]),
        password=str(cfg["password"]),
        server=str(cfg["server"]),
    )
    if not initialized:
        return {"ok": False, "error": f"MT5 init failed: {mt5.last_error()}"}

    try:
        resolved_symbol = cfg["symbol"]
        if not mt5.symbol_select(resolved_symbol, True):
            candidates = mt5.symbols_get(f"{cfg['symbol']}*") or []
            resolved_symbol = candidates[0].name if candidates else cfg["symbol"]
            mt5.symbol_select(resolved_symbol, True)

        account = mt5.account_info()
        terminal = mt5.terminal_info()
        positions = mt5.positions_get() or []
        orders = mt5.orders_get() or []
        magic = int(cfg.get("magic", 3001001))
        bot_positions = [p for p in positions if int(getattr(p, "magic", 0)) == magic]
        bot_orders = [o for o in orders if int(getattr(o, "magic", 0)) == magic]
        floating = sum(float(getattr(p, "profit", 0.0)) for p in bot_positions)
        return {
            "ok": True,
            "resolved_symbol": resolved_symbol,
            "account": {
                "login": int(account.login) if account else None,
                "server": str(account.server) if account else None,
                "balance": float(account.balance) if account else None,
                "equity": float(account.equity) if account else None,
                "margin_free": float(account.margin_free) if account else None,
            },
            "terminal": {
                "trade_allowed": bool(terminal.trade_allowed) if terminal else None,
                "tradeapi_disabled": bool(terminal.tradeapi_disabled) if terminal else None,
                "connected": bool(terminal.connected) if terminal else None,
            },
            "bot": {
                "magic": magic,
                "position_count": len(bot_positions),
                "order_count": len(bot_orders),
                "floating_profit": floating,
            },
            "positions": [
                {
                    "ticket": int(p.ticket),
                    "symbol": str(p.symbol),
                    "type": int(p.type),
                    "volume": float(p.volume),
                    "price_open": float(p.price_open),
                    "profit": float(p.profit),
                    "comment": str(p.comment),
                }
                for p in bot_positions
            ],
        }
    finally:
        mt5.shutdown()


def _safe_float(data: dict[str, list[str]], key: str, default: float) -> float:
    try:
        return float(data.get(key, [str(default)])[0])
    except ValueError:
        return default


def _safe_int(data: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(data.get(key, [str(default)])[0])
    except ValueError:
        return default


def _parse_form(body: str) -> dict[str, Any]:
    form = parse_qs(body, keep_blank_values=True)
    return {
        "login": _safe_int(form, "login", 0),
        "password": form.get("password", [""])[0],
        "server": form.get("server", [""])[0],
        "terminal_path": form.get("terminal_path", [""])[0],
        "symbol": form.get("symbol", ["EURUSD"])[0],
        "base_lots": _safe_float(form, "base_lots", 0.01),
        "pending_lots": _safe_float(form, "pending_lots", 0.0),
        "dca_lots": _safe_float(form, "dca_lots", 0.01),
        "target_profit_usd": _safe_float(form, "target_profit_usd", 10.0),
        "tp_mode": form.get("tp_mode", ["money"])[0],
        "max_spread_points": _safe_int(form, "max_spread_points", 25),
        "loop_seconds": _safe_float(form, "loop_seconds", 1.0),
        "log_level": form.get("log_level", ["info"])[0],
        "live_log_path": form.get("live_log_path", ["nowtrading/live_runner.log"])[0],
        "magic": _safe_int(form, "magic", 3001001),
        "disable_session_filter": form.get("disable_session_filter", ["off"])[0] == "on",
    }


def _default_config() -> dict[str, Any]:
    persisted = APP_STATE.config
    return {
        "login": persisted.get("login", 0),
        "password": persisted.get("password", ""),
        "server": persisted.get("server", "Exness-MT5Trial7"),
        "terminal_path": persisted.get("terminal_path", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"),
        "symbol": persisted.get("symbol", "EURUSD"),
        "base_lots": persisted.get("base_lots", 0.01),
        "pending_lots": persisted.get("pending_lots", 0.0),
        "dca_lots": persisted.get("dca_lots", 0.01),
        "target_profit_usd": persisted.get("target_profit_usd", 10.0),
        "tp_mode": persisted.get("tp_mode", "money"),
        "max_spread_points": persisted.get("max_spread_points", 25),
        "loop_seconds": persisted.get("loop_seconds", 1.0),
        "log_level": persisted.get("log_level", "debug"),
        "live_log_path": persisted.get("live_log_path", "nowtrading/live_runner.log"),
        "magic": persisted.get("magic", 3001001),
        "disable_session_filter": persisted.get("disable_session_filter", False),
    }


def _render_html(config: dict[str, Any], notice: str = "") -> str:
    checked = "checked" if config.get("disable_session_filter") else ""
    selected_money = "selected" if config.get("tp_mode") == "money" else ""
    selected_atr = "selected" if config.get("tp_mode") == "atr" else ""
    selected_err = "selected" if config.get("log_level") == "error" else ""
    selected_info = "selected" if config.get("log_level") == "info" else ""
    selected_debug = "selected" if config.get("log_level") == "debug" else ""
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NowTrading Dashboard</title>
  <style>
    :root {{
      --bg: #f3f6ef;
      --panel: #ffffff;
      --ink: #10291f;
      --muted: #4a6558;
      --accent: #157347;
      --warn: #a94442;
      --line: #d9e7db;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Tahoma", sans-serif;
      background: radial-gradient(circle at 0% 0%, #ecf7ea 0%, var(--bg) 48%, #edf4ea 100%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1200px;
      margin: 20px auto;
      padding: 0 16px 24px;
    }}
    .hero {{
      background: linear-gradient(120deg, #144c35 0%, #1a7f53 100%);
      color: white;
      border-radius: 14px;
      padding: 16px 18px;
      box-shadow: 0 10px 24px rgba(21, 115, 71, 0.25);
    }}
    .hero h1 {{
      margin: 0;
      font-size: 26px;
      letter-spacing: 0.3px;
    }}
    .hero p {{
      margin: 7px 0 0;
      color: #e6f5e8;
      font-size: 14px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      box-shadow: 0 6px 16px rgba(12, 40, 28, 0.06);
    }}
    .panel h2 {{
      margin: 0 0 8px;
      font-size: 18px;
    }}
    .kpis {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .kpi {{
      background: #f4fbf5;
      border: 1px solid #cde3d0;
      border-radius: 10px;
      padding: 8px 10px;
      min-width: 130px;
    }}
    .kpi b {{
      display: block;
      font-size: 18px;
      margin-top: 3px;
    }}
    form .row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 8px;
    }}
    label {{
      font-size: 12px;
      color: var(--muted);
      display: block;
      margin-bottom: 3px;
    }}
    input, select {{
      width: 100%;
      border: 1px solid #c7ddca;
      border-radius: 8px;
      padding: 7px 8px;
      font-size: 13px;
      box-sizing: border-box;
      background: #fbfffb;
    }}
    .line {{
      display: flex;
      gap: 7px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}
    button {{
      border: 0;
      border-radius: 9px;
      padding: 9px 12px;
      font-weight: 600;
      cursor: pointer;
      color: white;
      background: var(--accent);
    }}
    button.stop {{
      background: var(--warn);
    }}
    pre {{
      background: #0f1f16;
      color: #ccf2d3;
      border-radius: 10px;
      padding: 10px;
      font-size: 12px;
      line-height: 1.35;
      overflow: auto;
      max-height: 280px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 6px 4px;
    }}
    .note {{
      margin-top: 8px;
      font-size: 13px;
      color: #254737;
    }}
    .status-running {{
      color: #0f8a4b;
      font-weight: 700;
    }}
    .status-stopped {{
      color: #9f2b25;
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>NowTrading Control Dashboard</h1>
      <p>Manage live runner, monitor MT5 state, inspect logs and basket events.</p>
    </div>
    <div class="note">{notice}</div>
    <div class="grid">
      <div class="panel" style="grid-column: span 2;">
        <h2>Runner Config</h2>
        <form method="post" action="/action">
          <input type="hidden" name="action" value="save" />
          <div class="row">
            <div><label>Login</label><input name="login" value="{config['login']}" /></div>
            <div><label>Password</label><input name="password" type="password" value="{config['password']}" /></div>
          </div>
          <div class="row">
            <div><label>Server</label><input name="server" value="{config['server']}" /></div>
            <div><label>Terminal Path</label><input name="terminal_path" value="{config['terminal_path']}" /></div>
          </div>
          <div class="row">
            <div><label>Symbol</label><input name="symbol" value="{config['symbol']}" /></div>
            <div><label>Magic</label><input name="magic" value="{config['magic']}" /></div>
          </div>
          <div class="row">
            <div><label>Base Lots</label><input name="base_lots" value="{config['base_lots']}" /></div>
            <div><label>Pending Lots</label><input name="pending_lots" value="{config['pending_lots']}" /></div>
          </div>
          <div class="row">
            <div><label>DCA Lots</label><input name="dca_lots" value="{config['dca_lots']}" /></div>
            <div><label>Target Profit USD</label><input name="target_profit_usd" value="{config['target_profit_usd']}" /></div>
          </div>
          <div class="row">
            <div>
              <label>TP Mode</label>
              <select name="tp_mode">
                <option value="money" {selected_money}>money</option>
                <option value="atr" {selected_atr}>atr</option>
              </select>
            </div>
            <div><label>Max Spread Points</label><input name="max_spread_points" value="{config['max_spread_points']}" /></div>
          </div>
          <div class="row">
            <div><label>Loop Seconds</label><input name="loop_seconds" value="{config['loop_seconds']}" /></div>
            <div>
              <label>Log Level</label>
              <select name="log_level">
                <option value="error" {selected_err}>error</option>
                <option value="info" {selected_info}>info</option>
                <option value="debug" {selected_debug}>debug</option>
              </select>
            </div>
          </div>
          <div class="row">
            <div><label>Live Log Path</label><input name="live_log_path" value="{config['live_log_path']}" /></div>
            <div style="display:flex;align-items:flex-end;"><label><input type="checkbox" name="disable_session_filter" {checked}/> Disable Session Filter</label></div>
          </div>
          <div class="line">
            <button type="submit">Save Config</button>
            <button type="submit" onclick="this.form.action.value='start';">Start Bot</button>
            <button type="submit" onclick="this.form.action.value='restart';">Restart Bot</button>
            <button class="stop" type="submit" onclick="this.form.action.value='stop';">Stop Bot</button>
            <button type="button" onclick="window.location='/';">Refresh</button>
          </div>
        </form>
      </div>
      <div class="panel">
        <h2>Live Runner Status</h2>
        <div id="runner-kpi" class="kpis"></div>
      </div>
      <div class="panel">
        <h2>MT5 Snapshot</h2>
        <div id="mt5-kpi" class="kpis"></div>
      </div>
      <div class="panel">
        <h2>Bot Positions</h2>
        <table id="positions-table">
          <thead><tr><th>Ticket</th><th>Type</th><th>Vol</th><th>Open</th><th>PnL</th><th>Comment</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Live Runner Log (tail)</h2>
        <pre id="live-log"></pre>
      </div>
      <div class="panel" style="grid-column: span 2;">
        <h2>Basket Event Log (tail)</h2>
        <table id="basket-table">
          <thead>
            <tr><th>timestamp</th><th>event</th><th>dir</th><th>lots</th><th>price</th><th>dd_daily</th><th>dd_float</th><th>note</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>
  <script>
    async function refreshApi() {{
      try {{
        const res = await fetch('/api/status');
        const data = await res.json();

        const runner = data.runner || {{}};
        document.getElementById('runner-kpi').innerHTML = `
          <div class="kpi"><span>Status</span><b class="${{runner.running ? 'status-running' : 'status-stopped'}}">${{runner.running ? 'RUNNING' : 'STOPPED'}}</b></div>
          <div class="kpi"><span>Managed</span><b>${{runner.managed ? 'YES' : 'NO'}}</b></div>
          <div class="kpi"><span>PID</span><b>${{runner.pid || '-'}}</b></div>
          <div class="kpi"><span>Updated</span><b>${{data.timestamp}}</b></div>
        `;

        const mt5 = data.mt5 || {{}};
        const acct = mt5.account || {{}};
        const term = mt5.terminal || {{}};
        const bot = mt5.bot || {{}};
        document.getElementById('mt5-kpi').innerHTML = `
          <div class="kpi"><span>Account</span><b>${{acct.login || '-'}}</b></div>
          <div class="kpi"><span>Balance</span><b>${{acct.balance ?? '-'}}</b></div>
          <div class="kpi"><span>Equity</span><b>${{acct.equity ?? '-'}}</b></div>
          <div class="kpi"><span>Algo Trading</span><b>${{term.trade_allowed ? 'ON' : 'OFF'}}</b></div>
          <div class="kpi"><span>Bot Pos</span><b>${{bot.position_count ?? 0}}</b></div>
          <div class="kpi"><span>Floating</span><b>${{bot.floating_profit ?? 0}}</b></div>
        `;

        const posRows = (mt5.positions || []).map(p => `
          <tr>
            <td>${{p.ticket}}</td>
            <td>${{p.type}}</td>
            <td>${{p.volume}}</td>
            <td>${{p.price_open}}</td>
            <td>${{p.profit}}</td>
            <td>${{p.comment || ''}}</td>
          </tr>
        `).join('');
        document.querySelector('#positions-table tbody').innerHTML = posRows || '<tr><td colspan="6">No bot positions</td></tr>';

        document.getElementById('live-log').textContent = data.live_log || '';

        const basketRows = (data.basket_rows || []).map(r => `
          <tr>
            <td>${{r.timestamp || ''}}</td>
            <td>${{r.event_type || ''}}</td>
            <td>${{r.direction || ''}}</td>
            <td>${{r.lots || ''}}</td>
            <td>${{r.price || ''}}</td>
            <td>${{r.dd_daily || ''}}</td>
            <td>${{r.dd_floating || ''}}</td>
            <td>${{r.note || ''}}</td>
          </tr>
        `).join('');
        document.querySelector('#basket-table tbody').innerHTML = basketRows || '<tr><td colspan="8">No basket events yet</td></tr>';
      }} catch (err) {{
        console.error(err);
      }}
    }}

    refreshApi();
    setInterval(refreshApi, 5000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str, status: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            cfg = _default_config()
            mt5_data = _mt5_snapshot(cfg)
            payload = {
                "timestamp": _utc_now(),
                "runner": APP_STATE.process_status(),
                "mt5": mt5_data,
                "live_log": _tail_text(Path(cfg.get("live_log_path", LIVE_LOG_PATH))),
                "basket_rows": _read_basket_csv(BASKET_LOG_PATH),
            }
            self._send_json(payload)
            return

        if parsed.path == "/":
            notice = ""
            query = parse_qs(parsed.query)
            if "msg" in query:
                notice = query["msg"][0]
            self._send_html(_render_html(_default_config(), notice=notice))
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/action":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        cfg = _parse_form(raw)
        action = parse_qs(raw).get("action", ["save"])[0]

        if action == "save":
            APP_STATE._remember_config(cfg)
            msg = "Config saved"
        elif action == "start":
            msg = APP_STATE.start_bot(cfg)["message"]
        elif action == "stop":
            msg = APP_STATE.stop_bot()["message"]
        elif action == "restart":
            msg = APP_STATE.restart_bot(cfg)["message"]
        else:
            msg = "Unknown action"

        self.send_response(303)
        self.send_header("Location", f"/?msg={msg}")
        self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"NowTrading Dashboard running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()

