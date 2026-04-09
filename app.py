from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

from youtube_minister_subscribers import build_rows, filter_rows, load_ministers


def to_csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Ministry", "Minister", "Channel", "Subscribers"])
    for row in rows:
        writer.writerow(
            [
                row["Ministry"],
                row["Minister"],
                row["Channel"],
                row["Subscribers"],
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")


def main() -> None:
    st.set_page_config(
        page_title="KR Ministry/Minister YouTube Subscribers",
        page_icon="YT",
        layout="wide",
    )

    st.title("KR Ministry/Minister YouTube Subscriber Dashboard")
    st.caption("Latest minister list + YouTube API (fallback to HTML parsing)")

    with st.sidebar:
        st.header("Settings")

        mode_label = st.radio(
            "Target",
            ["Ministry + Minister", "Ministry only", "Minister only"],
            index=0,
        )
        mode = {
            "Ministry + Minister": "both",
            "Ministry only": "ministry",
            "Minister only": "minister",
        }[mode_label]

        query = st.text_input("Search", placeholder="e.g. science, budget, Bae")

        api_key = st.text_input(
            "YouTube API Key (optional)",
            value=os.getenv("YOUTUBE_API_KEY", ""),
            type="password",
            help="If provided, YouTube Data API is used first.",
        ).strip()

        ministers_json = st.text_input(
            "Local ministers JSON",
            value="ministries_2026.json",
            help="Used when automatic scraping fails.",
        )

        run = st.button("Run", type="primary")

    if not run:
        st.info("Choose options and click Run.")
        return

    json_path = Path(ministers_json)
    with st.spinner("Fetching ministries, channels, and subscriber counts..."):
        ministers = load_ministers(json_path)
        rows = build_rows(ministers=ministers, api_key=api_key or None, mode=mode)
        rows = filter_rows(rows, query if query else None)

    table_rows = [
        {
            "Ministry": row.ministry,
            "Minister": row.minister,
            "Channel": row.channel_name,
            "Subscribers": row.subscribers,
        }
        for row in rows
    ]

    st.success(f"Completed: {len(table_rows)} rows")
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    csv_bytes = to_csv_bytes(table_rows)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"kr_ministry_youtube_subscribers_{ts}.csv"

    st.download_button(
        label="Download CSV",
        data=csv_bytes,
        file_name=file_name,
        mime="text/csv",
    )

    if not api_key:
        st.warning(
            "No API key provided. HTML parsing fallback is used and may be less stable."
        )


if __name__ == "__main__":
    main()
