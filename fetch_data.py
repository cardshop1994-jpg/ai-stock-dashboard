# -*- coding: utf-8 -*-
"""
AI サプライチェーン監視ダッシュボード用 データ生成スクリプト.

「これから注目のAI関連銘柄チーム」を毎日ウォッチするためのデータを作る。
各銘柄について 株価/前日比/5日・1ヶ月・1年騰落/1年高値からの下落率/出来高比/
配当利回り/1年ぶんの値動き(スパークライン用)/ニュース を取得し、
data.json と data.js（window.SITE_DATA=...）を index.html の隣に書き出す。

米国株(USD)・日本株(.T=JPY)・韓国株(.KS=KRW) が混在するので、円換算も付ける。

実行:
  $env:PYTHONUTF8="1"; $env:PYTHONIOENCODING="utf-8"; chcp 65001 > $null
  & <python> fetch_data.py
"""
from __future__ import annotations
import json, datetime, os
import yfinance as yf

# ============================ CONFIG ============================
# テーマ順のウォッチリスト。 (ticker, 表示名, 通貨, 国籍) 通貨: USD / JPY / KRW
# 「AI開発に必要なもの」= 電力・半導体 の "その先" を握る会社たち。
THEMES = [
    ("メモリ (HBM)", "AIチップに必須の広帯域メモリ。今いちばんの品薄部材。", [
        ("000660.KS", "SKハイニックス", "KRW", "🇰🇷 韓国"),
        ("MU",        "マイクロン",     "USD", "🇺🇸 米国"),
    ]),
    ("ネットワーク / AIチップ", "GPUを何万個も束ねるスイッチ・カスタムASIC。", [
        ("AVGO", "ブロードコム", "USD", "🇺🇸 米国"),
        ("MRVL", "マーベル",     "USD", "🇺🇸 米国"),
        ("ANET", "アリスタ",     "USD", "🇺🇸 米国"),
    ]),
    ("光通信", "サーバー間を光でつなぐ光トランシーバ・光ファイバ。", [
        ("LITE",  "ルメンタム",     "USD", "🇺🇸 米国"),
        ("COHR",  "コヒレント",     "USD", "🇺🇸 米国"),
        ("FN",    "ファブリネット", "USD", "🇹🇭 タイ"),
        ("5803.T","フジクラ",       "JPY", "🇯🇵 日本"),
    ]),
    ("冷却・電源", "最新GPUの熱と電気をさばく 液冷/電源インフラ。", [
        ("VRT", "ヴァーティブ", "USD", "🇺🇸 米国"),
        ("ETN", "イートン",     "USD", "🇺🇸 米国"),
    ]),
    ("発電・原子力・ウラン", "電力そのもの。発電所・送電網・核燃料まで。", [
        ("GEV", "GEベルノバ",       "USD", "🇺🇸 米国"),
        ("PWR", "クアンタ",         "USD", "🇺🇸 米国"),
        ("CEG", "コンステレーション","USD", "🇺🇸 米国"),
        ("VST", "ビストラ",         "USD", "🇺🇸 米国"),
        ("CCJ", "カメコ (ウラン)",  "USD", "🇨🇦 カナダ"),
    ]),
    ("データセンター REIT", "AIサーバーを置く土地・建物。", [
        ("EQIX", "エクイニクス",       "USD", "🇺🇸 米国"),
        ("DLR",  "デジタルリアルティ", "USD", "🇺🇸 米国"),
    ]),
    ("製造装置・先端パッケージング", "GPUとHBMを貼り合わせる後工程・IC基板・製造装置。", [
        ("ASML",  "ASML",           "USD", "🇳🇱 オランダ"),
        ("AMAT",  "アプライドM",    "USD", "🇺🇸 米国"),
        ("LRCX",  "ラムリサーチ",   "USD", "🇺🇸 米国"),
        ("6857.T","アドバンテスト", "JPY", "🇯🇵 日本"),
        ("8035.T","東京エレクトロン","JPY", "🇯🇵 日本"),
        ("6146.T","ディスコ",       "JPY", "🇯🇵 日本"),
        ("4062.T","イビデン",       "JPY", "🇯🇵 日本"),
    ]),
]
# ===============================================================

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def fx_rate(pair: str) -> float | None:
    """USD建て為替。 pair 例 'JPY=X'(USD/JPY), 'KRW=X'(USD/KRW)."""
    try:
        h = yf.Ticker(pair).history(period="5d")["Close"].dropna()
        return float(h.iloc[-1]) if len(h) else None
    except Exception:
        return None


def clean_closes(hist):
    """>40% の1日変動(分割/データ不良)以降だけを使い、指標が段差をまたがないようにする。"""
    closes = hist["Close"].dropna()
    if len(closes) < 10:
        return closes if len(closes) >= 2 else None, False
    jumps = closes.pct_change().abs()
    big = jumps[jumps > 0.4]
    if len(big):
        closes = closes.loc[big.index[-1]:]
        return (closes if len(closes) >= 2 else None), True
    return closes, False


def downsample(vals, n=64):
    """スパークライン用に等間隔で最大 n 点へ間引く（最初と最後は必ず含む）。"""
    m = len(vals)
    if m <= n:
        return [round(float(v), 4) for v in vals]
    idx = [round(i * (m - 1) / (n - 1)) for i in range(n)]
    return [round(float(vals[i]), 4) for i in sorted(set(idx))]


def get_news(t):
    out = []
    try:
        for it in (t.news or [])[:5]:
            c = it.get("content", it) if isinstance(it, dict) else {}
            title = c.get("title") or (it.get("title") if isinstance(it, dict) else None)
            url = None
            for key in ("canonicalUrl", "clickThroughUrl"):
                v = c.get(key)
                if isinstance(v, dict) and v.get("url"):
                    url = v["url"]; break
            if not url and isinstance(it, dict):
                url = it.get("link")
            if title and url:
                out.append({"t": title[:120], "u": url})
            if len(out) >= 2:
                break
    except Exception:
        pass
    return out


def yield_pct(t, price, adjusted):
    if adjusted:
        return None
    try:
        divs = t.dividends
        if len(divs) == 0:
            return None
        import pandas as pd
        cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.Timedelta(days=365)
        last12 = divs[divs.index >= cutoff]
        return round(float(last12.sum()) / price * 100, 2) if len(last12) else None
    except Exception:
        return None


def to_jpy(cur, val, usdjpy, usdkrw):
    if val is None:
        return None
    if cur == "JPY":
        return val
    if cur == "USD" and usdjpy:
        return val * usdjpy
    if cur == "KRW" and usdjpy and usdkrw:
        return val * (usdjpy / usdkrw)
    return None


def fetch_row(ticker, name, cur, country, theme, usdjpy, usdkrw):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        closes, adjusted = clean_closes(hist)
        if closes is None:
            return None
        vals = list(closes.values)
        price = float(vals[-1]); hi = float(max(vals)); lo = float(min(vals)); n = len(vals)

        def chg(back):
            return round((price / float(vals[-1 - back]) - 1) * 100, 1) if n > back else None
        chg1d = chg(1)
        chg5d = chg(5)
        chg1mo = chg(21)
        chg1y = round((price / float(vals[0]) - 1) * 100, 1)

        # 出来高比 (直近 / 20日平均)
        relvol = None
        try:
            vol = hist["Volume"].dropna()
            if len(vol) >= 21 and float(vol.tail(20).mean()) > 0:
                relvol = round(float(vol.iloc[-1]) / float(vol.tail(20).mean()), 2)
        except Exception:
            pass

        # 時価総額 (円換算・兆円)
        mcap_jpy = None
        try:
            mc = t.fast_info.get("market_cap") if hasattr(t.fast_info, "get") else t.fast_info["market_cap"]
            j = to_jpy(cur, float(mc), usdjpy, usdkrw)
            if j:
                mcap_jpy = round(j / 1e12, 2)  # 兆円
        except Exception:
            pass

        dec = 0 if cur in ("JPY", "KRW") else 2
        return {
            "code": ticker, "yf": ticker, "name": name, "theme": theme, "cur": cur,
            "country": country,
            "price": round(price, dec),
            "jpy": (round(to_jpy(cur, price, usdjpy, usdkrw)) if cur != "JPY" else None),
            "high1y": round(hi, dec), "low1y": round(lo, dec),
            "drawdown": round((price / hi - 1) * 100, 1),
            "chg1d": chg1d, "chg5d": chg5d, "chg1mo": chg1mo, "chg1y": chg1y,
            "relvol": relvol, "yield_pct": yield_pct(t, price, adjusted),
            "mcap_jpy": mcap_jpy, "adjusted": adjusted,
            "spark": downsample(vals, 64), "news": get_news(t),
        }
    except Exception as e:
        print(f"  [warn] {ticker}: {e}")
        return None


def main():
    jst = datetime.timezone(datetime.timedelta(hours=9))
    print("為替を取得中 ...")
    usdjpy = fx_rate("JPY=X"); usdkrw = fx_rate("KRW=X")
    print(f"  USD/JPY={usdjpy}  USD/KRW={usdkrw}")

    groups = []
    for theme, note, members in THEMES:
        rows = []
        for ticker, name, cur, country in members:
            print(f"取得: {ticker} ({name}) ...")
            r = fetch_row(ticker, name, cur, country, theme, usdjpy, usdkrw)
            if r:
                rows.append(r)
        rows.sort(key=lambda r: (r["chg1d"] if r["chg1d"] is not None else -999), reverse=True)
        groups.append({"theme": theme, "note": note, "rows": rows})

    data = {
        "updated": datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M") + " JST",
        "fx": {"usdjpy": usdjpy, "usdkrw": usdkrw},
        "groups": groups,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(os.path.dirname(OUT), "data.js"), "w", encoding="utf-8") as f:
        f.write("window.SITE_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";")
    total = sum(len(g["rows"]) for g in groups)
    print(f"\nwrote data.json / data.js : {total} 銘柄, {len(groups)} テーマ")


if __name__ == "__main__":
    main()
