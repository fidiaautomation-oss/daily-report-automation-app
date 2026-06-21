import os
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()


class DriveUploader:
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    def __init__(self):
        creds = self._load_credentials()
        # トークンが期限切れの場合は自動更新
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        self.service = build("drive", "v3", credentials=creds)
        self.root_folder_id = os.environ["DRIVE_ROOT_FOLDER_ID"]

    def _load_credentials(self) -> Credentials:
        """環境変数またはtoken.jsonからOAuth2認証情報を読み込む"""
        # 環境変数 GOOGLE_OAUTH_TOKEN_JSON があればそちらを優先（GitHub Actions用）
        token_json = os.environ.get("GOOGLE_OAUTH_TOKEN_JSON")
        if token_json:
            info = json.loads(token_json)
        else:
            # ローカル用: credentials/token.json を読み込む
            token_path = os.environ.get(
                "GOOGLE_TOKEN_PATH", "credentials/token.json"
            )
            with open(token_path) as f:
                info = json.load(f)
        return Credentials(
            token=info.get("token"),
            refresh_token=info.get("refresh_token"),
            token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=info.get("client_id"),
            client_secret=info.get("client_secret"),
            scopes=info.get("scopes", self.SCOPES),
        )

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        query = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
            f" and '{parent_id}' in parents and trashed=false"
        )
        res = self.service.files().list(
            q=query,
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self.service.files().create(
            body=meta, fields="id", supportsAllDrives=True
        ).execute()
        return folder["id"]

    def _find_file(self, name: str, parent_id: str) -> str | None:
        escaped = name.replace("'", "\\'")
        res = self.service.files().list(
            q=(
                f"name='{escaped}' and '{parent_id}' in parents and trashed=false"
            ),
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def upload_csv(
        self, local_path: str, filename: str, date_str: str, top_folder: str = "raw"
    ) -> str:
        """CSVファイルをDrive <top_folder>/YYYY-MM-DD/ へアップロードする。

        同名ファイルが既に存在する場合は上書き（update）する。ファイルIDを返す。
        """
        top_folder_id = self._get_or_create_folder(top_folder, self.root_folder_id)
        date_folder_id = self._get_or_create_folder(date_str, top_folder_id)

        media = MediaFileUpload(local_path, mimetype="text/csv")
        existing_id = self._find_file(filename, date_folder_id)
        if existing_id:
            updated = self.service.files().update(
                fileId=existing_id,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            ).execute()
            return updated["id"]
        file_meta = {"name": filename, "parents": [date_folder_id]}
        uploaded = self.service.files().create(
            body=file_meta,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return uploaded["id"]

    def download_folder_csvs(self, date_str: str, top_folder: str = "raw") -> dict:
        """Drive <top_folder>/YYYY-MM-DD/ の全CSVを取得する。{ファイル名: bytes} を返す。"""
        top_folder_id = self._get_or_create_folder(top_folder, self.root_folder_id)
        date_folder_id = self._get_or_create_folder(date_str, top_folder_id)
        res = self.service.files().list(
            q=f"'{date_folder_id}' in parents and trashed=false",
            fields="files(id,name)",
            pageSize=200,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        out = {}
        for f in res.get("files", []):
            if not f["name"].endswith(".csv"):
                continue
            data = self.service.files().get_media(
                fileId=f["id"], supportsAllDrives=True
            ).execute()
            out[f["name"]] = data
        return out
