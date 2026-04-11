"""データ整理スクリプト。

スコアリング後に {actor}_analysis.json の選別結果に基づいてデータ整理を行う。

処理フロー:
1. {actor}_analysis.json の選別結果が ok の写真を confirmed/ へ移動する。
2. {actor}_analysis.json の選別結果が ng の写真を削除する。
3. ok / ng エントリを {actor}_analysis.json から analysis.json に移動する。

Usage:
    python -m src.finalize.main
"""

import json
import os
import shutil
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# 環境変数
# ---------------------------------------------------------------------------


def _load_env() -> None:
    """プロジェクトルートの .env を読み込む。既存の環境変数は上書きしない。"""
    load_dotenv(override=False)


# ---------------------------------------------------------------------------
# データ整理リポジトリ
# ---------------------------------------------------------------------------


class FinalizeRepository:
    """{actor}_analysis.json と analysis.json の読み書きを担う。"""

    def __init__(self, project_root: Path, one_drive_root: Path) -> None:
        """初期化。

        Args:
            project_root: プロジェクトルートディレクトリ。
            one_drive_root: OneDrive ルートディレクトリ。
        """
        self._analysis_json_path = one_drive_root / "data" / "analysis.json"
        self._data_dir = one_drive_root / "data"

    def getActors(self) -> list:
        """OneDrive data ディレクトリ内の被写体 ID 一覧を返す。

        {actor}_analysis.json ファイル名から被写体 ID を取得する。

        Returns:
            被写体 ID のリスト（ソート済み）。ディレクトリが存在しない場合は空リスト。
        """
        if not self._data_dir.exists():
            return []
        actors = []
        for p in sorted(self._data_dir.glob("*_analysis.json")):
            actor = p.stem.replace("_analysis", "")
            actors.append(actor)
        return actors

    def loadActorEntries(self, actor: str) -> list:
        """{actor}_analysis.json から選別エントリを raw dict として読み込む。

        Args:
            actor: 被写体 ID。

        Returns:
            エントリの dict リスト。ファイルが存在しない場合は空リスト。
        """
        path = self._data_dir / f"{actor}_analysis.json"
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def saveActorEntries(self, actor: str, entries: list) -> None:
        """{actor}_analysis.json に選別エントリを保存する。

        Args:
            actor: 被写体 ID。
            entries: エントリの dict リスト。
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        path = self._data_dir / f"{actor}_analysis.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    def loadAnalysisJson(self) -> dict:
        """analysis.json を読み込む。

        Returns:
            actor → エントリリスト の辞書。ファイルが存在しない場合は空辞書。
        """
        if not self._analysis_json_path.exists():
            return {}
        with open(self._analysis_json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def saveAnalysisJson(self, data: dict) -> None:
        """analysis.json を保存する。

        Args:
            data: actor → エントリリスト の辞書。
        """
        self._analysis_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._analysis_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 写真整理器
# ---------------------------------------------------------------------------


class PhotoFinalizer:
    """写真の confirmed 移動・削除を担う。"""

    def __init__(self, one_drive_root: Path) -> None:
        """初期化。

        Args:
            one_drive_root: OneDrive ルートディレクトリ。
        """
        self._images_root = one_drive_root / "images"
        self._confirmed_root = one_drive_root / "confirmed"

    def moveToConfirmed(self, actor: str, filename: str) -> None:
        """写真を images/{actor}/ から confirmed/{actor}/ へ移動する。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
        """
        src = self._images_root / actor / filename
        dst_dir = self._confirmed_root / actor
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst_dir / filename))

    def deleteFromImages(self, actor: str, filename: str) -> None:
        """images/{actor}/ から写真を削除する。ファイルが無い場合は何もしない。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
        """
        path = self._images_root / actor / filename
        if path.exists():
            path.unlink()


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------


def run(
    repository: Optional[FinalizeRepository] = None,
    finalizer: Optional[PhotoFinalizer] = None,
    project_root: Optional[Path] = None,
    one_drive_root: Optional[Path] = None,
) -> None:
    """データ整理のメイン処理。

    全被写体に対してデータ整理を実行し、analysis.json を更新する。

    Args:
        repository: FinalizeRepository インスタンス（DI 用）。
        finalizer: PhotoFinalizer インスタンス（DI 用）。
        project_root: プロジェクトルートパス（DI 用）。
        one_drive_root: OneDrive ルートパス（DI 用）。
    """
    _load_env()

    if project_root is None:
        project_root = Path(os.environ["PROJECT_ROOT"])
    if one_drive_root is None:
        one_drive_root = Path(os.environ["ONE_DRIVE_ROOT"])
    if repository is None:
        repository = FinalizeRepository(project_root, one_drive_root)
    if finalizer is None:
        finalizer = PhotoFinalizer(one_drive_root)

    actors = repository.getActors()
    analysis_data = repository.loadAnalysisJson()

    for actor in actors:
        print(f"[INFO] Finalizing actor: {actor}")
        _run_finalize_for_actor(actor, repository, finalizer, analysis_data)

    repository.saveAnalysisJson(analysis_data)
    print("[INFO] Finalize complete.")


def _run_finalize_for_actor(
    actor: str,
    repository: FinalizeRepository,
    finalizer: PhotoFinalizer,
    analysis_data: dict,
) -> None:
    """被写体ごとのデータ整理処理。

    1. ok エントリ → images/ から confirmed/ へ移動
    2. ng エントリ → images/ から削除
    3. ok / ng エントリを {actor}_analysis.json から analysis.json に移動
    4. pending エントリのみ {actor}_analysis.json に残す

    Args:
        actor: 被写体 ID。
        repository: FinalizeRepository インスタンス。
        finalizer: PhotoFinalizer インスタンス。
        analysis_data: analysis.json の内容（インプレースで更新する）。
    """
    entries = repository.loadActorEntries(actor)

    remaining = []
    finalized_entries = []

    for entry in entries:
        state = entry.get("selectionState")
        if state == "ok":
            # ok: confirmed/ へ移動
            finalizer.moveToConfirmed(actor, entry["filename"])
            print(f"[INFO] Moved to confirmed: {actor}/{entry['filename']}")
            finalized_entries.append(entry)
        elif state == "ng":
            # ng: images/ から削除
            finalizer.deleteFromImages(actor, entry["filename"])
            print(f"[INFO] Deleted: {actor}/{entry['filename']}")
            finalized_entries.append(entry)
        else:
            # pending: 残す
            remaining.append(entry)

    # pending のみ {actor}_analysis.json に保存する
    repository.saveActorEntries(actor, remaining)

    # ok / ng エントリを analysis.json に移動（重複排除）
    if finalized_entries:
        if actor not in analysis_data:
            analysis_data[actor] = []
        existing_filenames = {e["filename"] for e in analysis_data[actor]}
        for entry in finalized_entries:
            if entry["filename"] not in existing_filenames:
                analysis_data[actor].append(entry)


if __name__ == "__main__":  # pragma: no cover
    run()
