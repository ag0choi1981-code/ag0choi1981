#!/usr/bin/env python3
"""
대한민국 부처/장관 유튜브 채널 구독자 수 조회기

기능:
- 최신 장관 명단 자동 수집(위키백과 "이재명 정부" 페이지 우선)
- YouTube Data API 사용(키가 없으면 BeautifulSoup 기반 크롤링 폴백)
- 부처명/장관명/채널명 검색 필터
- 표 형태 출력 + CSV 저장

주의:
- 유튜브 HTML 구조 변경 시 크롤링 폴백이 실패할 수 있습니다.
- 정확도를 높이려면 YOUTUBE_API_KEY 환경변수 설정을 권장합니다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

WIKI_URL = "https://ko.wikipedia.org/wiki/이재명_정부"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# 자동 수집 실패 시 사용하는 기본값(2026년 예시; 필요 시 수정)
LOCAL_FALLBACK = [
    {"ministry": "기획재정부", "minister": "구윤철"},
    {"ministry": "과학기술정보통신부", "minister": "배경훈"},
    {"ministry": "교육부", "minister": "최교진"},
    {"ministry": "외교부", "minister": "(확인필요)"},
    {"ministry": "통일부", "minister": "(확인필요)"},
    {"ministry": "법무부", "minister": "정성호"},
    {"ministry": "국방부", "minister": "(확인필요)"},
    {"ministry": "행정안전부", "minister": "윤호중"},
    {"ministry": "국가보훈부", "minister": "권오을"},
    {"ministry": "문화체육관광부", "minister": "최휘영"},
    {"ministry": "농림축산식품부", "minister": "송미령"},
    {"ministry": "산업통상자원부", "minister": "김정관"},
    {"ministry": "보건복지부", "minister": "정은경"},
    {"ministry": "환경부", "minister": "김성환"},
    {"ministry": "고용노동부", "minister": "김영훈"},
    {"ministry": "여성가족부", "minister": "원민경"},
    {"ministry": "국토교통부", "minister": "김윤덕"},
    {"ministry": "해양수산부", "minister": "(확인필요)"},
    {"ministry": "중소벤처기업부", "minister": "한성숙"},
]

MINISTRY_PATTERNS = [
    "기획재정부",
    "교육부",
    "과학기술정보통신부",
    "외교부",
    "통일부",
    "법무부",
    "국방부",
    "행정안전부",
    "국가보훈부",
    "문화체육관광부",
    "농림축산식품부",
    "산업통상자원부",
    "보건복지부",
    "환경부",
    "고용노동부",
    "여성가족부",
    "국토교통부",
    "해양수산부",
    "중소벤처기업부",
]


@dataclass
class MinistryRecord:
    ministry: str
    minister: str


@dataclass
class ChannelResult:
    ministry: str
    minister: str
    channel_name: str
    subscribers: str


def http_get(url: str, **kwargs) -> requests.Response:
    """
    Use a clean session that ignores broken environment proxy settings.
    This helps when HTTP(S)_PROXY points to an invalid local proxy.
    """
    with requests.Session() as s:
        s.trust_env = False
        return s.get(url, **kwargs)


def safe_get(url: str, timeout: int = 20, headers: dict | None = None) -> requests.Response:
    h = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
    }
    if headers:
        h.update(headers)
    r = http_get(url, timeout=timeout, headers=h)
    r.raise_for_status()
    return r


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def clean_name(s: str) -> str:
    s = re.sub(r"\[[^\]]+\]", "", s)
    s = re.sub(r"\([^)]*\)", "", s)
    return normalize_text(s)


def is_ministry_name(name: str) -> bool:
    return any(p in name for p in MINISTRY_PATTERNS)


def fetch_latest_ministers_from_wiki() -> list[MinistryRecord]:
    """
    ko.wikipedia.org/wiki/이재명_정부 내 표에서 부처-장관 쌍 추출.
    표 구조가 달라져도 최대한 유연하게 파싱한다.
    """
    r = safe_get(WIKI_URL)
    soup = BeautifulSoup(r.text, "html.parser")

    records: list[MinistryRecord] = []

    for table in soup.select("table.wikitable"):
        header_cells = [normalize_text(th.get_text(" ", strip=True)) for th in table.select("tr th")]
        if not header_cells:
            continue

        has_ministry_col = any("부처" in h or "기관" in h for h in header_cells)
        has_minister_col = any("장관" in h or "국무위원" in h for h in header_cells)
        if not (has_ministry_col and has_minister_col):
            continue

        # 헤더 위치 추정
        header_row = table.select_one("tr")
        header_titles = [normalize_text(x.get_text(" ", strip=True)) for x in header_row.select("th,td")]
        ministry_idx = next(
            (i for i, h in enumerate(header_titles) if "부처" in h or "기관" in h),
            None,
        )
        minister_idx = next(
            (i for i, h in enumerate(header_titles) if "장관" in h or "국무위원" in h),
            None,
        )
        if ministry_idx is None or minister_idx is None:
            continue

        for tr in table.select("tr")[1:]:
            tds = tr.select("th,td")
            if len(tds) <= max(ministry_idx, minister_idx):
                continue

            ministry = clean_name(tds[ministry_idx].get_text(" ", strip=True))
            minister = clean_name(tds[minister_idx].get_text(" ", strip=True))

            if not ministry or not minister:
                continue
            if not is_ministry_name(ministry):
                continue

            records.append(MinistryRecord(ministry=ministry, minister=minister))

    # 중복 제거 (마지막 값을 우선)
    merged: dict[str, str] = {}
    for rec in records:
        merged[rec.ministry] = rec.minister

    result = [MinistryRecord(ministry=k, minister=v) for k, v in merged.items()]

    # 주요 19개 부처만 정렬
    order = {m: i for i, m in enumerate(MINISTRY_PATTERNS)}
    result.sort(key=lambda x: order.get(x.ministry, 999))

    return result


def load_ministers(local_json_path: Path | None = None) -> list[MinistryRecord]:
    # 1) 위키 자동 수집
    try:
        wiki_data = fetch_latest_ministers_from_wiki()
        if wiki_data:
            return wiki_data
    except Exception:
        pass

    # 2) 사용자가 준 로컬 JSON
    if local_json_path and local_json_path.exists():
        # Handle UTF-8 BOM and editor-specific encodings safely.
        try:
            with local_json_path.open("r", encoding="utf-8-sig") as f:
                raw = json.load(f)
        except json.JSONDecodeError:
            text = local_json_path.read_text(encoding="utf-8", errors="replace")
            text = text.lstrip("\ufeff")
            raw = json.loads(text)
        return [MinistryRecord(ministry=x["ministry"], minister=x["minister"]) for x in raw]

    # 3) 내장 fallback
    return [MinistryRecord(ministry=x["ministry"], minister=x["minister"]) for x in LOCAL_FALLBACK]


def youtube_api_search_channel(query: str, api_key: str) -> tuple[str, str] | None:
    params = {
        "part": "snippet",
        "type": "channel",
        "q": query,
        "maxResults": 1,
        "key": api_key,
        "regionCode": "KR",
        "relevanceLanguage": "ko",
    }
    r = http_get(f"{YOUTUBE_API_BASE}/search", params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    items = data.get("items", [])
    if not items:
        return None

    item = items[0]
    channel_id = item["snippet"]["channelId"]
    channel_name = item["snippet"]["channelTitle"]
    return channel_id, channel_name


def youtube_api_subscribers(channel_id: str, api_key: str) -> str | None:
    params = {
        "part": "statistics,snippet",
        "id": channel_id,
        "key": api_key,
    }
    r = http_get(f"{YOUTUBE_API_BASE}/channels", params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    items = data.get("items", [])
    if not items:
        return None

    stats = items[0].get("statistics", {})
    sub = stats.get("subscriberCount")
    if sub is None:
        return None
    try:
        return f"{int(sub):,}"
    except Exception:
        return str(sub)


def scrape_youtube_search_channels(query: str, limit: int = 5) -> list[tuple[str, str]]:
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    r = safe_get(url)
    html = r.text

    # channelRenderer 단위로 채널 후보를 여러 개 추출
    # (첫 결과가 공식 채널이 아닐 수 있어 다중 후보를 시도)
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(r'"channelRenderer":\{(.*?)\}\}\}\}', html):
        block = m.group(1)
        m_id = re.search(r'"channelId":"([^"]+)"', block)
        if not m_id:
            continue
        channel_id = m_id.group(1)
        if channel_id in seen:
            continue
        seen.add(channel_id)

        m_name = re.search(r'"title":\{"simpleText":"([^"]+)"\}', block)
        channel_name = unescape(m_name.group(1)) if m_name else f"channel:{channel_id}"
        results.append((channel_id, channel_name))
        if len(results) >= limit:
            break

    # channelRenderer 파싱 실패 시 기존 단일 패턴으로 마지막 폴백
    if not results:
        m_id = re.search(r'"channelId":"([^"]+)"', html)
        if m_id:
            channel_id = m_id.group(1)
            m_name = re.search(r'"title":\{"simpleText":"([^"]+)"\}', html)
            channel_name = unescape(m_name.group(1)) if m_name else f"channel:{channel_id}"
            results.append((channel_id, channel_name))

    return results


def scrape_youtube_search_first_channel(query: str) -> tuple[str, str] | None:
    channels = scrape_youtube_search_channels(query=query, limit=1)
    return channels[0] if channels else None


def scrape_youtube_subscribers(channel_id: str) -> str | None:
    url = f"https://www.youtube.com/channel/{channel_id}"
    r = safe_get(url)
    html = r.text

    patterns = [
        r'"subscriberCountText":\{"accessibility":\{"accessibilityData":\{"label":"([^"]+)"\}\}\}',
        r'"subscriberCountText":\{"simpleText":"([^"]+)"\}',
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return unescape(m.group(1))

    # JSON-LD fallback
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        txt = script.get_text(strip=True)
        if "interactionStatistic" in txt and "userInteractionCount" in txt:
            m = re.search(r'"userInteractionCount"\s*:\s*"?(\d+)"?', txt)
            if m:
                return f"{int(m.group(1)):,}"

    return None


def _decode_json_escaped_text(text: str) -> str:
    if "\\u" not in text and "\\x" not in text:
        return text
    try:
        return bytes(text, "utf-8").decode("unicode_escape")
    except Exception:
        return text


def scrape_youtube_subscribers_from_url(channel_url: str) -> str | None:
    """
    Scrape subscriber count directly from a known channel URL
    (e.g. https://www.youtube.com/@moelkorea).
    """
    r = safe_get(channel_url)
    html = r.text

    patterns = [
        # Korean escaped string in accessibilityLabel: "\\uad6c\\ub3c5\\uc790 14\\ub9cc\\uba85"
        r'"accessibilityLabel":"\\uad6c\\ub3c5\\uc790 ([^"]+)"',
        # Korean plain string fallback
        r'"accessibilityLabel":"구독자 ([^"]+)"',
        # content field fallback
        r'"content":"\\uad6c\\ub3c5\\uc790 ([^"]+)"',
        # English locale fallback
        r'"accessibilityLabel":"([^"]*subscribers[^"]*)"',
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            value = _decode_json_escaped_text(m.group(1)).strip()
            value = value.replace("\\u00a0", " ").replace("\xa0", " ")
            return value

    return None


def resolve_channel_and_subscribers(query: str, api_key: str | None) -> tuple[str, str]:
    if api_key:
        try:
            found = youtube_api_search_channel(query, api_key)
            if found:
                cid, cname = found
                sub = youtube_api_subscribers(cid, api_key) or "N/A"
                return cname, sub
        except Exception:
            pass

    # BeautifulSoup/HTML 파싱 폴백
    try:
        candidates = scrape_youtube_search_channels(query=query, limit=7)
        for cid, cname in candidates:
            sub = scrape_youtube_subscribers(cid)
            if sub and sub != "N/A":
                return cname, sub
        if candidates:
            # 후보는 찾았지만 구독자 파싱이 실패한 경우
            return candidates[0][1], "N/A"
    except Exception:
        pass

    return "N/A", "N/A"


def build_rows(
    ministers: Iterable[MinistryRecord],
    api_key: str | None,
    mode: str,
) -> list[ChannelResult]:
    rows: list[ChannelResult] = []

    for rec in ministers:
        queries: list[str] = []

        if mode in ("both", "ministry"):
            queries.append(f"{rec.ministry} 공식 유튜브")
        if mode in ("both", "minister") and rec.minister and rec.minister != "(확인필요)":
            queries.append(f"{rec.minister} 유튜브")

        if not queries:
            rows.append(
                ChannelResult(
                    ministry=rec.ministry,
                    minister=rec.minister,
                    channel_name="N/A",
                    subscribers="N/A",
                )
            )
            continue

        for q in queries:
            cname, subs = resolve_channel_and_subscribers(q, api_key)
            rows.append(
                ChannelResult(
                    ministry=rec.ministry,
                    minister=rec.minister,
                    channel_name=cname,
                    subscribers=subs,
                )
            )

    return rows


def filter_rows(rows: list[ChannelResult], query: str | None) -> list[ChannelResult]:
    if not query:
        return rows
    q = query.lower().strip()
    return [
        r
        for r in rows
        if q in r.ministry.lower() or q in r.minister.lower() or q in r.channel_name.lower()
    ]


def print_table(rows: list[ChannelResult]) -> None:
    headers = ["부처명", "장관 이름", "채널명", "구독자 수"]
    data = [[r.ministry, r.minister, r.channel_name, r.subscribers] for r in rows]

    widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def fmt_line(values: list[str]) -> str:
        return " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(values))

    sep = "-+-".join("-" * w for w in widths)
    print(fmt_line(headers))
    print(sep)
    for row in data:
        print(fmt_line(row))


def save_csv(rows: list[ChannelResult], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["부처명", "장관 이름", "채널명", "구독자 수"])
        for r in rows:
            writer.writerow([r.ministry, r.minister, r.channel_name, r.subscribers])


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="대한민국 부처/장관 유튜브 채널 구독자 수 조회 및 CSV 저장",
    )
    p.add_argument(
        "--query",
        type=str,
        default=None,
        help="부처명/장관명/채널명 검색어 (부분일치)",
    )
    p.add_argument(
        "--mode",
        type=str,
        choices=["both", "ministry", "minister"],
        default="both",
        help="조회 대상: both(기본), ministry, minister",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("kr_ministry_youtube_subscribers.csv"),
        help="CSV 저장 경로",
    )
    p.add_argument(
        "--ministers-json",
        type=Path,
        default=Path("ministries_2026.json"),
        help="위키 수집 실패 시 사용할 로컬 장관명단 JSON 경로",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    api_key = os.getenv("YOUTUBE_API_KEY")
    ministers = load_ministers(args.ministers_json)

    if not ministers:
        print("장관 명단을 가져오지 못했습니다.", file=sys.stderr)
        return 1

    rows = build_rows(ministers=ministers, api_key=api_key, mode=args.mode)
    rows = filter_rows(rows, args.query)

    print_table(rows)
    save_csv(rows, args.output)

    print(f"\nCSV 저장 완료: {args.output.resolve()}")
    if not api_key:
        print("참고: YOUTUBE_API_KEY가 없어 BeautifulSoup/HTML 파싱 폴백이 사용될 수 있습니다.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
