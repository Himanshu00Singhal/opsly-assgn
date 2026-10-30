from opsly.graph.parser import parse_python_ast


def test_parse_simple_module() -> None:
    source = '''"""module doc"""
import os
class Foo:
    def bar(self, x: int) -> None:
        """bar doc"""
        pass
'''
    result = parse_python_ast(source, "sample.py")
    labels = {e.label for e in result.entities}
    assert "Class" in labels
    assert "Method" in labels
    assert "Import" in labels
    rels = {r.rel_type for r in result.relations}
    assert "CONTAINS" in rels
    assert "IMPORTS" in rels
