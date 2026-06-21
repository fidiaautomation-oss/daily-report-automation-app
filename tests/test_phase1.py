import pytest
import tempfile
import glob
import os
import pandas as pd
from unittest.mock import MagicMock, patch
from phase1.drive_uploader import DriveUploader
from phase1.asp_downloader import AspDownloader


def test_get_or_create_folder_returns_existing_id():
    """既存フォルダIDを返すこと"""
    uploader = DriveUploader.__new__(DriveUploader)
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {
        "files": [{"id": "existing_folder_id"}]
    }
    uploader.service = mock_service

    result = uploader._get_or_create_folder("raw", "parent_id")
    assert result == "existing_folder_id"


def test_get_or_create_folder_creates_new_when_missing():
    """フォルダが存在しない場合は作成すること"""
    uploader = DriveUploader.__new__(DriveUploader)
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {"files": []}
    mock_service.files().create().execute.return_value = {"id": "new_folder_id"}
    uploader.service = mock_service

    result = uploader._get_or_create_folder("2026-05-29", "parent_id")
    assert result == "new_folder_id"


def test_asp_downloader_returns_csv_path(tmp_path):
    """ダウンロード済みCSVのパスが返ること（Playwright部分はモック）"""
    downloader = AspDownloader.__new__(AspDownloader)
    downloader.download_dir = str(tmp_path)

    # ダミーCSVを作成（Playwrightが落としたとみなす）
    csv_path = tmp_path / "report_20260529.csv"
    csv_path.write_text("item_id,date,clicks\nA001,2026-05-29,100\n")

    result = downloader._find_downloaded_csv("report_*.csv")
    assert result == str(csv_path)

