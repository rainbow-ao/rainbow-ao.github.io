import json
import os
import requests
from datetime import datetime, timezone, timedelta


CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

ANALYTICS_BASE = "https://youtubeanalytics.googleapis.com/v2"


def get_access_token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    })
    r.raise_for_status()
    return r.json()["access_token"]


def get_channel_analytics(access_token, start_date, end_date):
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(f"{ANALYTICS_BASE}/reports", headers=headers, params={
        "ids": "channel==MINE",
        "startDate": start_date,
        "endDate": end_date,
        "metrics": "views,estimatedMinutesWatched,averageViewDuration,impressions,impressionClickThroughRate",
        "dimensions": "video",
        "sort": "-views",
        "maxResults": 50,
    })
    if not r.ok:
        print(f"Analytics API error: {r.status_code} {r.text}")
    r.raise_for_status()
    return r.json()


def get_overall_analytics(access_token, start_date, end_date):
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(f"{ANALYTICS_BASE}/reports", headers=headers, params={
        "ids": "channel==MINE",
        "startDate": start_date,
        "endDate": end_date,
        "metrics": "views,estimatedMinutesWatched,subscribersGained",
    })
    if not r.ok:
        print(f"Overall analytics error: {r.status_code} {r.text}")
    r.raise_for_status()
    return r.json()


def load_video_metadata():
    try:
        with open("youtube_stats.json", encoding="utf-8") as f:
            data = json.load(f)
        return {v["id"]: v for v in data.get("videos", [])}
    except FileNotFoundError:
        return {}


def format_ctr(value):
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def analyze_title_pattern(title):
    if "していたら" in title or "した時のBGM" in title or "気がした" in title:
        return "情景タイトル"
    elif "【" in title and "】" in title:
        return "キーワードタイトル"
    else:
        return "その他"


def main():
    print("アクセストークン取得中...")
    access_token = get_access_token()

    today = datetime.now(timezone.utc).date()
    d28_ago = (today - timedelta(days=28)).isoformat()
    d7_ago = (today - timedelta(days=7)).isoformat()
    today_str = today.isoformat()

    print("チャンネル全体の分析中...")
    overall_28 = get_overall_analytics(access_token, d28_ago, today_str)
    overall_7 = get_overall_analytics(access_token, d7_ago, today_str)

    print("動画別の分析中...")
    video_analytics_28 = get_channel_analytics(access_token, d28_ago, today_str)

    video_meta = load_video_metadata()

    rows_28 = video_analytics_28.get("rows", []) or []
    col_headers = [c["name"] for c in video_analytics_28.get("columnHeaders", [])]

    def get_val(row, name):
        idx = col_headers.index(name) if name in col_headers else -1
        return row[idx] if idx >= 0 else None

    video_rows = []
    for row in rows_28:
        vid = get_val(row, "video")
        meta = video_meta.get(vid, {})
        ctr = get_val(row, "impressionClickThroughRate")
        impressions = get_val(row, "impressions")
        views = get_val(row, "views")
        avg_dur = get_val(row, "averageViewDuration")
        title = meta.get("title", vid)
        video_rows.append({
            "id": vid,
            "title": title,
            "views": views,
            "impressions": impressions,
            "ctr": ctr,
            "avg_duration": avg_dur,
            "pattern": analyze_title_pattern(title),
        })

    video_rows.sort(key=lambda x: x["views"] or 0, reverse=True)

    top5 = video_rows[:5]
    bottom5 = [v for v in video_rows if (v["impressions"] or 0) > 10][-5:]

    pattern_stats = {}
    for v in video_rows:
        p = v["pattern"]
        if p not in pattern_stats:
            pattern_stats[p] = {"count": 0, "ctr_sum": 0, "ctr_n": 0}
        pattern_stats[p]["count"] += 1
        if v["ctr"] is not None:
            pattern_stats[p]["ctr_sum"] += v["ctr"]
            pattern_stats[p]["ctr_n"] += 1

    def overall_row(data):
        rows = data.get("rows", [])
        if not rows:
            return [0] * 5
        return rows[0]

    o28 = overall_row(overall_28)
    o7 = overall_row(overall_7)
    o28_headers = [c["name"] for c in overall_28.get("columnHeaders", [])]

    def ov(row, headers, name):
        idx = headers.index(name) if name in headers else -1
        return row[idx] if idx >= 0 and idx < len(row) else 0

    o28_views = ov(o28, o28_headers, "views")
    o28_subs = ov(o28, o28_headers, "subscribersGained")
    o28_watch = ov(o28, o28_headers, "estimatedMinutesWatched")

    o7_headers = [c["name"] for c in overall_7.get("columnHeaders", [])]
    o7_views = ov(o7, o7_headers, "views")

    # 動画別CTRの平均をチャンネルCTRとして使用
    ctr_values = [v["ctr"] for v in video_rows if v["ctr"] is not None]
    channel_avg_ctr = sum(ctr_values) / len(ctr_values) if ctr_values else None

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append(f"# rainbow_tone チャンネル分析レポート")
    lines.append(f"更新日時: {now_str}\n")

    lines.append("## チャンネル全体")
    lines.append(f"| 期間 | 再生数 | 総視聴時間(分) | 登録者増加 |")
    lines.append(f"|------|--------|--------------|----------|")
    lines.append(f"| 直近28日 | {int(o28_views):,} | {int(o28_watch):,} | +{int(o28_subs)} |")
    lines.append(f"| 直近7日 | {int(o7_views):,} | — | — |\n")
    lines.append(f"**動画別平均CTR（直近28日）: {format_ctr(channel_avg_ctr)}**\n")

    lines.append("## 動画別パフォーマンス（直近28日・再生数順）")
    lines.append("| タイトル | 再生数 | インプレッション | CTR | 平均視聴時間 | タイトル形式 |")
    lines.append("|---------|--------|----------------|-----|------------|------------|")
    for v in video_rows[:15]:
        title_short = v["title"][:30] + "…" if len(v["title"]) > 30 else v["title"]
        avg_s = int(v["avg_duration"]) if v["avg_duration"] else 0
        avg_fmt = f"{avg_s//60}:{avg_s%60:02d}" if avg_s else "N/A"
        lines.append(
            f"| {title_short} | {int(v['views'] or 0):,} | {int(v['impressions'] or 0):,} | {format_ctr(v['ctr'])} | {avg_fmt} | {v['pattern']} |"
        )
    lines.append("")

    lines.append("## タイトル形式別CTR比較")
    lines.append("| タイトル形式 | 動画数 | 平均CTR |")
    lines.append("|------------|--------|--------|")
    for p, s in pattern_stats.items():
        avg_ctr = s["ctr_sum"] / s["ctr_n"] if s["ctr_n"] > 0 else None
        lines.append(f"| {p} | {s['count']} | {format_ctr(avg_ctr)} |")
    lines.append("")

    lines.append("## CTR改善アクション（次の動画への推奨）")

    best_ctr_video = max((v for v in video_rows if v["ctr"] is not None), key=lambda x: x["ctr"], default=None)
    worst_ctr_video = min(
        (v for v in video_rows if v["ctr"] is not None and (v["impressions"] or 0) > 20),
        key=lambda x: x["ctr"], default=None
    )

    if best_ctr_video:
        lines.append(f"### 勝ちパターン（最高CTR: {format_ctr(best_ctr_video['ctr'])}）")
        lines.append(f"- 動画: {best_ctr_video['title']}")
        lines.append(f"- タイトル形式: {best_ctr_video['pattern']}")
        lines.append(f"- このパターンを次の動画のタイトルに適用する\n")

    if worst_ctr_video:
        lines.append(f"### 要改善（最低CTR: {format_ctr(worst_ctr_video['ctr'])}）")
        lines.append(f"- 動画: {worst_ctr_video['title']}")
        lines.append(f"- サムネイルまたはタイトルの見直しを検討\n")

    channel_ctr = o28_ctr if o28_ctr else 0
    lines.append("### 次回動画チェックリスト")
    lines.append(f"- 動画別平均CTR: {format_ctr(channel_avg_ctr)}")
    if channel_avg_ctr is None or channel_avg_ctr < 3.0:
        lines.append("- [ ] サムネイルにキャラクター（ヴェイル）を配置する")
        lines.append("- [ ] タイトルは情景タイトル形式（「〇〇していたら〇〇した時のBGM」）")
    lines.append("- [ ] タイトルに 作業用 / 勉強用 / 睡眠用 / 配信用 を含める")
    lines.append("- [ ] 説明欄にBOOTHリンクを入れる")
    lines.append("- [ ] ShortとLongをセットで投稿し相互リンクする")

    report = "\n".join(lines)

    with open("video_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    print("完了: video_report.md を生成しました")
    print(f"動画別平均CTR（28日）: {format_ctr(channel_avg_ctr)}")


if __name__ == "__main__":
    main()
