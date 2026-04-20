"""sorterテスト用フィクスチャ。torch・clip をDockerテスト環境でモック化する。"""

import sys
from unittest.mock import MagicMock

# torch・clip はDockerテスト環境では未インストールのため、sys.modulesに登録してモック化する
if "torch" not in sys.modules:
    _mock_torch = MagicMock()
    _mock_torch.backends.mps.is_available.return_value = False
    sys.modules["torch"] = _mock_torch
    sys.modules["torch.backends"] = _mock_torch.backends
    sys.modules["torch.backends.mps"] = _mock_torch.backends.mps

if "clip" not in sys.modules:
    sys.modules["clip"] = MagicMock()
