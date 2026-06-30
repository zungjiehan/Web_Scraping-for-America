"""
美股排行榜抓取（Alpha Vantage API 版）
資料來源：Alpha Vantage TOP_GAINERS_LOSERS

產生兩份 CSV：
  data/{今天日期}/美股排行榜.csv（漲幅/跌幅/成交量前20）
  data/{今天日期}/美股收盤價.csv（所有上榜個股）

使用方式：
  1. 把你的 Alpha Vantage API Key 填入下方 ALPHA_VANTAGE_KEY
  2. python3 fetch_america_stocks.py                # 整批抓排行榜
  3. python3 fetch_america_stocks.py --symbol AAPL  # 查單一代號（用 Yahoo Finance，
                                                       因 Alpha Vantage 的排行榜API無法查任意代號）
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# ─────────────────────────────────────────────
# ⚠️ 填入你的 Alpha Vantage API Key
# ─────────────────────────────────────────────
ALPHA_VANTAGE_KEY = "BX0SNSFNXFFJG4O5"

TODAY = date.today().strftime("%Y-%m-%d")
DATA_DIR = Path("data") / TODAY

HEADERS = {"User-Agent": "Mozilla/5.0"}
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


def fetch_rankings() -> dict:
    """抓取美股漲幅/跌幅/成交量排行"""
    print("  抓取美股排行榜（Alpha Vantage）...", flush=True)
    url = f"https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey={ALPHA_VANTAGE_KEY}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        print(f"  [錯誤] 排行榜取得失敗: {r.status_code}")
        return {}
    data = r.json()
    print(f"  資料更新時間：{data.get('last_updated', '未知')}", flush=True)
    return data


def build_ranking_csv(data: dict) -> pd.DataFrame:
    """組合排行榜 CSV"""
    all_records = []

    mapping = [
        ("漲幅排行", "top_gainers"),
        ("跌幅排行", "top_losers"),
        ("成交量排行", "most_actively_traded"),
    ]

    for rank_type, key in mapping:
        items = data.get(key, [])
        for i, item in enumerate(items, 1):
            ticker = item.get("ticker", "")
            price = float(item.get("price", 0) or 0)
            change_amount = float(item.get("change_amount", 0) or 0)
            change_pct_str = item.get("change_percentage", "0%").replace("%", "")
            try:
                change_pct = float(change_pct_str)
            except:
                change_pct = 0.0
            volume = int(float(item.get("volume", 0) or 0))

            all_records.append({
                "排行類型": rank_type,
                "名次": i,
                "代號": ticker,
                "股價": price,
                "漲跌": change_amount,
                "漲跌幅(%)": f"{change_pct:.2f}%",
                "成交量": volume,
            })

    return pd.DataFrame(all_records)


def build_price_csv(data: dict) -> pd.DataFrame:
    """組合所有上榜個股的收盤價 CSV（去重）"""
    seen = set()
    rows = []

    for key in ["top_gainers", "top_losers", "most_actively_traded"]:
        for item in data.get(key, []):
            ticker = item.get("ticker", "")
            if ticker in seen:
                continue
            seen.add(ticker)

            price = float(item.get("price", 0) or 0)
            change_amount = float(item.get("change_amount", 0) or 0)
            change_pct_str = item.get("change_percentage", "0%").replace("%", "")
            try:
                change_pct = float(change_pct_str)
            except:
                change_pct = 0.0
            volume = int(float(item.get("volume", 0) or 0))
            prev_close = round(price - change_amount, 4) if price and change_amount else 0.0

            rows.append({
                "代號": ticker,
                "股價(收盤/最新)": price,
                "漲跌": change_amount,
                "漲跌幅(%)": f"{change_pct:.2f}%",
                "昨收": prev_close,
                "成交量": volume,
                "時間": TODAY,
            })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# 單一代號查詢模式（給跨市場對應股價用）
# 改用 Yahoo Finance，因為 Alpha Vantage 的
# TOP_GAINERS_LOSERS 只回傳排行榜內股票，查不到任意代號
# ─────────────────────────────────────────────

def fetch_yahoo_price(ticker: str) -> dict | None:
    """用 Yahoo Finance 查詢單一美股代號當日資料"""
    ticker = ticker.strip().upper()
    url = f"{YAHOO_BASE}/{ticker}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        result = r.json().get("chart", {}).get("result", [])
        if not result:
            return None
        meta = result[0].get("meta", {})
        close = float(meta.get("regularMarketPrice", 0) or 0)
        prev_close = float(meta.get("chartPreviousClose", 0) or meta.get("previousClose", 0) or 0)
        if close == 0:
            return None
        change = round(close - prev_close, 4) if prev_close else 0.0
        change_pct = round((change / prev_close * 100), 2) if prev_close else 0.0
        return {
            "代號": ticker,
            "收盤": close,
            "漲跌": change,
            "漲跌幅": change_pct,
            "昨收": prev_close,
        }
    except Exception:
        return None


def cmd_single_symbol(ticker: str):
    """CLI 單一代號查詢，輸出 JSON 方便 Claude Code 解析"""
    result = fetch_yahoo_price(ticker)
    if result is None:
        print(json.dumps({"代號": ticker, "找到": False}, ensure_ascii=False))
        sys.exit(1)
    output = {
        "代號": result["代號"],
        "找到": True,
        "收盤": result["收盤"],
        "漲跌幅(%)": result["漲跌幅"],
        "資料日期": TODAY,
        "資料來源": "Yahoo Finance（單一代號查詢，非Alpha Vantage排行榜）",
    }
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print(f"=== 美股排行榜資料抓取 ===")
    print(f"執行日期：{TODAY}\n")

    if ALPHA_VANTAGE_KEY == "填入你的API_KEY":
        print("[錯誤] 請先填入 ALPHA_VANTAGE_KEY")
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    data = fetch_rankings()
    if not data:
        print("[錯誤] 無法取得排行榜資料")
        sys.exit(1)

    rank_df = build_ranking_csv(data)
    price_df = build_price_csv(data)

    rank_df.to_csv(DATA_DIR / "美股排行榜.csv", index=False, encoding="utf-8-sig")
    price_df.to_csv(DATA_DIR / "美股收盤價.csv", index=False, encoding="utf-8-sig")

    print(f"\n[完成] 美股排行榜.csv：{len(rank_df)} 筆")
    print(f"[完成] 美股收盤價.csv：{len(price_df)} 筆")

    ok = True
    if len(rank_df) < 30:
        print(f"[驗證失敗] 排行榜 {len(rank_df)} < 30 筆"); ok = False
    if ok:
        print("[驗證通過]")
    return ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", help="只查詢單一代號的當日漲跌幅（用Yahoo Finance，不執行整批爬蟲）")
    args = parser.parse_args()

    if args.symbol:
        cmd_single_symbol(args.symbol)
    else:
        sys.exit(0 if main() else 1)
