from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
import re
from pathlib import Path

from flask import Flask, jsonify, make_response

from youtube_minister_subscribers import scrape_youtube_subscribers_from_url

app = Flask(__name__)

MOEL_OFFICIAL_URL = "https://www.youtube.com/@moelkorea"
MINISTER_URL = "https://www.youtube.com/@ministerhoon"
APP_BUILD = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

DEFAULT_MINISTRY_LIST_PATH = (
    Path(os.environ.get("USERPROFILE", ""))
    / "Desktop"
    / "정부부처 유튜브 주소 리스트.txt"
)

# Always-include / override channels
MANUAL_MINISTRY_CHANNELS = {
    "국토교통부": "https://www.youtube.com/@korealand",
}


def to_numeric_subscribers(raw: str) -> str:
    text = (raw or "").strip().lower().replace(",", "")
    if not text:
        return "N/A"

    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(억|만|천)", text)
    if m:
        num = float(m.group(1))
        mult = {"천": 1_000, "만": 10_000, "억": 100_000_000}[m.group(2)]
        return f"{int(round(num * mult)):,}"

    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([kmb])", text)
    if m:
        num = float(m.group(1))
        mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[m.group(2)]
        return f"{int(round(num * mult)):,}"

    digits = re.findall(r"\d+", text)
    if digits:
        return f"{int(''.join(digits)):,}"
    return "N/A"


def normalize_youtube_url(raw: str) -> str | None:
    if not raw:
        return None
    u = raw.strip().strip('"\'')
    if "youtube.com" not in u.lower():
        return None
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u.lstrip("/")
    return u


def parse_ministry_url_file(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows: list[dict[str, str]] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in re.split(r"\t+", line) if p.strip()]
        if not parts:
            continue

        youtube_candidate = ""
        for p in parts[::-1]:
            if "youtube.com" in p.lower():
                youtube_candidate = p
                break
        if not youtube_candidate:
            continue

        url = normalize_youtube_url(youtube_candidate)
        if not url:
            continue

        ministry = parts[0]
        rows.append({"ministry": ministry, "url": url})

    # de-duplicate by URL while preserving order
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for r in rows:
        key = r["url"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def merge_with_moel(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged = [{"ministry": "고용노동부", "url": MOEL_OFFICIAL_URL}]

    # 1) add parsed rows first (excluding MOEL duplicate)
    for r in rows:
        if r["url"].lower() == MOEL_OFFICIAL_URL.lower():
            continue
        merged.append(r)

    # 2) apply manual overrides / forced includes
    by_ministry = {r["ministry"]: r for r in merged}
    for ministry, url in MANUAL_MINISTRY_CHANNELS.items():
        by_ministry[ministry] = {"ministry": ministry, "url": url}

    return list(by_ministry.values())


def fetch_one(row: dict[str, str], checked_at: str) -> dict[str, str]:
    raw = scrape_youtube_subscribers_from_url(row["url"]) or "N/A"
    subs = to_numeric_subscribers(raw)
    return {
        "kind": row["ministry"],
        "url": row["url"],
        "subscribers": raw,
        "sort_subscribers": subs,
        "raw": raw,
        "checked_at": checked_at,
    }


def fetch_ministry_rows(checked_at: str) -> list[dict[str, str]]:
    file_rows = parse_ministry_url_file(DEFAULT_MINISTRY_LIST_PATH)
    targets = merge_with_moel(file_rows)

    if not targets:
        targets = [{"ministry": "고용노동부", "url": MOEL_OFFICIAL_URL}]

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda r: fetch_one(r, checked_at), targets))

    def num_key(v: str) -> int:
        if not v or v == "N/A":
            return -1
        return int(v.replace(",", ""))

    # Sort by subscriber count DESC
    results.sort(key=lambda x: num_key(x.get("sort_subscribers", "N/A")), reverse=True)
    for i, r in enumerate(results, start=1):
        r["rank"] = i
    return results


HTML_PAGE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>MOEL + Ministries YouTube Subscriber Checker</title>
  <style>
    :root { --line:#d7dee8; --ink:#101828; --muted:#475467; --accent:#0b69ff; }
    body { margin:0; font-family:"Segoe UI","Malgun Gothic",sans-serif; background:linear-gradient(160deg,#f8fbff,#eef4ff 65%); color:var(--ink); }
    .wrap { max-width: 1160px; margin: 28px auto; padding: 0 16px; }
    .card { background:#fff; border:1px solid var(--line); border-radius:14px; box-shadow:0 8px 24px rgba(16,24,40,.07); padding:20px; }
    h1 { margin:0 0 10px 0; font-size:27px; }
    p { margin:0 0 12px 0; color:var(--muted); }
    .howto { border:1px solid var(--line); border-radius:10px; background:#f8fafc; padding:12px; margin-bottom:12px; font-size:14px; }
    .row { display:flex; gap:12px; align-items:center; margin: 8px 0 10px 0; }
    button { border:0; border-radius:10px; background:var(--accent); color:#fff; font-weight:700; padding:11px 18px; cursor:pointer; }
    button:disabled { opacity:.6; cursor:not-allowed; }
    .msg { margin-top:10px; color:var(--muted); }
    .error { color:#b42318; }
    .kpi { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:14px; }
    .kpi-card { border:1px solid var(--line); border-radius:12px; padding:14px; background:#f8fafc; }
    .kpi-title { color:var(--muted); font-size:14px; margin-bottom:6px; }
    .kpi-value { font-size:28px; font-weight:800; letter-spacing:.3px; }
    table { width:100%; border-collapse:collapse; margin-top:14px; }
    th,td { border-bottom:1px solid var(--line); padding:11px 8px; text-align:left; vertical-align:top; }
    th { background:#f8fafc; }
    td code { font-size:12px; }
    @media (max-width: 760px) { .kpi { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>고용노동부 + 정부부처 공식 유튜브 구독자수 조회</h1>
      <p>조회 버튼을 누르면 고용노동부/노동부장관 + 정부부처 공식 유튜브 구독자수를 함께 가져옵니다.</p>
      <p style="font-size:13px;color:#667085;">Build: <code>__APP_BUILD__</code></p>

      <div class="howto">
        <strong>실행 방법</strong><br/>
        1) <code>run_moel_web_page.bat</code> 더블클릭<br/>
        2) 브라우저에서 <code>http://127.0.0.1:5050</code> 열기
      </div>

      <div class="row">
        <button id="checkBtn">조회</button>
      </div>

      <div id="message" class="msg">Ready</div>

      <div class="kpi" id="kpiWrap" hidden>
        <div class="kpi-card">
          <div class="kpi-title">고용노동부 공식 유튜브 구독자수</div>
          <div class="kpi-value" id="ministrySubs">-</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">노동부장관 유튜브 구독자수</div>
          <div class="kpi-value" id="ministerSubs">-</div>
        </div>
      </div>

      <table id="resultTable" hidden>
        <thead>
          <tr>
            <th>순위</th>
            <th>부처</th>
            <th>유튜브 주소</th>
            <th>구독자수</th>
            <th>조회시각</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <script>
    const btn = document.getElementById("checkBtn");
    const msg = document.getElementById("message");
    const table = document.getElementById("resultTable");
    const tbody = table.querySelector("tbody");
    const kpiWrap = document.getElementById("kpiWrap");
    const ministrySubs = document.getElementById("ministrySubs");
    const ministerSubs = document.getElementById("ministerSubs");

    function setMessage(text, isError=false) {
      msg.textContent = text;
      msg.className = isError ? "msg error" : "msg";
    }

    function renderRows(rows) {
      tbody.innerHTML = "";
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${row.rank ?? ""}</td>
          <td>${row.kind}</td>
          <td><code>${row.url}</code></td>
          <td>${row.subscribers}</td>
          <td>${row.checked_at}</td>
        `;
        tbody.appendChild(tr);
      }
      table.hidden = false;
    }

    function renderKpi(data) {
      ministrySubs.textContent = data.moel_official?.subscribers || "N/A";
      ministerSubs.textContent = data.moel_minister?.subscribers || "N/A";
      kpiWrap.hidden = false;
    }

    async function runCheck() {
      btn.disabled = true;
      setMessage("조회 중...");
      table.hidden = true;
      kpiWrap.hidden = true;

      try {
        const res = await fetch("/api/check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
          cache: "no-store"
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "조회 실패");

        renderKpi(data);
        renderRows(data.rows || []);
        setMessage(data.note ? ("조회 완료 - " + data.note) : "조회 완료");
      } catch (err) {
        setMessage(err.message, true);
      } finally {
        btn.disabled = false;
      }
    }

    btn.addEventListener("click", runCheck);
  </script>
</body>
</html>
"""

HTML_PAGE = HTML_PAGE.replace("__APP_BUILD__", APP_BUILD)


@app.get("/")
def index():
    response = make_response(HTML_PAGE)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.post("/api/check")
def check():
    try:
        checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        moel_official_raw = scrape_youtube_subscribers_from_url(MOEL_OFFICIAL_URL) or "N/A"
        moel_minister_raw = scrape_youtube_subscribers_from_url(MINISTER_URL) or "N/A"
        moel_official_subs = to_numeric_subscribers(moel_official_raw)
        moel_minister_subs = to_numeric_subscribers(moel_minister_raw)

        rows = fetch_ministry_rows(checked_at)

        note = ""
        if any(r.get("subscribers") == "N/A" for r in rows):
            note = "일부 채널은 파싱 실패 가능성이 있어요. 3~5초 후 다시 조회해 보세요."

        return jsonify(
            {
                "moel_official": {
                    "subscribers": moel_official_raw,
                    "raw": moel_official_raw,
                    "url": MOEL_OFFICIAL_URL,
                },
                "moel_minister": {
                    "subscribers": moel_minister_raw,
                    "raw": moel_minister_raw,
                    "url": MINISTER_URL,
                },
                "rows": rows,
                "note": note,
                "source_file": str(DEFAULT_MINISTRY_LIST_PATH),
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
