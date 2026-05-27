"""
一回だけ実行してリフレッシュトークンを取得するスクリプト。
取得したトークンはGitHub Secretsに保存してください。

使い方:
  pip install requests
  python get_refresh_token.py
"""

import json
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests

CLIENT_ID = input("クライアントID を貼り付けてください: ").strip()
CLIENT_SECRET = input("クライアントシークレット を貼り付けてください: ").strip()

REDIRECT_URI = "http://localhost:8080"
SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"

auth_code = None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = parse_qs(urlparse(self.path).query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h2>認証完了！このウィンドウを閉じてください。</h2>".encode())

    def log_message(self, format, *args):
        pass


auth_url = (
    "https://accounts.google.com/o/oauth2/auth"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URI}"
    "&response_type=code"
    f"&scope={SCOPE}"
    "&access_type=offline"
    "&prompt=consent"
)

print("\nブラウザが開きます。Googleアカウントで認証してください...")
webbrowser.open(auth_url)

server = HTTPServer(("localhost", 8080), Handler)
server.handle_request()

if not auth_code:
    print("認証コードの取得に失敗しました。")
    exit(1)

r = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    },
)

tokens = r.json()
refresh_token = tokens.get("refresh_token")

if refresh_token:
    print("\n" + "=" * 60)
    print("リフレッシュトークン（GitHub Secretsに保存してください）:")
    print(refresh_token)
    print("=" * 60)
    print("\nGitHub Secrets に以下の3つを登録してください:")
    print(f"  GOOGLE_CLIENT_ID     = {CLIENT_ID}")
    print(f"  GOOGLE_CLIENT_SECRET = {CLIENT_SECRET}")
    print(f"  GOOGLE_REFRESH_TOKEN = {refresh_token}")
else:
    print("エラー:", tokens)
