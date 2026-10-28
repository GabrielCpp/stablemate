"""The device view hierarchy, translated into the elements the DOM scan produces."""

from __future__ import annotations

import io
import json

import pytest

from ostler.qa.harness_host import load_harness_module

hierarchy = load_harness_module("ostler_qa_hierarchy")
scan = load_harness_module("ostler_qa_scan")

MAESTRO = """\
Running on emulator-5554

{
  "attributes": {},
  "children": [
    {
      "attributes": {"ignoreBoundsFiltering": "false"},
      "children": [
        {
          "attributes": {
            "resource-id": "com.example.app:id/content_frame",
            "class": "androidx.core.widget.NestedScrollView",
            "bounds": "[0,128][1080,2337]",
            "clickable": "false"
          },
          "children": [
            {
              "attributes": {
                "resource-id": "com.example.app:id/submit",
                "accessibilityText": "Submit",
                "text": "Submit",
                "class": "android.widget.Button",
                "bounds": "[40,2000][1040,2160]"
              },
              "children": []
            }
          ]
        }
      ]
    }
  ]
}
"""

UIAUTOMATOR = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        package="com.example.app" content-desc="" bounds="[0,0][1080,2400]">
    <node index="0" text="" resource-id="com.example.app:id/content_frame"
          class="androidx.core.widget.NestedScrollView" package="com.example.app"
          content-desc="" bounds="[0,128][1080,2337]">
      <node index="0" text="Submit" resource-id="com.example.app:id/submit"
            class="android.widget.Button" package="com.example.app"
            content-desc="Submit" bounds="[40,2000][1040,2160]" />
    </node>
  </node>
</hierarchy>
"""


def test_maestro_output_is_parsed_past_its_banner() -> None:
    elements = hierarchy.parse_maestro(MAESTRO)

    submit = [element for element in elements if element["selector"] == "submit"]
    assert submit, "the short form of a resource-id is a selector the book may have written"
    assert submit[0]["bbox"] == {"x": 40.0, "y": 2000.0, "width": 1000.0, "height": 160.0}
    assert submit[0]["role"] == "button"
    assert submit[0]["tag"] == "android.widget.Button"


def test_a_node_is_emitted_once_per_spelling_that_names_it() -> None:
    """Matching is by selector, so every name an element has has to reach the region."""
    regions = scan.merge_rects(hierarchy.parse_maestro(MAESTRO))

    button = next(region for region in regions if region["role"] == "button")
    assert button["selectors"] == ["com.example.app:id/submit", "submit", "Submit"]
    assert len(regions) == 2, "the two rects are two regions, whatever the spellings"


def test_maestro_output_without_json_says_so() -> None:
    with pytest.raises(ValueError, match="printed no JSON"):
        hierarchy.parse_maestro("Running on emulator-5554\nno device connected\n")


def test_uiautomator_reads_the_same_screen() -> None:
    """The two Android sources are interchangeable, which is the point of having both."""
    from_maestro = scan.merge_rects(hierarchy.parse_maestro(MAESTRO))
    from_dump = scan.merge_rects(hierarchy.parse_uiautomator(UIAUTOMATOR))

    boxes = {tuple(sorted(region["bbox"].items())) for region in from_maestro}
    assert boxes <= {tuple(sorted(region["bbox"].items())) for region in from_dump}
    assert [region["role"] for region in from_dump] == [None, "region", "button"]


def test_the_viewport_is_the_extent_of_what_was_measured() -> None:
    """Neither source's root node carries bounds, so the screen is read off its contents."""
    frame = hierarchy.frame_for(hierarchy.parse_maestro(MAESTRO))

    assert frame["viewport"] == {"width": 1080.0, "height": 2337.0}
    assert frame["document"] == frame["viewport"], "a device screen does not scroll itself"


def test_an_element_carries_the_name_the_node_announces_so_placement_can_hold_the_book_to_it() -> None:
    """Placement compares the book's `name:` against what the scan recorded; a census that records none reads as an observed silence."""
    submit = [e for e in hierarchy.parse_maestro(MAESTRO) if e["selector"] == "Submit"]
    assert submit and all(element["name"] == "Submit" for element in submit)
    region = next(r for r in scan.merge_rects(hierarchy.parse_maestro(MAESTRO)) if "Submit" in r["selectors"])
    assert region["names"][region["selectors"].index("Submit")] == "Submit"
    labelled_only_by_text = hierarchy.parse_maestro(
        '{"attributes": {"resource-id": "x:id/go", "text": "Go", "class": "android.widget.Button", '
        '"bounds": "[0,0][10,10]"}}'
    )
    assert {element["name"] for element in labelled_only_by_text} == {"Go"}


def test_an_element_no_attribute_names_falls_back_to_its_class() -> None:
    unnamed = hierarchy.parse_maestro(
        '{"attributes": {"class": "android.widget.LinearLayout", "bounds": "[0,0][10,10]"}}'
    )

    assert [element["selector"] for element in unnamed] == ["LinearLayout"]
    assert unnamed[0]["role"] == "", "a layout box is not a landmark, and guessing one lies"


def test_a_degenerate_rect_is_not_a_region() -> None:
    assert hierarchy.parse_maestro('{"attributes": {"bounds": "[0,0][0,0]", "class": "V"}}') == []


@pytest.mark.parametrize(
    ("class_name", "role"),
    [
        ("android.widget.EditText", "textbox"),
        ("androidx.recyclerview.widget.RecyclerView", "list"),
        ("androidx.appcompat.widget.Toolbar", "banner"),
        ("XCUIElementTypeButton", "button"),
        ("XCUIElementTypeNavigationBar", "navigation"),
        ("XCUIElementTypeStaticText", ""),
    ],
)
def test_a_widget_class_implies_a_role_on_either_platform(class_name: str, role: str) -> None:
    assert hierarchy.role_for(class_name) == role


def test_an_unknown_source_is_named_rather_than_ignored() -> None:
    with pytest.raises(ValueError, match="unknown hierarchy source"):
        hierarchy.scan(source="xcuitest")


def _hierarchy(*nodes: dict) -> str:
    return "Running on emulator-5554\n" + json.dumps({"attributes": {}, "children": list(nodes)})


def _drawn(**fields: object) -> dict:
    top = {key: fields.pop(key) for key in ("enabled", "checked", "selected") if isinstance(fields.get(key), bool)}
    return {"attributes": {"bounds": "[0,0][100,100]", **fields}, "children": [], **top}


def _shown(raw: str, **perceivable: object) -> bool:
    return hierarchy.DeviceReading(hierarchy.parse_device_nodes(raw)).shown(perceivable)


def test_a_device_node_is_found_by_the_name_in_its_text() -> None:
    raw = _hierarchy(_drawn(**{"class": "android.widget.Button", "text": "Open details"}))

    assert _shown(raw, role="button", name="Open details")


def test_a_device_node_is_not_found_by_a_test_id_alone() -> None:
    raw = _hierarchy(_drawn(**{"class": "android.widget.Button", "resource-id": "com.example.app:id/open details"}))

    assert not _shown(raw, role="button", name="Open details")
    assert not _shown(raw, role="button", name="open details")


def test_a_device_node_of_another_role_is_not_a_match() -> None:
    raw = _hierarchy(_drawn(**{"class": "android.widget.Button", "text": "Results"}))

    assert not _shown(raw, role="table", name="Results")


def test_a_node_whose_class_implies_no_role_matches_whatever_role_the_book_gives() -> None:
    raw = _hierarchy(_drawn(**{"class": "android.view.View", "content-desc": "Results"}))

    assert _shown(raw, role="table", name="Results")


def test_an_alert_is_found_by_the_text_it_contains() -> None:
    raw = _hierarchy(_drawn(**{"class": "android.widget.TextView", "text": "Error: Could not load results. Retry"}))

    assert _shown(raw, role="alert", name="Could not load results")
    assert not _shown(raw, role="button", name="Could not load results")


def test_a_progress_indicator_class_is_a_progressbar() -> None:
    raw = _hierarchy(_drawn(**{"class": "android.widget.ProgressBar", "content-desc": "Loading results"}))

    assert _shown(raw, role="progressbar", name="Loading results")
    assert not _shown(raw, role="button", name="Loading results")


def test_disabled_reads_the_top_level_field_and_the_attribute_string() -> None:
    field = _hierarchy(_drawn(**{"class": "android.widget.Button", "text": "Save", "enabled": False}))
    attribute = _hierarchy(_drawn(**{"class": "android.widget.Button", "text": "Save", "enabled": "false"}))
    enabled = _hierarchy(_drawn(**{"class": "android.widget.Button", "text": "Save", "enabled": True}))
    unknown = _hierarchy(_drawn(**{"class": "android.widget.Button", "text": "Save"}))

    assert _shown(field, role="button", name="Save", disabled=True)
    assert _shown(attribute, role="button", name="Save", disabled=True)
    assert not _shown(enabled, role="button", name="Save", disabled=True)
    assert not _shown(unknown, role="button", name="Save", disabled=True)


def test_checked_and_selected_need_the_hierarchy_to_say_so() -> None:
    raw = _hierarchy(_drawn(**{"class": "android.widget.CheckBox", "text": "Agree", "checked": "true"}))

    assert _shown(raw, role="checkbox", name="Agree", checked=True)
    assert not _shown(raw, role="checkbox", name="Agree", selected=True)


def test_a_node_with_no_area_is_not_drawn() -> None:
    raw = _hierarchy(_drawn(**{"class": "android.widget.Button", "text": "Save", "bounds": "[0,0][0,0]"}))

    assert not _shown(raw, role="button", name="Save")


def _inventory(*nodes: dict) -> str:
    return hierarchy.DeviceReading(hierarchy.parse_device_nodes(_hierarchy(*nodes))).inventory()


def test_a_device_inventory_lists_each_named_node_by_role_and_first_name() -> None:
    inventory = _inventory(
        _drawn(**{"class": "android.widget.Button", "text": "Open details"}),
        _drawn(**{"class": "android.widget.TextView", "text": "Welcome"}),
        _drawn(**{"class": "android.widget.Button"}),
    )

    assert inventory == "button 'Open details', element 'Welcome'"


def test_a_device_inventory_drops_duplicates_and_keeps_draw_order() -> None:
    inventory = _inventory(
        _drawn(**{"class": "android.widget.Button", "text": "Save"}),
        _drawn(**{"class": "android.widget.TextView", "text": "Title"}),
        _drawn(**{"class": "android.widget.Button", "text": "Save"}),
    )

    assert inventory == "button 'Save', element 'Title'"


def test_a_device_inventory_stops_at_forty_entries_and_says_so() -> None:
    nodes = [_drawn(**{"class": "android.widget.Button", "text": f"Item {index}"}) for index in range(41)]

    entries = _inventory(*nodes).split(", ")

    assert entries[:2] == ["button 'Item 0'", "button 'Item 1'"]
    assert entries[-2:] == ["button 'Item 39'", "…"]
    assert len(entries) == 41


def test_a_device_with_no_named_node_has_an_empty_inventory() -> None:
    assert _inventory(_drawn(**{"class": "android.widget.FrameLayout"})) == ""


MCP_CSV = '''\
Hierarchy of emulator-5554
element_num,depth,bounds,attributes,parent_num
0,0,,,
1,1,"[0,0][1080,2400]","class=android.widget.FrameLayout; enabled=true",0
2,2,"[0,275][1080,1517]","scrollable=true; class=android.widget.ScrollView; important-for-accessibility=true; enabled=true",1
3,3,"[40,300][1040,400]","text=Tea; milk=none; class=android.widget.TextView; enabled=true",2
4,3,"[40,420][1040,520]","text=Save; class=android.widget.Button; clickable=true",2
5,3,"[40,540][1040,640]","hintText=Your email; class=android.widget.EditText; enabled=true; focused=true",2
'''


def _csv_shown(**perceivable: object) -> bool:
    nodes = hierarchy.parse_device_nodes(hierarchy.csv_to_hierarchy(MCP_CSV))
    return hierarchy.DeviceReading(nodes).shown(perceivable)


def test_the_csv_reply_becomes_a_tree_the_json_parsers_read() -> None:
    tree = json.loads(hierarchy.csv_to_hierarchy(MCP_CSV))

    scroll = tree["children"][0]["children"][0]["children"][0]
    assert scroll["attributes"]["class"] == "android.widget.ScrollView"
    assert scroll["attributes"]["bounds"] == "[0,275][1080,1517]"
    assert [child["attributes"].get("text") for child in scroll["children"]] == ["Tea; milk=none", "Save", None]


def test_a_text_holding_a_semicolon_and_an_equals_sign_matches_whole() -> None:
    assert _csv_shown(role="list", name="Tea; milk=none")
    assert not _csv_shown(role="list", name="Tea")


def test_a_field_is_found_by_its_hint() -> None:
    assert _csv_shown(role="textbox", name="Your email")


def test_a_button_missing_its_enabled_key_is_disabled() -> None:
    assert _csv_shown(role="button", name="Save", disabled=True)
    assert not _csv_shown(role="textbox", name="Your email", disabled=True)


def test_a_csv_with_no_header_is_refused() -> None:
    with pytest.raises(ValueError, match="no CSV header"):
        hierarchy.csv_to_hierarchy("nothing here")


def test_a_reply_joins_its_text_parts() -> None:
    reply = {"result": {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}}

    assert hierarchy.reply_text(reply) == "a\nb"


def test_a_reply_that_reports_an_error_raises_with_its_text() -> None:
    with pytest.raises(RuntimeError, match="no device"):
        hierarchy.reply_text({"result": {"isError": True, "content": [{"text": "no device"}]}})
    with pytest.raises(RuntimeError, match="boom"):
        hierarchy.reply_text({"error": {"code": -1, "message": "boom"}})


class _Process:
    def __init__(self, replies: list[str]) -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(reply + "\n" for reply in replies))
        self.killed = False

    def poll(self) -> int | None:
        return 0 if self.killed else None

    def kill(self) -> None:
        self.killed = True

    def terminate(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        return 0


def _answers(*texts: str) -> list[str]:
    handshake = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
    calls = [
        json.dumps({"jsonrpc": "2.0", "id": index + 2, "result": {"content": [{"type": "text", "text": text}]}})
        for index, text in enumerate(texts)
    ]
    return [handshake, *calls]


def test_the_resident_reader_handshakes_once_and_reads_the_device_by_its_serial() -> None:
    process = _Process(_answers("first", "second"))
    launched: list[_Process] = []

    def launch() -> _Process:
        launched.append(process)
        return process

    reader = hierarchy.ResidentReader(launch, lambda timeout: "emulator-5554")

    assert [reader(5), reader(5)] == ["first", "second"]
    assert len(launched) == 1
    sent = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert [message.get("method") for message in sent] == [
        "initialize", "notifications/initialized", "tools/call", "tools/call",
    ]
    assert sent[2]["params"] == {"name": "inspect_view_hierarchy", "arguments": {"device_id": "emulator-5554"}}


def test_a_session_that_closes_mid_read_is_replaced_once_and_the_read_retried() -> None:
    processes = [_Process(_answers()), _Process(_answers("again"))]
    reader = hierarchy.ResidentReader(lambda: processes.pop(0), lambda timeout: "serial")

    assert reader(5) == "again"


def test_a_session_that_closes_twice_raises_naming_what_happened() -> None:
    processes = [_Process(_answers()), _Process(_answers())]
    reader = hierarchy.ResidentReader(lambda: processes.pop(0), lambda timeout: "serial")

    with pytest.raises(RuntimeError, match="ended twice"):
        reader(5)


def test_a_released_reader_stops_its_process_and_the_next_read_starts_a_fresh_one() -> None:
    first, second = _Process(_answers("one")), _Process(_answers("two"))
    processes = [first, second]
    reader = hierarchy.ResidentReader(lambda: processes.pop(0), lambda timeout: "serial")

    assert reader(5) == "one"
    reader.shutdown()

    assert first.killed
    assert not second.killed
    assert reader(5) == "two"
    assert processes == []


def test_releasing_the_device_shuts_the_run_resident_reader_down(monkeypatch: pytest.MonkeyPatch) -> None:
    stopped: list[str] = []
    monkeypatch.setattr(hierarchy.RESIDENT, "shutdown", lambda: stopped.append("shutdown"))

    hierarchy.release_device()

    assert stopped == ["shutdown"]


def test_a_maestro_hierarchy_scan_releases_the_device_first(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(hierarchy.shutil, "which", lambda name: "/usr/bin/maestro")
    monkeypatch.setattr(hierarchy, "release_device", lambda: events.append("release"))
    monkeypatch.setattr(hierarchy, "_run", lambda command, *, timeout: events.append("hierarchy") or MAESTRO)

    hierarchy.maestro_elements()

    assert events == ["release", "hierarchy"]


def test_a_missing_maestro_raises_the_install_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hierarchy.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="the maestro CLI is not installed on this machine"):
        hierarchy.ResidentReader()(5)


def _device_node(text: str) -> object:
    raw = _hierarchy(_drawn(**{"class": "android.widget.TextView", "text": text}))
    return hierarchy.parse_device_nodes(raw)[0]


def test_a_device_node_carries_its_bounds_and_whether_it_scrolls() -> None:
    raw = _hierarchy(_drawn(**{"class": "android.widget.ScrollView", "scrollable": "true", "bounds": "[0,275][1080,1517]"}))

    node = hierarchy.parse_device_nodes(raw)[0]

    assert (node.bounds, node.scrollable) == ((0, 275, 1080, 1517), True)


def test_a_reading_asks_its_scan_only_on_a_miss_and_only_once() -> None:
    calls: list[int] = []

    def scan() -> list[object]:
        calls.append(1)
        return [_device_node("Below the fold")]

    nodes = hierarchy.parse_device_nodes(_hierarchy(_drawn(**{"class": "android.widget.TextView", "text": "Here"})))
    reading = hierarchy.DeviceReading(nodes, scan)

    assert reading.shown({"role": "button", "name": "Here"})
    assert calls == []
    assert reading.shown({"role": "button", "name": "Below the fold"})
    assert not reading.shown({"role": "button", "name": "Nowhere"})
    assert calls == [1]


def test_an_inventory_lists_the_scanned_nodes_after_the_viewport_ones() -> None:
    nodes = hierarchy.parse_device_nodes(_hierarchy(_drawn(**{"class": "android.widget.TextView", "text": "Here"})))
    reading = hierarchy.DeviceReading(nodes, lambda: [_device_node("There")])

    assert reading.inventory() == "element 'Here'"
    reading.shown({"role": "button", "name": "There"})
    assert reading.inventory() == "element 'Here', element 'There'"
