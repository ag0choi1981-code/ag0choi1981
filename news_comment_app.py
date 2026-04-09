from __future__ import annotations

import csv
import io
from datetime import datetime

import streamlit as st

from news_comment_analyzer import analyze_news_url


def csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "comment", "sentiment"])
    for r in rows:
        w.writerow([r["id"], r["comment"], r["sentiment"]])
    return buf.getvalue().encode("utf-8-sig")


def main() -> None:
    st.set_page_config(page_title="News Comment Analyzer", layout="wide")
    st.title("News + Comment Analyzer")
    st.caption("Enter a news URL to analyze article text and comments.")

    col1, col2 = st.columns([4, 1])
    with col1:
        url = st.text_input("News URL", placeholder="https://...")
    with col2:
        run = st.button("Analyze", use_container_width=True, type="primary")

    if not run:
        st.info("Paste a URL and click Analyze.")
        return

    if not url.strip().startswith(("http://", "https://")):
        st.error("Please enter a valid URL starting with http:// or https://")
        return

    with st.spinner("Collecting and analyzing article/comments..."):
        try:
            result = analyze_news_url(url.strip())
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            st.warning(
                "Some sites load comments with JavaScript/login flow, so raw HTML scraping may miss them."
            )
            return

    st.subheader("Article")
    st.write(f"- Domain: `{result.domain}`")
    st.write(f"- Title: {result.title}")
    st.write(f"- Article length: {len(result.article_text)} chars")
    st.write(f"- Summary: {result.article_summary if result.article_summary else 'N/A'}")
    st.write(
        "- Article keywords: "
        + (", ".join(result.article_keywords) if result.article_keywords else "N/A")
    )

    st.subheader("Comments")
    st.write(f"- Extracted comments: {result.total_comments}")
    st.write(
        "- Comment keywords: "
        + (", ".join(result.comment_keywords) if result.comment_keywords else "N/A")
    )
    st.write(
        "- Sentiment counts: "
        f"positive={result.sentiment_counts['positive']}, "
        f"negative={result.sentiment_counts['negative']}, "
        f"neutral={result.sentiment_counts['neutral']}"
    )

    if result.comments:
        st.dataframe(result.comments, use_container_width=True, hide_index=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            "Download comments CSV",
            data=csv_bytes(result.comments),
            file_name=f"comments_{ts}.csv",
            mime="text/csv",
        )
    else:
        st.warning("No comments found.")

    st.caption(
        "Note: This generic analyzer may not capture comments from dynamically rendered or protected platforms."
    )


if __name__ == "__main__":
    main()
