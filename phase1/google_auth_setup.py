"""Google OAuth トークン再生成スクリプト。

`credentials/token.json` が失効（invalid_grant: Token has been expired or revoked）した
場合に実行する。ブラウザでGoogleにログイン・許可すると token.json を再生成する。

使い方:
    python -m phase1.google_auth_setup
"""

import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]
CLIENT_SECRETS = os.environ.get(
    "GOOGLE_CLIENT_SECRETS_PATH", "credentials/client_secrets.json"
)
TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "credentials/token.json")


def main():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    # access_type=offline かつ prompt=consent でリフレッシュトークンを確実に取得
    creds = flow.run_local_server(
        port=0, access_type="offline", prompt="consent"
    )
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print(f"[OK] {TOKEN_PATH} を再生成しました")
    print(f"     refresh_token: {'あり' if creds.refresh_token else 'なし'}")


if __name__ == "__main__":
    main()
