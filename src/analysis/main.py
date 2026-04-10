"""DeepFace による写真解析スクリプト。

INBOX_ROOT/{actor}/ の写真を DeepFace で解析し、
analysis.pki に解析結果を保存して inbox → images へ移動する。
{actor}_analysis.json を更新する。

Usage:
    python -m src.analysis.main
    python -m src.analysis.main --scoring
    python -m src.analysis.main --finalize
"""
