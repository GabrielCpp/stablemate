"""What an operator reads of the workspace a run works in: the checkouts, a file and the
uncommitted change. groom asks the run's sidecar and falls back to reading the volume; the
book's groom has neither a sidecar nor a volume, so each read says it failed."""

from ostler.book import Answer, Endpoint, Field, Object, Str

from ...model import actions
from .shapes import DIFF, FILE_TEXT, RUN_ID, TREE

APP = "groom/groom/app.py::"
READERS = ("groom/groom/relpath.py", "groom/groom/localfs.py", "groom/groom/docker_io.py", "groom/groom/sidecar_hub.py", "groom/groom/sidecar.py")
CONTAINER = Object(container_id=Field(RUN_ID, does="the run's container id"))


class ReadFiles(Endpoint):
    method = "GET"
    path = "/files/{container_id}"
    params = CONTAINER
    query = Object(repo=Field(Str(), required=False, does="the checkout to list, when the run holds several"))
    answers = (Answer(200, TREE, "the repo-relative paths of the checkout, and whether the read failed"),)
    source = (APP + "files", APP + "_sidecar_rpc", APP + "_checkout_names", *READERS)
    does = "Lists the files of one run's checkout, from its sidecar or else from its workspace volume. A run with no volume fails the read."
    carries = actions.ReadFiles


class ReadFile(Endpoint):
    method = "GET"
    path = "/file/{container_id}"
    params = CONTAINER
    query = Object(
        repo=Field(Str(), required=False, does="the checkout the file is in"),
        path=Field(Str(), required=False, does="the repo-relative path of the file"),
    )
    answers = (Answer(200, FILE_TEXT, "the file's text, its language and whether the read failed"),)
    source = (APP + "file_content", "groom/groom/projection.py::file_lang", *READERS)
    does = "Reads one file of a run's checkout. The language is the highlight.js grammar the file name implies, whether the read worked or not."
    carries = actions.ReadFile


class ReadDiff(Endpoint):
    method = "GET"
    path = "/diff/{container_id}"
    params = CONTAINER
    query = Object(
        repo=Field(Str(), required=False),
        view=Field(Str(), required=False, does="branch reads the change since the branch started; anything else reads the uncommitted change"),
    )
    answers = (Answer(200, DIFF, "the diff, the untracked files and whether the read failed"),)
    source = (APP + "diff", APP + "_branch_start", "groom/groom/gitdiff.py", *READERS)
    does = "Reads the change of one run's checkout, from its sidecar or else from its volume. A run with no volume fails the read. With `view=branch` it reads only from the sidecar, against the merge base the sidecar computes, and a run with no sidecar fails the read. With no `view` the reply is the uncommitted read, unchanged."
    carries = actions.ReadDiff


ALL = (ReadFiles, ReadFile, ReadDiff)
