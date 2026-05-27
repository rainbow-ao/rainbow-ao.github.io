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
        "metrics": "views,estimatedMinutesWatched,averageViewDuration,likes,comments",
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
        views = get_val(row, "views")
        avg_dur = get_val(row, "averageViewDuration")
        likes = get_val(row, "likes")
        comments = get_val(row, "comments")
        watch_min = get_val(row, "estimatedMinutesWatched")
        title = meta.get("title", vid)
        like_rate = (likes / views * 100) if (views and likes) else None
        video_rows.append({
            "id": vid,
            "title": title,
            "views": views,
            "avg_duration": avg_dur,
            "likes": likes,
            "comments": comments,
            "watch_min": watch_min,
            "like_rate": like_rate,
            "pattern": analyze_title_pattern(title),
        })

    video_rows.sort(key=lambda x: x["views"] or 0, reverse=True)

    pattern_stats = {}
    for v in video_rows:
        p = v["pattern"]
        if p not in pattern_stats:
            pattern_stats[p] = {"count": 0, "views_sum": 0, "like_rate_sum": 0, "like_rate_n": 0}
        pattern_stats[p]["count"] += 1
        pattern_stats[p]["views_sum"] += v["views"] or 0
        if v["like_rate"] is not None:
            pattern_stats[p]["like_rate_sum"] += v["like_rate"]
            pattern_stats[p]["like_rate_n"] += 1

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

    best_video = max(video_rows, key=lambda x: x["views"] or 0, default=None)
    best_like_video = max((v for v in video_rows if v["like_rate"] is not None), key=lambda x: x["like_rate"], default=None)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append("# rainbow_tone チャンネル分析レポート")
    lines.append(f"更新日時: {now_str}\n")
    lines.append("> ※ CTR・インプレッションはYouTube Analytics APIの非公開データのため、YouTube Studioで直接確認してください。\n")

    lines.append("## チャンネル全体（直近28日）")
    lines.append("| 再生数 | 総視聴時間(分) | 登録者増加 | 直近7日再生数 |")
    lines.append("|--------|--------------|----------|-----------  |")
    lines.append(f"| {int(o28_views):,} | {int(o28_watch):,} | +{int(o28_subs)} | {int(o7_views):,} |\n")

    lines.append("## 動画別パフォーマンス（直近28日・再生数順）")
    lines.append("| タイトル | 再生数 | 平均視聴時間 | いいね率 | タイトル形式 |")
    lines.append("|---------|--------|------------|--------|------------|")
    for v in video_rows[:15]:
        title_short = v["title"][:28] + "…" if len(v["title"]) > 28 else v["title"]
        avg_s = int(v["avg_duration"]) if v["avg_duration"] else 0
        avg_fmt = f"{avg_s//60}:{avg_s%60:02d}" if avg_s else "N/A"
        like_str = f"{v['like_rate']:.2f}%" if v["like_rate"] is not None else "N/A"
        lines.append(f"| {title_short} | {int(v['views'] or 0):,} | {avg_fmt} | {like_str} | {v['pattern']} |")
    lines.append("")

    lines.append("## タイトル形式別パフォーマンス比較")
    lines.append("| タイトル形式 | 動画数 | 合計再生数 | 平均いいね率 |")
    lines.append("|------------|--------|----------|------------|")
    for p, s in sorted(pattern_stats.items(), key=lambda x: x[1]["views_sum"], reverse=True):
        avg_lr = s["like_rate_sum"] / s["like_rate_n"] if s["like_rate_n"] > 0 else None
        lr_str = f"{avg_lr:.2f}%" if avg_lr is not None else "N/A"
        lines.append(f"| {p} | {s['count']} | {s['views_sum']:,} | {lr_str} |")
    lines.append("")

    lines.append("## 次回動画チェックリスト")
    if best_video:
        lines.append(f"**直近28日の最多再生動画**: {best_video['title'][:40]} ({int(best_video['views'] or 0):,}回)\n")
    lines.append("- [ ] サムネイルにキャラクター（ヴェイル）を配置する")
    lines.append("- [ ] タイトルは情景タイトル形式（「〇〇していたら〇〇した時のBGM」）")
    lines.append("- [ ] タイトルに 作業用 / 勉強用 / 睡眠用 / 配信用 を含める")
    lines.append("- [ ] 説明欄にBOOTHリンクを入れる")
    lines.append("- [ ] ShortとLongをセットで投稿し相互リンクする")
    lines.append("\n> CTR確認: YouTube Studio → アナリティクス → リーチ → インプレッションのクリック率")

    report = "\n".join(lines)

    with open("video_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    print("完了: video_report.md を生成しました")
    print(f"直近28日再生数: {int(o28_views):,}")


if __name__ == "__main__":
    main()
