#!/bin/bash
# 解析スクリプトの自動再起動ループ。
# OOM 等でプロセスが強制終了された場合、自動で再起動する。
#
# 解析フロー:
#   1. 解析を実行し、全ファイルが処理されたら手動でのファイル移動を促して終了する。
#   2. ユーザーが ANALYZE_ROOT/{actor}/ のファイルを DATA_ROOT/images/{actor}/ へ手動で移動する。
#   3. analyze.sh を再実行すると ANALYZE_ROOT が空であることを検出し、
#      --publish フェーズを実行して sorting_state.public を true に更新する。
#
# Usage:
#   ./analyze.sh [--workers N]
#
# Options:
#   --workers N   並列処理ワーカー数（デフォルト: 2）
#                 Raspberry Pi 4: 2, M4 MacBook Air: 4〜6

# スクリプトのあるディレクトリ（プロジェクトルート）に移動する
cd "$(dirname "$0")" || exit 1

# デフォルトのワーカー数
WORKERS=4

# 引数を解析する
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        *)
            echo "[ERROR] 不明なオプション: $1" >&2
            echo "Usage: $0 [--workers N]" >&2
            exit 1
            ;;
    esac
done

# .env を読み込む（既存の環境変数は上書きしない）
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source ".env"
    set +a
fi

# pyenv を初期化する（pyenv がインストール済みの場合）
if [ -d "$HOME/.pyenv" ]; then
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)" 2>/dev/null || true
fi

# 仮想環境を有効化する
# shellcheck disable=SC1091
source ".venv/bin/activate"

# ANALYZE_ROOT の検証
if [ -z "$ANALYZE_ROOT" ]; then
    echo "[ERROR] ANALYZE_ROOT が設定されていません。.env を確認してください。" >&2
    exit 1
fi
if [[ "$ANALYZE_ROOT" != /* ]]; then
    echo "[ERROR] ANALYZE_ROOT は絶対パスで指定してください: ${ANALYZE_ROOT}" >&2
    exit 1
fi

# DATA_ROOT の検証
if [ -z "$DATA_ROOT" ]; then
    echo "[ERROR] DATA_ROOT が設定されていません。.env を確認してください。" >&2
    exit 1
fi
if [[ "$DATA_ROOT" != /* ]]; then
    echo "[ERROR] DATA_ROOT は絶対パスで指定してください: ${DATA_ROOT}" >&2
    exit 1
fi

while true; do
    # ANALYZE_ROOT/{actor}/ 配下のファイル数で残件数を確認
    remaining=$(find "$ANALYZE_ROOT" -mindepth 2 -maxdepth 2 -type f 2>/dev/null | wc -l)
    if [ "$remaining" -eq 0 ]; then
        echo "[INFO] ANALYZE_ROOT が空です。--publish フェーズを実行します..."
        TF_CPP_MIN_LOG_LEVEL=3 python3 -m src.finalize.main --publish
        echo "[INFO] 公開処理が完了しました。"
        break
    fi

    echo "[INFO] 残り ${remaining} 件。解析を開始します（workers=${WORKERS}）..."
    TF_CPP_MIN_LOG_LEVEL=3 python3 -m src.analysis.main --workers "$WORKERS"

    exit_code=$?
    if [ "$exit_code" -eq 0 ]; then
        echo "[INFO] 解析が正常終了しました。"
        echo ""
        echo "=========================================================="
        echo "  次のステップ: 解析済みファイルを手動で移動してください"
        echo "  移動元: ${ANALYZE_ROOT}/{actor}/"
        echo "  移動先: ${DATA_ROOT}/images/{actor}/"
        echo ""
        echo "  移動完了後、analyze.sh を再実行して公開処理を行ってください:"
        echo "    bash analyze.sh"
        echo "=========================================================="
        break
    else
        echo "[WARN] プロセスが終了コード ${exit_code} で終了しました。再起動します..."
        sleep 2
    fi
done
