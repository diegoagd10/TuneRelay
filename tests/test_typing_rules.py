"""D-10: one concrete type per variable.

No `Any` or `object` in annotations, and no unions of unrelated types: only
`X | None` is allowed.

Recorded exception (design D-10): `jsondata.py` may use `Any`, and only `Any`.
`json.loads` and `tomllib.loads` return untyped data, and under strict pyright
narrowing it (`isinstance(value, list)`) yields `Unknown` element types, so the
boundary needs one declared `Any`. Every getter there returns one concrete type
or `None`, so nothing untyped leaves that module.
"""

import ast
from pathlib import Path

import pytest

SOURCES = sorted((Path(__file__).parent.parent / "src" / "tunerelay").glob("*.py"))
JSON_BOUNDARY = {"jsondata.py"}
BANNED_NAMES = {"Any", "object"}


def annotations(tree: ast.Module) -> list[ast.expr]:
    found: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            found.append(node.annotation)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            arguments = node.args
            every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
            every += [arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None]
            found.extend(arg.annotation for arg in every if arg.annotation is not None)
            if node.returns is not None:
                found.append(node.returns)
    return [_unquote(annotation) for annotation in found]


def _unquote(annotation: ast.expr) -> ast.expr:
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return ast.parse(annotation.value, mode="eval").body
    return annotation


def _union_members(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _union_members(node.left) + _union_members(node.right)
    return [node]


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def violations(source: str, *, any_allowed: bool = False) -> list[str]:
    problems: list[str] = []
    for annotation in annotations(ast.parse(source)):
        nested = {
            id(child)
            for node in ast.walk(annotation)
            if isinstance(node, ast.BinOp)
            for child in (node.left, node.right)
        }
        for node in ast.walk(annotation):
            if not isinstance(node, ast.expr):
                continue
            name = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else ""
            )
            if name in BANNED_NAMES and not (any_allowed and name == "Any"):
                problems.append(f"line {node.lineno}: `{name}` in annotation")
            if name in {"Union", "Optional"}:
                problems.append(f"line {node.lineno}: use `X | None` instead of `{name}`")
            if isinstance(node, ast.BinOp) and id(node) not in nested:
                concrete = [m for m in _union_members(node) if not _is_none(m)]
                if len(concrete) > 1:
                    problems.append(f"line {node.lineno}: mixed union `{ast.unparse(node)}`")
    return problems


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: path.name)
def test_source_files_use_one_concrete_type_per_variable(path: Path) -> None:
    assert violations(path.read_text(), any_allowed=path.name in JSON_BOUNDARY) == []


def test_the_json_boundary_exception_covers_only_any() -> None:
    assert violations("x: dict[str, Any] = {}", any_allowed=True) == []
    assert violations("x: dict[str, object] = {}", any_allowed=True) == ["line 1: `object` in annotation"]
    assert violations("x: int | str = 1", any_allowed=True) == ["line 1: mixed union `int | str`"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x: int | None = None", []),
        ("def f(a: 'list[str] | None') -> None: ...", []),
        ("x: int | str = 1", ["line 1: mixed union `int | str`"]),
        ("def f(a: int | str | None) -> None: ...", ["line 1: mixed union `int | str | None`"]),
        ("def f() -> 'Song | Duplicate': ...", ["line 1: mixed union `Song | Duplicate`"]),
        ("def f(a: Any) -> None: ...", ["line 1: `Any` in annotation"]),
        ("x: dict[str, object] = {}", ["line 1: `object` in annotation"]),
        ("x: Optional[int] = None", ["line 1: use `X | None` instead of `Optional`"]),
        ("x: typing.Any = 1", ["line 1: `Any` in annotation"]),
    ],
)
def test_the_rule_itself(source: str, expected: list[str]) -> None:
    assert violations(source) == expected
