from unittest import mock

import pytest
from gi.repository import Gtk


@pytest.mark.parametrize(
    "text, ignored_ranges, expected_text",
    [
        #    0123456789012345678901234567890123456789012345678901234567890123456789
        # Matching without groups
        (
            "# asdasdasdasdsad",
            [(0, 17)],
            "",
        ),
        # Matching with single group
        (
            "asdasdasdasdsab",
            [(1, 14)],
            "ab",
        ),
        # Matching with multiple groups
        (
            "xasdyasdz",
            [(1, 4), (5, 8)],
            "xyz",
        ),
        # Matching with multiple partially overlapping filters
        (
            "qaqxqbyqzq",
            [(2, 6), (7, 8)],
            "qayzq",
        ),
        # Matching with multiple fully overlapping filters
        (
            "qaqxqybqzq",
            [(2, 8)],
            "qazq",
        ),
        # Matching with and without groups, with single dominated match
        (
            "# asdasdasdasdsab",
            [(0, 17)],
            "",
        ),
        # Matching with and without groups, with partially overlapping filters
        (
            "/*a*/ub",
            [(0, 6)],
            "b",
        ),
        # Non-matching with groups
        (
            "xasdyasdx",
            [],
            "xasdyasdx",
        ),
        # Multiple lines with non-overlapping filters
        (
            "#ab\na2b",
            [(0, 3), (5, 6)],
            "\nab",
        ),
        # CVS keyword
        (
            "$Author: John Doe $",
            [(8, 18)],
            "$Author:$",
        ),
    ],
)
def test_filter_text(text, ignored_ranges, expected_text):
    from meld.filediff import FileDiff
    from meld.filters import FilterEntry

    filter_patterns = [
        "#.*",
        r"/\*.*\*/",
        "a(.*)b",
        "x(.*)y(.*)z",
        r"\$\w+:([^\n$]+)\$",
    ]
    filters = [
        FilterEntry.new_from_gsetting(("name", True, f), FilterEntry.REGEX)
        for f in filter_patterns
    ]

    filediff = mock.MagicMock()
    filediff.text_filters = filters
    filter_text = FileDiff._filter_text

    buf = Gtk.TextBuffer()
    buf.create_tag("inline")
    buf.create_tag("dimmed")
    buf.set_text(text)
    start, end = buf.get_bounds()

    text = filter_text(filediff, buf.get_text(start, end, False), buf, start, end)

    # Find ignored ranges
    tag = buf.get_tag_table().lookup("dimmed")
    toggles = []
    it = start.copy()
    if it.toggles_tag(tag):
        toggles.append(it.get_offset())
    while it.forward_to_tag_toggle(tag):
        toggles.append(it.get_offset())
    toggles = list(zip(toggles[::2], toggles[1::2]))

    print("Text:", text)
    print("Toggles:", toggles)

    assert toggles == ignored_ranges
    assert text == expected_text


@pytest.mark.parametrize(
    "num_panes, focused, action, expected",
    [
        (2, 0, "action_next_pane", 1),
        (2, 1, "action_next_pane", 0),  # wraps, so two panes toggle
        (2, 0, "action_prev_pane", 1),
        (3, 2, "action_next_pane", 0),
        (3, 0, "action_prev_pane", 2),
        (3, 1, "action_next_pane", 2),
    ],
)
def test_pane_cycling(num_panes, focused, action, expected):
    from meld.filediff import FileDiff

    filediff = mock.MagicMock(spec=FileDiff)
    filediff.num_panes = num_panes
    filediff._get_focused_pane.return_value = focused
    filediff._switch_pane = lambda n: FileDiff._switch_pane(filediff, n)
    filediff.textview = [mock.Mock() for _ in range(num_panes)]

    getattr(FileDiff, action)(filediff)

    filediff.move_cursor_pane.assert_called_once_with(focused, expected)


def test_pane_focus_without_focused_textview():
    from meld.filediff import FileDiff

    filediff = mock.MagicMock(spec=FileDiff)
    filediff.num_panes = 3
    filediff._get_focused_pane.return_value = -1
    filediff.textview = [mock.Mock() for _ in range(3)]
    filediff._switch_pane = lambda n: FileDiff._switch_pane(filediff, n)

    FileDiff.action_next_pane(filediff)

    filediff.move_cursor_pane.assert_not_called()
    filediff.textview[0].grab_focus.assert_called_once()


@pytest.mark.parametrize(
    "target, called", [(0, True), (2, True), (3, False), (-1, False)]
)
def test_focus_pane_action(target, called):
    from gi.repository import GLib

    from meld.filediff import FileDiff

    filediff = mock.MagicMock(spec=FileDiff)
    filediff.num_panes = 3
    FileDiff.action_focus_pane(filediff, None, GLib.Variant.new_int32(target))
    assert filediff._switch_pane.called == called


def _filediff_mock(num_panes=2):
    from meld.filediff import FileDiff

    filediff = mock.MagicMock(spec=FileDiff)
    filediff.num_panes = num_panes
    filediff.textbuffer = [mock.Mock() for _ in range(num_panes)]
    # Behave as if the user confirmed discarding any unsaved changes
    filediff.confirm_unsaved_change_action = lambda on_confirm, buffers=None: (
        on_confirm()
    )
    return filediff


def test_revert_pane_reloads_pane():
    # Regression test: the "File has changed on disk" info bar's Reload
    # button called a removed method (check_unsaved_changes), so nothing
    # happened when it was clicked.
    from meld.filediff import FileDiff

    filediff = _filediff_mock()
    FileDiff.revert_pane(filediff, 1)

    data = filediff.textbuffer[1].data
    filediff.set_file.assert_called_once_with(1, data.gfile, data.encoding)


def test_revert_pane_confirms_before_discarding():
    from meld.filediff import FileDiff

    filediff = _filediff_mock()
    filediff.confirm_unsaved_change_action = mock.Mock()
    FileDiff.revert_pane(filediff, 0)

    filediff.confirm_unsaved_change_action.assert_called_once()
    filediff.set_file.assert_not_called()


def test_refresh_without_disk_changes_only_rediffs():
    from meld.filediff import FileDiff

    filediff = _filediff_mock()
    for buf in filediff.textbuffer:
        buf.data.changed_on_disk.return_value = False
    FileDiff.action_refresh(filediff)

    filediff.refresh_comparison.assert_called_once()
    filediff.set_files.assert_not_called()


def test_refresh_reloads_only_files_changed_on_disk():
    from meld.filediff import FileDiff

    filediff = _filediff_mock(3)
    for buf, changed in zip(filediff.textbuffer, (True, False, True)):
        buf.data.changed_on_disk.return_value = changed
    FileDiff.action_refresh(filediff)

    filediff.refresh_comparison.assert_not_called()
    gfiles = filediff.set_files.call_args.args[0]
    encodings = filediff.set_files.call_args.kwargs["encodings"]
    data = [buf.data for buf in filediff.textbuffer]
    assert gfiles == [data[0].gfile, None, data[2].gfile]
    assert encodings == [data[0].encoding, None, data[2].encoding]
