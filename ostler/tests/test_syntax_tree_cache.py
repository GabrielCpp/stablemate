"""Lock down the syntax._tree lru_cache size against the eviction segfault."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ostler import behavior, syntax


EVICTION_MITIGATION_FLOOR = 64


def _go_source(body: str) -> str:
    return f'package api\nimport "net/http"\n\n{body}\n'


GO_TEMPLATES: tuple[str, ...] = (
    "func Handler(w http.ResponseWriter, r *http.Request) {{\n{w}\n}}\n",
    "type Service struct {{}}\nfunc (s *Service) {name}(req *http.Request) error {{\n{w}\nreturn nil\n}}\n",
    'func init() {{\nhttp.HandleFunc("/{name}", func(w http.ResponseWriter, r *http.Request) {{\n{w}\n}})\n}}\n',
)


def _synthesise_files(count: int) -> list[Path]:
    """Write *count* Go files into a temp dir, each unique by ``{name}`` and body."""
    tmpdir = Path(tempfile.mkdtemp(prefix="syntax-tree-cache-"))
    files: list[Path] = []
    for i in range(count):
        body = "\n".join(f"// variant {j}\nvar v{j} = {i * 100 + j}" for j in range(3))
        template = GO_TEMPLATES[i % len(GO_TEMPLATES)]
        text = template.format(name=f"F{i:04d}", w=body)
        path = tmpdir / f"file_{i:04d}.go"
        path.write_text(_go_source(text), encoding="utf-8")
        files.append(path)
    return files


def test_syntax_tree_cache_maxsize_matches_eviction_mitigation() -> None:
    """``syntax._tree`` must be wide enough that a single drive never evicts."""
    cache = syntax._tree
    params = cache.cache_parameters()
    assert isinstance(params, dict), (
        f"lru_cache.cache_parameters() should be a dict; got {type(params).__name__}"
    )
    assert params.get("maxsize") is not None, "syntax._tree must have a finite maxsize"
    assert params["maxsize"] >= EVICTION_MITIGATION_FLOOR, (
        f"syntax._tree maxsize must be >= {EVICTION_MITIGATION_FLOOR} "
        f"(the previous maxsize=16 evicted a Tree mid-visit and segfaulted); "
        f"got {params['maxsize']}. If you are reducing it for memory, also restore "
        f"the call-site hardening (behavior_go.GoEvidence._slice / "
        f"behavior_tree.TreeEvidence._slice reads source bytes directly so a freed "
        f"Tree is not dereferenced)."
    )


def test_unique_parses_stay_cached_below_eviction_threshold() -> None:
    """N unique parses at N below the floor must all remain cached."""
    text_samples = [
        _go_source(
            f"func F{i:04d}(r *http.Request) {{ /* unique body {i} */ }}",
        )
        for i in range(EVICTION_MITIGATION_FLOOR)
    ]

    syntax._tree.cache_clear()

    seen_ids: set[int] = set()
    for text in text_samples:
        tree = syntax._tree("go", text)
        seen_ids.add(id(tree))
    assert len(seen_ids) == EVICTION_MITIGATION_FLOOR, (
        f"every parse must yield a unique Tree; only {len(seen_ids)} distinct "
        f"trees survived {EVICTION_MITIGATION_FLOOR} parses — the lru_cache "
        f"evicted during the loop, which is exactly the regression that crashed "
        f"the api project's 312-file walk"
    )

    info = syntax._tree.cache_info()
    assert info.currsize == EVICTION_MITIGATION_FLOOR, (
        f"cache must hold all {EVICTION_MITIGATION_FLOOR} parses; "
        f"currsize={info.currsize} indicates an eviction occurred"
    )


def test_extract_evidence_across_synthesised_go_corpus_completes() -> None:
    """End-to-end shape: extract_evidence over a Go corpus never crashes."""
    files = _synthesise_files(EVICTION_MITIGATION_FLOOR)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "api"
            root.mkdir()
            for f in files:
                dst = root / f.name
                dst.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            paths = [f.name for f in files]
            inv = behavior.extract_evidence(root, paths)
            assert inv.files, "extract_evidence must report files for a Go corpus"
            assert inv.candidates, (
                "the synthesised corpus has at least one public declaration per "
                "file, so the inventory must surface at least one candidate"
            )
    finally:
        for f in files:
            f.unlink(missing_ok=True)
        files[0].parent.rmdir()
