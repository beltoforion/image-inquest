import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanError:
    """Describes a problem encountered while scanning a node file."""
    file: Path
    message: str

    def __str__(self) -> str:
        return f"{self.file.name}: {self.message}"


class NodeRegistry:
    """Discovers node classes in Python source files via AST scanning.

    The registry maps class names to display names without importing or
    instantiating any node class.  Use it to populate menus or node
    palettes in the UI.

    Typical usage at application startup:

        registry = NodeRegistry()
        errors  = registry.scan_builtin(BUILTIN_NODES_DIR)
        errors += registry.scan_user(USER_NODES_DIR)
        if errors:
            # show popup with errors (handled by UI layer)
            ...
    """

    def __init__(self) -> None:
        self._nodes: dict[str, str] = {}  # class_name -> display_name

    # ── Scanning ───────────────────────────────────────────────────────────────

    def scan_builtin(self, folder: Path) -> list[ScanError]:
        """Scan the built-in nodes folder recursively.

        All .py files under folder and its subdirectories are scanned.
        Returns a list of any parse errors encountered.
        """
        return self._scan(folder, reject_conflicts=False)

    def scan_user(self, folder: Path) -> list[ScanError]:
        """Scan the user nodes folder recursively, creating it if absent.

        User node class names must not conflict with already-registered
        built-in nodes — conflicts are rejected and reported as errors.
        Returns a list of parse errors and conflict rejections.
        """
        _ensure_user_nodes_dir(folder)
        return self._scan(folder, reject_conflicts=True)

    def _scan(self, folder: Path, reject_conflicts: bool) -> list[ScanError]:
        errors: list[ScanError] = []
        for path in sorted(folder.rglob("*.py")):
            found, file_errors = _parse_node_file(path)
            errors.extend(file_errors)
            for class_name, display_name in found.items():
                if reject_conflicts and class_name in self._nodes:
                    errors.append(ScanError(
                        file=path,
                        message=(
                            f"'{class_name}' conflicts with a built-in node "
                            f"and was not loaded"
                        ),
                    ))
                else:
                    self._nodes[class_name] = display_name
        return errors

    # ── Access ─────────────────────────────────────────────────────────────────

    @property
    def nodes(self) -> dict[str, str]:
        """Return a {class_name: display_name} snapshot of all registered nodes."""
        return dict(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def __iter__(self):
        return iter(self._nodes.items())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ensure_user_nodes_dir(folder: Path) -> None:
    """Create the user nodes folder and its subdirectories if they don't exist."""
    for subdir in (folder, folder / "sources", folder / "sinks", folder / "filters"):
        subdir.mkdir(parents=True, exist_ok=True)


# ── Internal AST helpers ───────────────────────────────────────────────────────

def _parse_node_file(path: Path) -> tuple[dict[str, str], list[ScanError]]:
    """Return ({class_name: display_name}, [errors]) for a single file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return {}, [ScanError(file=path, message=f"Syntax error: {e.msg} (line {e.lineno})")]
    except OSError as e:
        return {}, [ScanError(file=path, message=f"Could not read file: {e}")]

    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            entry = _extract_node_entry(node)
            if entry is not None:
                class_name, display_name = entry
                result[class_name] = display_name
    return result, []


def _extract_node_entry(class_node: ast.ClassDef) -> tuple[str, str] | None:
    """Return (class_name, display_name) if the class looks like a node, else None."""
    init = _find_init(class_node)
    if init is None or not _has_super_init(init):
        return None
    if _count_self_calls(init, "_add_input") == 0 and _count_self_calls(init, "_add_output") == 0:
        return None
    display_name = _extract_super_init_name(init) or class_node.name
    return class_node.name, display_name


def _find_init(class_node: ast.ClassDef) -> ast.FunctionDef | None:
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            return item
    return None


def _has_super_init(init_node: ast.FunctionDef) -> bool:
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "__init__"):
            continue
        if isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name) and func.value.func.id == "super":
            return True
    return False


def _extract_super_init_name(init_node: ast.FunctionDef) -> str | None:
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "__init__"):
            continue
        if not (isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name) and func.value.func.id == "super"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            return node.args[0].value
    return None


def _count_self_calls(init_node: ast.FunctionDef, method_name: str) -> int:
    count = 0
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == method_name
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            count += 1
    return count
