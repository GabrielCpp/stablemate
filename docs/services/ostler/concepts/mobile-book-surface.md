---
type: concept
slug: mobile-book-surface
title: The mobile surface of a book
---
# The mobile surface of a book

A mobile book plays an app on an Android emulator or phone the way a person drives it. It declares the same screens, components, interactions and typed inputs as a [web book](web-book-surface.md), and the run drives the device through Maestro and adb in place of a browser. Each interaction runs on the model and on the device, and the rows the screen then shows are compared with the model's rows.

The runtime supplies the device and the verbs a mobile book repeats: clearing and launching the app, forwarding a port, finding a component, typing, pressing, reading a value, and waiting on a component, a snackbar or a field's value. The book's surface supplies what is the app's own: how each interaction is performed, how the signed-in world is made, and how the rows are read. The surface subclasses `MobileSurface`, so its `self.browser` is the device and it writes the same `fill`, `press` and `wait_for` calls as a web surface.

A component is found by its semantics identifier, which a Flutter app sets with a `TestId`, or by its visible text or hint. The device reads the screen as Maestro reports it, and an empty field reads as empty even when the device reports its hint as its text.

- code: ostler/ostler/book/device.py::Device@0@46c138dc6375
- code: ostler/ostler/book/mobilesurface.py::MobileSurface@0@52853b996ba6
- code: ostler/ostler/qa/android.py::ScreenRecording@0@d83949660312
- rule: a mobile run records one video for each journey and each cell arrangement under `<out>/videos` with `adb screenrecord`, keeps it when a step failed or met a known defect or when `--keep-videos` is given, and lists each such step with the video and its offset as a web run does
- rule: the screen recording is the one the QA harness uses, so the segment loop lives in one module that both import
- rule: a mobile surface waits on an event, a component appearing, a snackbar showing or a field coming to hold a value, and a mobile book declares no sleep, timer or timeout
- rule: a mobile run needs adb, Maestro and a booted device, named by `ANDROID_SERIAL` when more than one is attached, and a run without them stops with an error that names what is missing
- rule: a text field is typed with the keyboard command, so text outside printable ASCII makes the input class unreachable and not a failure
- rule: a field whose reported text equals its hint holds nothing
- tests: ostler/tests/test_book_mobile.py::test_a_field_showing_only_its_hint_holds_nothing
- rule: a field is read back after typing and typed again up to three times, because the device drops keystrokes under load
- rule: a field that keeps only the first characters of a longer text makes the input class unreachable, and the surface puts the field back as it was
- rule: a generic step of a mobile book, such as clearing the app or reading a field, belongs to the runtime and the book's surface stays short
- tests: ostler/tests/test_book_mobile.py::test_a_component_is_found_by_its_id_or_by_its_name_and_role
- tests: ostler/tests/test_book_mobile.py::test_filling_replaces_what_the_field_holds_and_types_the_text
- tests: ostler/tests/test_book_mobile.py::test_a_field_that_caps_what_it_takes_is_unreachable_and_put_back
- tests: ostler/tests/test_book_mobile.py::test_the_segments_of_a_recording_are_pulled_in_order
- tests: ostler/tests/test_book_mobile.py::test_a_finished_recording_is_kept_or_deleted
