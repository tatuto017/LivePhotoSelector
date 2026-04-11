#!/bin/bash
# 解析スクリプトの自動再起動ループ。
# OOM 等でプロセスが強制終了された場合、inbox が空になるまで自動で再起動する。

# スクリプトのあるディレクトリ（プロジェクトルート）に移動する
cd "$(dirname "$0")" || exit 1

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

INBOX_ROOT="${ONE_DRIVE_ROOT}/inbox"

while true; do
    # inbox に処理対象ファイルが残っているか確認
    remaining=$(find "$INBOX_ROOT" -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \) 2>/dev/null | wc -l)
    if [ "$remaining" -eq 0 ]; then
        echo "[INFO] inbox が空です。解析完了。"
        break
    fi

    echo "[INFO] 残り ${remaining} 件。解析を開始します..."
    TF_CPP_MIN_LOG_LEVEL=3 python3 -m src.analysis.main

    exit_code=$?
    if [ "$exit_code" -eq 0 ]; then
        echo "[INFO] 解析が正常終了しました。"
        break
    else
        echo "[WARN] プロセスが終了コード ${exit_code} で終了しました。再起動します..."
        sleep 2
    fi
done
