"""Static (source-level) guards. They parse the code with `ast`, so they need neither FastAPI nor a model.

 * every pre-existing route is still declared, plus exactly the two new NLP routes
 * NLP is isolated: only the NLP endpoint, main.py (startup) and app/nlp itself import app.nlp - so chat,
   rides, riders, locations, health, services, repositories and deps can never call the model
 * NLP stays optional and off by default; requirements.txt gained no heavy dependency
"""
import ast
import re
from pathlib import Path

from tests.nlp_support import EXISTING_ROUTES, NEW_ROUTES

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _declared_routes() -> set:
    api_prefix = re.search(r'API_V1_PREFIX\s*:\s*str\s*=\s*"([^"]+)"', (APP / "core" / "config.py").read_text(encoding="utf-8")).group(1)
    prefix_of = {}
    for node in ast.walk(_tree(APP / "api" / "v1" / "router.py")):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "include_router":
            module = node.args[0].value.id  # e.g. chat in chat.router
            prefix_of[module] = next(kw.value.value for kw in node.keywords if kw.arg == "prefix")
    routes = set()
    for module, prefix in prefix_of.items():
        for node in ast.walk(_tree(APP / "api" / "v1" / "endpoints" / f"{module}.py")):
            if isinstance(node, ast.FunctionDef):
                for deco in node.decorator_list:
                    if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                            and isinstance(deco.func.value, ast.Name) and deco.func.value.id == "router"
                            and deco.func.attr in HTTP_METHODS):
                        routes.add((deco.func.attr.upper(), api_prefix + prefix + deco.args[0].value))
    return routes


def test_all_existing_routes_are_still_declared_plus_exactly_the_two_nlp_routes():
    declared = _declared_routes()
    assert EXISTING_ROUTES <= declared, f"missing existing routes: {sorted(EXISTING_ROUTES - declared)}"
    assert NEW_ROUTES <= declared, f"missing NLP routes: {sorted(NEW_ROUTES - declared)}"
    assert declared == EXISTING_ROUTES | NEW_ROUTES, f"unexpected extra routes: {sorted(declared - EXISTING_ROUTES - NEW_ROUTES)}"


def _imports_nlp(path: Path) -> list:
    hits = []
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "app.nlp" or module.startswith("app.nlp."):
                hits.append(module)
            elif module == "app" and any(a.name == "nlp" for a in node.names):
                hits.append("app.nlp")
            elif node.level > 0 and (module == "nlp" or module.startswith("nlp.") or any(a.name == "nlp" for a in node.names)):
                hits.append("." * node.level + module)
        elif isinstance(node, ast.Import):
            hits += [a.name for a in node.names if a.name == "app.nlp" or a.name.startswith("app.nlp.")]
    return hits


def test_only_the_nlp_endpoint_main_and_the_nlp_package_import_app_nlp():
    allowed = {APP / "main.py", APP / "api" / "v1" / "endpoints" / "nlp.py"}
    offenders = {}
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts or (APP / "nlp") in path.parents or path in allowed:
            continue
        hits = _imports_nlp(path)
        if hits:
            offenders[str(path.relative_to(BACKEND))] = hits
    assert not offenders, f"these modules must not use the NLP package: {offenders}"


def test_chat_and_safety_relevant_modules_do_not_import_nlp():
    names = ["api/v1/endpoints/chat.py", "api/v1/endpoints/rides.py", "api/v1/endpoints/riders.py",
             "api/v1/endpoints/locations.py", "api/v1/endpoints/health.py", "api/deps.py", "services/chat_service.py"]
    for name in names:
        path = APP / name
        if path.exists():
            assert _imports_nlp(path) == [], name
    for pkg in ("services", "repositories", "models"):
        for path in (APP / pkg).rglob("*.py"):
            assert _imports_nlp(path) == [], str(path)


def test_main_only_starts_loading_at_startup_and_nothing_else():
    source = (APP / "main.py").read_text(encoding="utf-8")
    assert source.count("start_background_load()") == 1
    assert "get_nlp_service().start_background_load()" in source


def _default_of(field: str):
    for node in ast.walk(_tree(APP / "core" / "config.py")):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == field:
            return node.value.value
    raise AssertionError(f"Settings has no field {field}")


def test_nlp_is_off_by_default_and_safe_defaults_are_declared():
    assert _default_of("NLP_ENABLED") is False
    assert _default_of("NLP_RETURN_RAW_OUTPUT") is False
    assert _default_of("NLP_ADAPTER_DIR") == ""
    assert _default_of("NLP_BASE_MODEL") == "Qwen/Qwen2.5-0.5B-Instruct"
    assert _default_of("NLP_LOCAL_FILES_ONLY") is False
    assert _default_of("NLP_QUEUE_TIMEOUT_SECONDS") == 10.0


def test_heavy_dependencies_are_optional_and_kept_out_of_requirements_txt():
    base = (BACKEND / "requirements.txt").read_text(encoding="utf-8").lower()
    for heavy in ("torch", "transformers", "peft", "accelerate"):
        assert heavy not in base, f"{heavy} must not be a required backend dependency"
    optional = (BACKEND / "requirements-nlp.txt").read_text(encoding="utf-8")
    for pin in ("torch==2.13.0", "transformers==5.15.1", "peft==0.21.2"):
        assert pin in optional


def test_torch_is_only_imported_lazily():
    tree = _tree(APP / "nlp" / "qwen_lora_service.py")
    top_level = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    for node in top_level:
        names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
        assert not any(n.split(".")[0] in ("torch", "transformers", "peft") for n in names), "heavy import at module level"
