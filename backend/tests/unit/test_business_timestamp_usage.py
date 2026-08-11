import ast
from pathlib import Path

FORBIDDEN_LOGGING_TIMESTAMPS = {"created_at", "updated_at"}
BUSINESS_LOGIC_ROOTS = (
    Path(__file__).parents[2] / "app" / "services",
    Path(__file__).parents[2] / "app" / "usecases",
)
BUSINESS_LOGIC_FILES = (
    Path(__file__).parents[2] / "app" / "libraries" / "auth_session_issuer.py",
    Path(__file__).parents[2] / "manage.py",
)


def test_business_logic_does_not_read_or_write_logging_timestamps() -> None:
    offenders: list[str] = []
    paths = [path for root in BUSINESS_LOGIC_ROOTS for path in sorted(root.rglob("*.py"))]
    paths.extend(BUSINESS_LOGIC_FILES)
    for path in paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_LOGGING_TIMESTAMPS:
                offenders.append(
                    f"{path.relative_to(Path(__file__).parents[2])}:{node.lineno} uses "
                    f"logging timestamp attribute {node.attr}; use a business timestamp column "
                    "such as registered_at, modified_at, occurred_at, or expires_at instead")
            if isinstance(node, ast.keyword) and node.arg in FORBIDDEN_LOGGING_TIMESTAMPS:
                offenders.append(
                    f"{path.relative_to(Path(__file__).parents[2])}:{node.lineno} passes "
                    f"logging timestamp keyword {node.arg}; use an explicit business timestamp "
                    "keyword instead")

    assert offenders == []
