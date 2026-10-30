from pathlib import Path
from unittest.mock import MagicMock, patch

from opsly.services.analyst import CodeAnalystService


def test_get_code_snippet_from_repo(tmp_path: Path) -> None:
    repo = tmp_path / "fastapi"
    repo.mkdir()
    py = repo / "app.py"
    py.write_text("class FastAPI:\n    '''app'''\n    pass\n", encoding="utf-8")
    svc = CodeAnalystService()
    with patch.object(svc, "_graph") as graph:
        graph.find_entity.return_value = [{"path": "app.py", "name": "FastAPI"}]
        with patch("opsly.services.analyst.get_app_settings") as settings:
            settings.return_value = MagicMock(fastapi_repo_path=str(repo))
            svc._settings = settings.return_value
            out = svc.get_code_snippet("FastAPI")
    assert "class FastAPI" in out["snippet"]
