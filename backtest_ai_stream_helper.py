from __future__ import annotations

import json
import re
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openai import OpenAI


HOST = "0.0.0.0"
PORT = 28180
MODEL = "gpt-5.4-mini"
THINKING_EFFORT = "low"
MAX_OUTPUT_TOKENS = 450
API_KEY = "pm-c66bd01e773bc2cbda09d0644a4c1822"
BASE_URL = "http://192.168.1.222:8087/v1"


def build_prompt(portfolio_context: str) -> str:
    return "\n".join(
        [
            "Return exactly one JSON object with keys: company_news, stock_performance, marketdata_summary, economy_status, industry_status, other_info, trade, hold_symbols, sources, reflection.",
            "Rules: use only sources with explicit publication timestamps on or before the cycle date; exclude ambiguous or undated sources; keep every text value concise; at most 6 total sources; choose exactly one highest-conviction trade for the cycle as BUY or SELL with integer quantity 1 if supported by dated evidence, otherwise set trade.action to HOLD; hold_symbols must list the remaining symbols from AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA.",
            "",
            "Cycle context:",
            portfolio_context.strip(),
        ]
    )


def extract_cycle_date(portfolio_context: str) -> date | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", portfolio_context)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d").date()


def stream_analysis(portfolio_context: str) -> dict:
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=120)
    prompt = build_prompt(portfolio_context)
    chunks: list[str] = []
    with client.responses.stream(
        model=MODEL,
        input=prompt,
        reasoning={"effort": THINKING_EFFORT},
        tools=[{"type": "web_search", "search_context_size": "high"}],
        max_output_tokens=MAX_OUTPUT_TOKENS,
    ) as stream:
        for event in stream:
            if getattr(event, "type", "") == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    chunks.append(delta)
        final = stream.get_final_response()
    return {
        "status": getattr(final, "status", None),
        "text": "".join(chunks),
    }


def normalize_source(item: object) -> dict[str, str | None]:
    if isinstance(item, dict):
        return {
            "title": item.get("title") or item.get("name") or "Untitled source",
            "published": item.get("published")
            or item.get("published_at")
            or item.get("date"),
            "url": item.get("url") or item.get("link") or "",
        }

    if isinstance(item, str):
        parts = [part.strip() for part in item.split("|")]
        if len(parts) >= 3:
            return {
                "title": parts[0],
                "published": parts[1],
                "url": parts[2],
            }
        return {
            "title": item,
            "published": None,
            "url": "",
        }

    return {
        "title": "Untitled source",
        "published": None,
        "url": "",
    }


def parse_source_date(value: str | None) -> date | None:
    if not value:
        return None
    iso_match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if not iso_match:
        return None
    return datetime.strptime(iso_match.group(0), "%Y-%m-%d").date()


def normalize_trade(parsed: dict[str, object]) -> dict[str, object]:
    trade = parsed.get("trade")
    if isinstance(trade, dict):
        action = str(trade.get("action", "HOLD")).upper()
        symbol = str(trade.get("symbol", "")).upper()
        quantity = trade.get("quantity", 1)
        if action in {"BUY", "SELL", "HOLD"} and symbol:
            return {
                "action": action,
                "symbol": symbol,
                "quantity": quantity if quantity is not None else 1,
            }

    reflection = str(parsed.get("reflection", ""))
    match = re.search(r"\b(BUY|SELL)\s+([A-Z]{1,6})\b", reflection)
    if match:
        return {
            "action": match.group(1),
            "symbol": match.group(2),
            "quantity": 1,
        }

    return {
        "action": "HOLD",
        "symbol": "",
        "quantity": 1,
    }


def normalize_payload(
    parsed: dict[str, object], cycle_date: date | None
) -> dict[str, object]:
    normalized = dict(parsed)
    raw_sources = parsed.get("sources", [])
    source_items = raw_sources if isinstance(raw_sources, list) else []
    normalized["trade"] = normalize_trade(parsed)
    normalized_sources = [normalize_source(item) for item in source_items]
    valid_sources: list[dict[str, str | None]] = []
    for source in normalized_sources:
        source_dt = parse_source_date(source.get("published"))
        if source_dt is None:
            continue
        if cycle_date is not None and source_dt > cycle_date:
            continue
        valid_sources.append(
            {
                "title": source["title"],
                "published": source_dt.isoformat() + "T00:00:00Z",
                "url": source["url"],
            }
        )
    normalized["sources"] = valid_sources[:6]
    return normalized


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/analyze":
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))
            portfolio_context = payload["portfolio_context"]

            result = stream_analysis(portfolio_context)
            cycle_date = extract_cycle_date(portfolio_context)
            parsed = normalize_payload(json.loads(result["text"]), cycle_date)

            body = json.dumps(
                {
                    "status": result["status"],
                    "parsed": parsed,
                    "raw_text": result["text"],
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Backtest AI stream helper listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
