"""Lock down the syntax._tree lru_cache size against the eviction segfault.

A cached ``Tree`` is freed the moment the lru_cache evicts its entry; a still-running
visitor that holds a child ``Node`` keeps the Python wrapper alive but the *C AST*
the wrapper dereferences is gone. The next ``node.start_byte`` read or ``Node.text``
property access crosses into freed memory, escapes Python's exception machinery, and
segfaults the interpreter (``bd8d0fd1`` for the 0.26.0 binding version of the fault;
``190495e7`` for the broader eviction class on 0.25.x).

The mitigation is twofold. The first layer — ``syntax._tree`` having
``maxsize=4096`` — was the load-bearing change in ``190495e7``; the second layer —
``behavior_go.GoEvidence._slice`` / ``behavior_tree.TreeEvidence._slice`` reading
``source_bytes[start:end].decode()`` instead of ``Node.text`` — is independent and
defends against the same fault class through a different path.

The post-fix commit message claims the size is enough that "no eviction happens
during a single drive, which is the only time the visitor holds ``Node`` references
without holding the ``Tree`` reference alongside." That is the property these tests
pin. A regression that shrinks the cache (someone tightening it to free a few KB,
or a partial revert) is caught here before any production drive does.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ostler import behavior, syntax


#: Parses that a single okf-builder drive typically does. A multi-hundred-file
#: evidence walk reads every referenced source file once and re-reads citations;
#: we round up to 64 to leave headroom over the previous ``maxsize=16`` that
#: triggered the fault and below the post-fix 4096.
EVICTION_MITIGATION_FLOOR = 64


#: Sources are synthesised in-process so the test runs without an external Go repo
#: (the existing ``test_py_tree_sitter_0_26_0_segfault`` skips on a missing
#: ``/mnt/data/workspace/example/api``; this test never needs that).
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
    """``syntax._tree`` must be wide enough that a single drive never evicts.

    The pre-fix ``maxsize=16`` evicted a Tree under a still-running visitor; the
    read-after-free segfaulted the interpreter. The mitigation is the cache size
    jumping to 4096, which ``190495e7`` justified as larger than any realistic
    drive. Asserting a floor here catches a regression that tightens the cache
    below the eviction threshold without also restoring the call-site hardening.
    """
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
    """N unique parses at N below the floor must all remain cached.

    Proves: with the post-fix ``maxsize=4096``, parsing more files than the
    previous ``maxsize=16`` does not evict any entry. A regression to ``maxsize=16``
    shows up here as ``currsize < N`` after the loop, even though the loop
    itself would not crash (an eviction-driven crash needs a Node held across
    the eviction; this test asserts the cache *width*, not the absence of a held
    Node).
    """
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
    """End-to-end shape: extract_evidence over a Go corpus never crashes.

    The pre-fix crash surfaced in the okf-builder flow's audit leg, which calls
    ``extract_evidence`` on a multi-hundred-file Go project. We synthesise a
    corpus larger than the previous maxsize so the visit pattern walks across the
    eviction boundary; with the post-fix cache the walk completes and the bytes
    the visitor reads via ``_slice`` come from the held ``source_bytes`` rather
    than from the freed Tree's C extension — neither path crashes.
    """
    files = _synthesise_files(EVICTION_MITIGATION_FLOOR)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "api"
            root.mkdir()
            for f in files:
                # Re-use the synthesised file body but place it under root
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
