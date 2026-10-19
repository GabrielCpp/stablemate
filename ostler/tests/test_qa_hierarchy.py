"""The device view hierarchy, translated into the elements the DOM scan produces."""

from __future__ import annotations

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
