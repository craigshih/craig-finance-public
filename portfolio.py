"""公開版：不含持股、交易與對帳功能。

原版這裡會從私人資料庫讀持股與交易紀錄；公開版一律回報「讀不到」，
build.py 會照常產生其他頁面，投資總覽頁顯示說明文字。想接自己的持股，照下面的介面實作即可。
"""
from pathlib import Path


class NotionUnavailable(Exception):
    pass


def load_notion() -> dict:
    """回傳 {"tickers": [...], "trades": [...]}；公開版不提供。"""
    raise NotionUnavailable("公開版不含持股功能")


def summarize(nd: dict) -> dict:
    raise NotionUnavailable("公開版不含持股功能")


def load_statements(statement_dir: Path) -> list[dict]:
    return []


def reconcile(statements: list[dict], notion_trades: list[dict], tickers: list[dict]) -> dict | None:
    return None


def issue_count(rc: dict | None) -> int:
    return 0
