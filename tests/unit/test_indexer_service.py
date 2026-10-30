from unittest.mock import MagicMock, patch

from opsly.services.indexer import IndexerService


def test_parse_ast_inline() -> None:
    svc = IndexerService()
    with patch.object(svc, "_graph", MagicMock()):
        out = svc.parse_ast("def foo(): pass", "f.py")
    assert out["entities"]
