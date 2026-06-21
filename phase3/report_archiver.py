import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()


class ReportArchiver:
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    def __init__(self):
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            scopes=self.SCOPES,
        )
        self.service = build("drive", "v3", credentials=creds)
        self.root_folder_id = os.environ["DRIVE_ROOT_FOLDER_ID"]

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        query = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
            f" and '{parent_id}' in parents and trashed=false"
        )
        res = self.service.files().list(q=query, fields="files(id)").execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self.service.files().create(body=meta, fields="id").execute()
        return folder["id"]

    def upload_report(self, local_path: str, filename: str, date_str: str) -> str:
        """完成ExcelをDrive report/YYYY-MM-DD/ へアップロードする"""
        report_folder_id = self._get_or_create_folder("report", self.root_folder_id)
        date_folder_id = self._get_or_create_folder(date_str, report_folder_id)

        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        media = MediaFileUpload(local_path, mimetype=mime)
        file_meta = {"name": filename, "parents": [date_folder_id]}
        uploaded = (
            self.service.files().create(body=file_meta, media_body=media, fields="id").execute()
        )
        return uploaded["id"]
