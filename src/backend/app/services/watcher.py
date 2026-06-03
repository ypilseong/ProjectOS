def compute_stable_changes(
    current: dict[str, str],
    last_built: dict[str, str],
    prev_poll: dict[str, str],
) -> set[str]:
    """변경(신규/수정)되었고 직전 폴링 대비 안정된 파일명 집합을 반환.

    - 변경: last_built에 해시가 없거나(신규) 다름(수정).
    - 안정: prev_poll의 해시가 current와 동일(쓰기/동기화 완료).
    """
    stable: set[str] = set()
    for fname, h in current.items():
        changed = last_built.get(fname) != h
        settled = prev_poll.get(fname) == h
        if changed and settled:
            stable.add(fname)
    return stable
