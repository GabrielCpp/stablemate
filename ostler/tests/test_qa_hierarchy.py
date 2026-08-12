"""The device view hierarchy, translated into the elements the DOM scan produces.

The fixtures below are the shapes a live Android emulator actually printed — including the
`Running on <device>` banner `maestro hierarchy` puts on stdout ahead of its JSON, which is
the detail that makes a parser starting at byte zero fail on every device.
"""

from __future__ import annotations

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
