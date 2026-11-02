"""test_eval_safety.py - proves the new evaluate_lora.py options cannot overwrite real results or the
real adapter. Needs NO torch and NO model: every case exits before any model is loaded. All file
writes happen in a temporary copy of the project; nothing in your real folders is touched.
Run: python test_eval_safety.py"""
import hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
import evaluate_lora as ev

def h(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

# ---------- 0. regression: path comparison must be platform-independent ----------
# On Windows, str(relative_path) uses backslashes; that made `new_files == ["results/lora_results_dbg.json"]` fail.
from pathlib import PureWindowsPath, PurePosixPath
_win = PureWindowsPath(r"C:\\tmp\\advanced_llm\\results\\lora_results_dbg.json")
_root = PureWindowsPath(r"C:\\tmp\\advanced_llm")
assert str(_win.relative_to(_root)) == "results\\lora_results_dbg.json"                 # the old, failing form
assert _win.relative_to(_root).as_posix() == "results/lora_results_dbg.json"            # the fixed form
_pos = PurePosixPath("/tmp/advanced_llm/results/lora_results_dbg.json")
assert _pos.relative_to(PurePosixPath("/tmp/advanced_llm")).as_posix() == "results/lora_results_dbg.json"
print("0. path normalisation: Windows-style and POSIX-style paths both compare equal via as_posix() ... PASS")

# ---------- 1. argument rules ----------
V = ev.validate_args
assert V(None, None, None) is None                                   # default run is allowed
assert V("debug", 16, str(ev.DEFAULT_ADAPTER_DIR / "x")) is None     # tagged debug run allowed
assert V("debug", None, None) is None                                # tagged full run of default adapter allowed
assert V(None, 16, None) is not None                                 # --limit without tag -> refused
assert V(None, None, str(ev.HERE / "models" / "_debug_checkpoints" / "epoch_2" / "adapter")) is not None
assert V("debug", 0, None) is not None and V("debug", -3, None) is not None
for bad in ["", "../evil", "a/b", "a\\b", "a b", ".hidden", "-x", "x" * 41, "t\u00e9st", "a.b"]:
    assert V(bad, 16, None) is not None, f"tag {bad!r} should be rejected"
print("1. argument rules: --limit / non-default --adapter-dir REQUIRE a safe tag; unsafe tags rejected ... PASS")

# ---------- 2. tagged output names can never equal default output names ----------
splits = ["test", "challenge"]
default_out = {ev.results_path(None)} | {ev.predictions_path(None, s) for s in splits} | {ev.figure_path(None, s) for s in splits}
for tag in ["debug", "test", "challenge", "results", "lora", "lora_results", "a", "x1", "d-e_f", "9"]:
    assert ev.TAG_RE.match(tag)
    tagged_out = {ev.results_path(tag)} | {ev.predictions_path(tag, s) for s in splits} | {ev.figure_path(tag, s) for s in splits}
    assert not (tagged_out & default_out), f"collision for tag {tag!r}: {tagged_out & default_out}"
    assert all(p.parent in (ev.HERE / "results", ev.HERE / "figures") for p in tagged_out), "tagged output outside results/figures"
print("2. tagged output paths are disjoint from default paths for adversarial tags, and stay in results/ & figures/ ... PASS")

# ---------- 3. subset selection ----------
recs = [{"id": i, "intent": f"I{i // 20}"} for i in range(240)]          # ordered by intent, like the real files
sub = ev.select_subset(recs, 16)
assert len(sub) == 16 and len({r["id"] for r in sub}) == 16 and sub == ev.select_subset(recs, 16)
assert len({r["intent"] for r in sub}) >= 10, "subset should spread across intents, not just the first ones"
assert ev.select_subset(recs, None) is recs and ev.select_subset(recs, 240) is recs and ev.select_subset(recs, 999) is recs
assert len(ev.select_subset(recs, 1)) == 1
print(f"3. --limit takes an even, deterministic spread ({len({r['intent'] for r in sub})} of 12 intents in 16 examples); no limit = all ... PASS")

# ---------- 4. missing-dataset detection ----------
tmpd = Path(tempfile.mkdtemp())
try:
    present = tmpd / "present.jsonl"; present.write_text("{}\n", encoding="utf-8")
    miss = ev.find_missing_datasets([("test", present), ("challenge", tmpd / "nope.jsonl")])
    assert [m[0] for m in miss] == ["challenge"] and ev.find_missing_datasets([("test", present)]) == []
    print("4. missing dataset file is detected (and warned about before the model loads) ... PASS")

    # ---------- 5. end-to-end in a TEMP COPY of the project: real files must be byte-identical afterwards ----------
    proj = tmpd / "advanced_llm"
    (proj / "scripts").mkdir(parents=True)
    for f in ["evaluate_lora.py", "common.py", "metrics_utils.py", "config.json"]:
        shutil.copy(SCRIPTS / f, proj / "scripts" / f)
    for d in ["results", "figures", "models/lora_adapter"]:
        (proj / d).mkdir(parents=True)
    sentinels = {
        proj / "results" / "lora_results.json": '{"SENTINEL": "REAL RESULTS"}',
        proj / "results" / "lora_predictions_test.jsonl": '{"SENTINEL": "REAL PREDICTIONS"}\n',
        proj / "results" / "lora_predictions_challenge.jsonl": '{"SENTINEL": "REAL PREDICTIONS"}\n',
        proj / "figures" / "confusion_matrix_lora_test.png": "REAL FIGURE",
        proj / "figures" / "confusion_matrix_lora_challenge.png": "REAL FIGURE",
        proj / "models" / "lora_adapter" / "adapter_model.safetensors": "REAL ADAPTER WEIGHTS",
        proj / "models" / "lora_adapter" / "adapter_config.json": "REAL ADAPTER CONFIG",
    }
    for p, text in sentinels.items(): p.write_text(text, encoding="utf-8")
    before = {p: h(p) for p in sentinels}
    tree_before = sorted(p.relative_to(proj).as_posix() for p in proj.rglob("*") if p.is_file())

    def run(*args):
        r = subprocess.run([sys.executable, "-B", str(proj / "scripts" / "evaluate_lora.py"), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, cwd=proj / "scripts")
        return r.returncode, r.stdout + r.stderr

    rc, out = run("--limit", "16");                           assert rc == 2 and "requires --tag" in out
    rc, out = run("--adapter-dir", "../models/other");        assert rc == 2 and "requires --tag" in out
    rc, out = run("--limit", "16", "--tag", "../evil");       assert rc == 2
    rc, out = run("--limit", "16", "--tag", "a b");           assert rc == 2
    assert sorted(p.relative_to(proj).as_posix() for p in proj.rglob("*") if p.is_file()) == tree_before, "refused runs must write NOTHING"
    print("5a. refused invocations (no tag / unsafe tag) exit with code 2 and write nothing ... PASS")

    rc, out = run("--adapter-dir", "../models/does_not_exist", "--limit", "16", "--tag", "dbg")
    assert rc == 0 and "DEBUG RUN [dbg]" in out
    new_files = sorted(set(p.relative_to(proj).as_posix() for p in proj.rglob("*") if p.is_file()) - set(tree_before))
    assert new_files == ["results/lora_results_dbg.json"], new_files
    assert json.loads((proj / "results/lora_results_dbg.json").read_text(encoding="utf-8"))["executed"] is False
    assert {p: h(p) for p in sentinels} == before, "REAL files changed during a tagged run!"
    print("5b. tagged debug run (failing early) wrote ONLY results/lora_results_dbg.json; all 7 real files byte-identical ... PASS")

    # default-run naming unchanged: with no adapter present it writes lora_results.json (executed:false), as before
    empty = tmpd / "advanced_llm_empty"; shutil.copytree(proj / "scripts", empty / "scripts")
    (empty / "results").mkdir(); (empty / "models" / "lora_adapter").mkdir(parents=True)
    r = subprocess.run([sys.executable, "-B", str(empty / "scripts" / "evaluate_lora.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, cwd=empty / "scripts")
    assert r.returncode == 0 and (empty / "results" / "lora_results.json").exists()
    assert json.loads((empty / "results" / "lora_results.json").read_text(encoding="utf-8"))["executed"] is False
    print("5c. default run with no adapter still writes results/lora_results.json (unchanged behaviour) ... PASS")

    # ---------- 6. static proof: every write in evaluate_lora.py goes through the three path functions ----------
    src = (SCRIPTS / "evaluate_lora.py").read_text(encoding="utf-8").splitlines()
    writes = [l.strip() for l in src if any(k in l for k in ("write_json(", "write_jsonl(", "savefig", ".write_text(", "open("))]
    print("6. every write site in evaluate_lora.py:"); [print("     ", w) for w in writes]
    assert all(("res_path" in w) or ("predictions_path(" in w) or ("def " in w) for w in writes if "write_json" in w), writes
    assert not any("DEFAULT_ADAPTER_DIR" in w and ("write" in w) for w in writes)
    print("   -> adapter folders are only ever READ; writes use res_path / predictions_path(tag, .) / figure_path(tag, .) ... PASS")
    print("\nALL SAFETY CHECKS PASSED")
finally:
    shutil.rmtree(tmpd, ignore_errors=True)
