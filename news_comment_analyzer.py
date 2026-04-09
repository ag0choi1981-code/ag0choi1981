from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

ARTICLE_SELECTORS = [
    "article",
    "#articleBodyContents",
    ".article_body",
    ".news_end",
    ".article-view-content-div",
    ".story-news",
    ".article_txt",
    ".article__content",
    ".article-content",
    ".post-content",
    "main",
]

COMMENT_SELECTORS = [
    ".comment",
    ".comments li",
    ".comment-list li",
    ".reply",
    "[class*='comment'] p",
    "[id*='comment'] li",
]

STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "from",
    "this",
    "have",
    "will",
    "about",
    "news",
    "article",
    "report",
    "said",
    "there",
    "their",
    "they",
    "were",
    "been",
    "into",
    "than",
    "then",
    "when",
    "where",
    "korea",
    "korean",
}

POSITIVE_WORDS = {
    "good",
    "great",
    "best",
    "nice",
    "support",
    "thanks",
    "thank",
    "excellent",
    "love",
    "hope",
    "agree",
    "useful",
    "positive",
}

NEGATIVE_WORDS = {
    "bad",
    "worst",
    "problem",
    "issue",
    "angry",
    "worry",
    "concern",
    "hate",
    "fail",
    "failure",
    "disagree",
    "critic",
    "negative",
}


@dataclass
class AnalysisResult:
    url: str
    domain: str
    title: str
    article_text: str
    article_summary: str
    article_keywords: list[str]
    total_comments: int
    comment_keywords: list[str]
    sentiment_counts: dict[str, int]
    comments: list[dict[str, str]]


def fetch_html(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[\.\!\?])\s+", text)
    return [s.strip() for s in raw if s.strip()]


def extract_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.text:
        return clean_text(soup.title.text)
    meta = soup.find("meta", attrs={"property": "og:title"})
    if meta and meta.get("content"):
        return clean_text(meta["content"])
    return "Untitled"


def extract_article_text(soup: BeautifulSoup) -> str:
    candidates: list[str] = []

    for sel in ARTICLE_SELECTORS:
        for node in soup.select(sel):
            txt = clean_text(node.get_text(" ", strip=True))
            if len(txt) >= 120:
                candidates.append(txt)

    if not candidates:
        paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
        paragraphs = [p for p in paragraphs if len(p) >= 40]
        merged = " ".join(paragraphs)
        return merged[:10000] if merged else ""

    candidates.sort(key=len, reverse=True)
    return candidates[0][:10000]


def extract_comments_from_jsonld(soup: BeautifulSoup) -> list[str]:
    out: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        txt = script.get_text(strip=True)
        if not txt:
            continue
        try:
            obj = json.loads(txt)
        except Exception:
            continue

        stack: list[Any] = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                body = cur.get("text") or cur.get("comment")
                if isinstance(body, str):
                    v = clean_text(body)
                    if 6 <= len(v) <= 500:
                        out.append(v)
                for v in cur.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)

    return out


def extract_comments(soup: BeautifulSoup) -> list[str]:
    comments: list[str] = []

    for sel in COMMENT_SELECTORS:
        for node in soup.select(sel):
            txt = clean_text(node.get_text(" ", strip=True))
            if 6 <= len(txt) <= 500:
                comments.append(txt)

    comments.extend(extract_comments_from_jsonld(soup))

    blocked = (
        "login",
        "register",
        "write",
        "copyright",
        "all rights",
        "reply",
        "comment",
    )

    uniq: list[str] = []
    seen: set[str] = set()
    for c in comments:
        low = c.lower()
        if any(b in low for b in blocked) and len(c) < 24:
            continue
        if c not in seen:
            seen.add(c)
            uniq.append(c)

    return uniq[:300]


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z]{2,}|[\uac00-\ud7a3]{2,}", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) >= 2]


def top_keywords(text: str, n: int = 10) -> list[str]:
    tokens = tokenize(text)
    if not tokens:
        return []
    cnt = Counter(tokens)
    return [k for k, _ in cnt.most_common(n)]


def sentiment_label(text: str) -> str:
    t = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def summarize(text: str, max_sentences: int = 3) -> str:
    sents = split_sentences(text)
    if not sents:
        return ""
    return " ".join(sents[:max_sentences])


def analyze_news_url(url: str) -> AnalysisResult:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    title = extract_title(soup)
    article_text = extract_article_text(soup)
    comments_raw = extract_comments(soup)

    article_summary = summarize(article_text, max_sentences=3)
    article_keywords = top_keywords(article_text, n=12)
    comment_keywords = top_keywords(" ".join(comments_raw), n=12)

    comments: list[dict[str, str]] = []
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}

    for idx, c in enumerate(comments_raw, start=1):
        label = sentiment_label(c)
        sentiment_counts[label] += 1
        comments.append(
            {
                "id": str(idx),
                "comment": c,
                "sentiment": label,
            }
        )

    domain = urlparse(url).netloc
    return AnalysisResult(
        url=url,
        domain=domain,
        title=title,
        article_text=article_text,
        article_summary=article_summary,
        article_keywords=article_keywords,
        total_comments=len(comments),
        comment_keywords=comment_keywords,
        sentiment_counts=sentiment_counts,
        comments=comments,
    )


def save_comments_csv(comments: list[dict[str, str]], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "comment", "sentiment"])
        for row in comments:
            writer.writerow([row["id"], row["comment"], row["sentiment"]])
