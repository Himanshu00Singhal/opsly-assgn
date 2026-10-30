from pathlib import Path

from opsly.env_loader import parse_keys_txt


def test_parse_keys_ignores_python_block(tmp_path: Path) -> None:
    keys = tmp_path / "keys.txt"
    keys.write_text(
        "GROQ_API_KEY=abc123\nfrom groq import Groq\nNEO4J_URI=bolt://localhost\n",
        encoding="utf-8",
    )
    parsed = parse_keys_txt(keys)
    assert parsed["GROQ_API_KEY"] == "abc123"
    assert parsed["NEO4J_URI"] == "bolt://localhost"
    assert "from groq" not in parsed
