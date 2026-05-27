import os
import json
import requests
from datetime import datetime, timezone

API_KEY = os.environ["YOUTUBE_API_KEY"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
BASE = "https://www.googleapis.com/youtube/v3"


def get_channel_stats():
    r = requests.get(f"{BASE}/channels", params={
        "part": "snippet,statistics",
        "id": CHANNEL_ID,
        "key": API_KEY,
    })
    r.raise_for_status()
    item = r.json()["items"][0]
    return {
        "title": item["snippet"]["title"],
        "description": item["snippet"]["description"],
        "subscribers": int(item["statistics"].get("subscriberCount", 0)),
        "total_views": int(item["statistics"].get("viewCount", 0)),
        "video_count": int(item["statistics"].get("videoCount", 0)),
    }


def get_videos():
    videos = []
    page_token = None

    while True:
        params = {
            "part": "snippet",
            "channelId": CHANNEL_ID,
            "maxResults": 50,
            "order": "date",
            "type": "video",
            "key": API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        r = requests.get(f"{BASE}/search", params=params)
        r.raise_for_status()
        data = r.json()

        video_ids = [item["id"]["videoId"] for item in data.get("items", [])]
        if not video_ids:
            break

        # 再生数・いいね数などの詳細を取得
        stats_r = requests.get(f"{BASE}/videos", params={
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
            "key": API_KEY,
        })
        stats_r.raise_for_status()

        for item in stats_r.json().get("items", []):
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            duration = item.get("contentDetails", {}).get("duration", "")
            videos.append({
                "id": item["id"],
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "title": snippet["title"],
                "published_at": snippet["publishedAt"],
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration": duration,
                "tags": snippet.get("tags", []),
                "description_head": snippet.get("description", "")[:200],
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return videos


def main():
    print("Fetching channel stats...")
    channel = get_channel_stats()

    print("Fetching videos...")
    videos = get_videos()

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
        "videos": videos,
    }

    with open("youtube_stats.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Done. {len(videos)} videos saved.")


if __name__ == "__main__":
    main()
