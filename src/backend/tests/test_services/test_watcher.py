from app.services.watcher import compute_stable_changes


def test_new_file_stable_after_two_identical_polls():
    current = {"a.txt": "h1"}
    last_built = {}
    prev_poll = {"a.txt": "h1"}
    assert compute_stable_changes(current, last_built, prev_poll) == {"a.txt"}


def test_modified_file_included_when_stable():
    current = {"a.txt": "h2"}
    last_built = {"a.txt": "h1"}
    prev_poll = {"a.txt": "h2"}
    assert compute_stable_changes(current, last_built, prev_poll) == {"a.txt"}


def test_unchanged_file_excluded():
    current = {"a.txt": "h1"}
    last_built = {"a.txt": "h1"}
    prev_poll = {"a.txt": "h1"}
    assert compute_stable_changes(current, last_built, prev_poll) == set()


def test_unstable_file_excluded_until_settled():
    current = {"a.txt": "h2"}
    last_built = {"a.txt": "h1"}
    prev_poll = {"a.txt": "h1_partial"}
    assert compute_stable_changes(current, last_built, prev_poll) == set()


def test_new_file_excluded_on_first_sighting():
    current = {"a.txt": "h1"}
    last_built = {}
    prev_poll = {}
    assert compute_stable_changes(current, last_built, prev_poll) == set()
