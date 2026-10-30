"""Python AST parser for repository indexing."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedEntity:
    label: str
    fqn: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    docstring: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedRelation:
    rel_type: str
    from_fqn: str
    to_fqn: str


@dataclass
class ParseResult:
    entities: list[ParsedEntity]
    relations: list[ParsedRelation]


def _doc(node: ast.AST) -> str | None:
    raw = ast.get_docstring(node)
    return raw.strip() if raw else None


def parse_python_ast(source: str, file_path: str) -> ParseResult:
    """Extract entities and relationships from Python source."""
    tree = ast.parse(source)
    module_fqn = file_path.replace("/", ".").removesuffix(".py")
    entities: list[ParsedEntity] = []
    relations: list[ParsedRelation] = []

    file_entity = ParsedEntity(
        label="File",
        fqn=file_path,
        name=Path(file_path).name,
        file_path=file_path,
        line_start=1,
        line_end=len(source.splitlines()) or 1,
    )
    entities.append(file_entity)
    mod = ParsedEntity(
        label="Module",
        fqn=module_fqn,
        name=module_fqn.split(".")[-1],
        file_path=file_path,
        line_start=1,
        line_end=file_entity.line_end,
        docstring=_doc(tree),
    )
    entities.append(mod)
    relations.append(ParsedRelation("CONTAINS", file_path, module_fqn))

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imp_name = alias.name
                imp_fqn = f"{file_path}::import:{imp_name}"
                entities.append(
                    ParsedEntity(
                        label="Import",
                        fqn=imp_fqn,
                        name=imp_name,
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                    )
                )
                relations.append(ParsedRelation("IMPORTS", module_fqn, imp_fqn))
        elif isinstance(node, ast.ImportFrom):
            mod_name = node.module or ""
            for alias in node.names:
                imp_name = f"{mod_name}.{alias.name}" if mod_name else alias.name
                imp_fqn = f"{file_path}::import:{imp_name}"
                entities.append(
                    ParsedEntity(
                        label="Import",
                        fqn=imp_fqn,
                        name=imp_name,
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                    )
                )
                relations.append(ParsedRelation("IMPORTS", module_fqn, imp_fqn))
        elif isinstance(node, ast.ClassDef):
            cls_fqn = f"{module_fqn}.{node.name}"
            entities.append(
                ParsedEntity(
                    label="Class",
                    fqn=cls_fqn,
                    name=node.name,
                    file_path=file_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    docstring=_doc(node),
                )
            )
            relations.append(ParsedRelation("CONTAINS", module_fqn, cls_fqn))
            for base in node.bases:
                if isinstance(base, ast.Name):
                    relations.append(ParsedRelation("INHERITS_FROM", cls_fqn, base.id))
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name):
                    dec_fqn = f"{file_path}::decorator:{dec.id}"
                    entities.append(
                        ParsedEntity(
                            label="Decorator",
                            fqn=dec_fqn,
                            name=dec.id,
                            file_path=file_path,
                            line_start=dec.lineno,
                            line_end=dec.lineno,
                        )
                    )
                    relations.append(ParsedRelation("DECORATED_BY", cls_fqn, dec_fqn))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _add_function(
                        item,
                        module_fqn,
                        cls_fqn,
                        file_path,
                        entities,
                        relations,
                        label="Method",
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _add_function(node, module_fqn, module_fqn, file_path, entities, relations, label="Function")

    for ent in list(entities):
        if ent.docstring:
            doc_fqn = f"{ent.fqn}::doc"
            entities.append(
                ParsedEntity(
                    label="Docstring",
                    fqn=doc_fqn,
                    name="docstring",
                    file_path=ent.file_path,
                    line_start=ent.line_start,
                    line_end=ent.line_end,
                    docstring=ent.docstring,
                )
            )
            relations.append(ParsedRelation("DOCUMENTED_BY", ent.fqn, doc_fqn))

    return ParseResult(entities=entities, relations=relations)


def _add_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module_fqn: str,
    parent_fqn: str,
    file_path: str,
    entities: list[ParsedEntity],
    relations: list[ParsedRelation],
    *,
    label: str,
) -> None:
    fn_fqn = f"{module_fqn}.{node.name}" if label == "Function" else f"{parent_fqn}.{node.name}"
    entities.append(
        ParsedEntity(
            label=label,
            fqn=fn_fqn,
            name=node.name,
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            docstring=_doc(node),
        )
    )
    relations.append(ParsedRelation("CONTAINS", parent_fqn, fn_fqn))
    for idx, arg in enumerate(node.args.args):
        param_fqn = f"{fn_fqn}::param:{arg.arg}"
        entities.append(
            ParsedEntity(
                label="Parameter",
                fqn=param_fqn,
                name=arg.arg,
                file_path=file_path,
                line_start=node.lineno,
                line_end=node.lineno,
                extra={"index": str(idx)},
            )
        )
        relations.append(ParsedRelation("HAS_PARAMETER", fn_fqn, param_fqn))
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            dec_fqn = f"{file_path}::decorator:{dec.id}"
            entities.append(
                ParsedEntity(
                    label="Decorator",
                    fqn=dec_fqn,
                    name=dec.id,
                    file_path=file_path,
                    line_start=dec.lineno,
                    line_end=dec.lineno,
                )
            )
            relations.append(ParsedRelation("DECORATED_BY", fn_fqn, dec_fqn))


def parse_file_path(path: Path, repo_root: Path | None = None) -> ParseResult:
    source = path.read_text(encoding="utf-8")
    if repo_root is not None:
        rel = path.relative_to(repo_root).as_posix()
    else:
        rel = path.as_posix()
    return parse_python_ast(source, rel)
