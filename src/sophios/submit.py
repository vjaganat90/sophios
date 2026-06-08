import json
from pathlib import Path
from pprint import pprint
import time
from typing import Any, cast

import requests

from .wic_types import RawJson

_TIMEOUT = (5, 30)
_STARTED = frozenset({"RUNNING", "COMPLETED", "ERROR", "CANCELLED"})
_SUCCESS = frozenset({"RUNNING", "COMPLETED"})


def submit(
    request_json: RawJson,
    submit_url: str,
    *,
    submission_id: str | None = None,
    timeout: tuple[int, int] = _TIMEOUT,
    poll_interval_seconds: int = 15,
    log_path: str | Path | None = None,
) -> int:
    """Submit serialized JSON text and wait for the job to start.

    This low-level transport API is intentionally schema-agnostic. If
    `submission_id` is omitted, the submitted JSON must contain a top-level
    `id` string so status and log endpoints can be polled.
    """
    request_mapping = _load_json_mapping(request_json)
    resolved_submission_id = submission_id or request_mapping.get("id")
    if not isinstance(resolved_submission_id, str) or not resolved_submission_id:
        raise ValueError("submit requires submission_id or a top-level JSON 'id' string")
    return _send_json_and_poll(
        request_json,
        submit_url,
        submission_id=resolved_submission_id,
        timeout=timeout,
        poll_interval_seconds=poll_interval_seconds,
        log_path=log_path,
    )


def _send_json_and_poll(
    request_json: str,
    submit_url: str,
    *,
    submission_id: str,
    timeout: tuple[int, int],
    poll_interval_seconds: int,
    log_path: str | Path | None,
) -> int:
    with requests.Session() as session:
        print("Sending request to Compute")
        response = session.post(
            _url(submit_url),
            data=request_json,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        print(f"Post response code: {response.status_code}")
        print(f"Submit response: {_json_or_text(response)}")
        if not response.ok:
            return 1

        phase = _wait_for_started(
            session,
            submit_url,
            submission_id,
            timeout=timeout,
            poll_interval_seconds=poll_interval_seconds,
        )
        if phase == "RUNNING":
            _print_logs(
                session,
                submit_url,
                submission_id,
                timeout=timeout,
                log_path=log_path,
            )
        else:
            print(
                f"Job reached {phase or 'an unknown state'} before RUNNING; skipping log fetch."
            )
        return 0 if phase in _SUCCESS else 1


def _wait_for_started(
    session: requests.Session,
    submit_url: str,
    submission_id: str,
    *,
    timeout: tuple[int, int],
    poll_interval_seconds: int,
) -> str:
    status_url = _url(submit_url, submission_id, "status")
    while True:
        response = session.get(status_url, timeout=timeout)
        response_body = _json_or_text(response)
        if response.ok and isinstance(response_body, dict) and "status" in response_body:
            print(json.dumps(response_body, indent=2))
            phase = str(response_body["status"]).upper()
            if phase in _STARTED:
                return phase
        time.sleep(poll_interval_seconds)


def _print_logs(
    session: requests.Session,
    submit_url: str,
    submission_id: str,
    *,
    timeout: tuple[int, int],
    log_path: str | Path | None,
) -> None:
    response = session.get(_url(submit_url, submission_id, "logs"), timeout=timeout)
    print(f"Logs response code: {response.status_code}")
    response_body = _json_or_text(response)
    print("Toil logs:")
    if isinstance(response_body, dict) and response_body:
        response_body = response_body[next(iter(response_body))]
    pprint(response_body, indent=4)
    if log_path is not None:
        Path(log_path).write_text(str(response_body), encoding="utf-8")


def _json_or_text(response: requests.Response) -> str | dict[str, Any] | list[Any]:
    try:
        response_body = response.json()
    except ValueError:
        return response.text
    if isinstance(response_body, dict):
        return cast(dict[str, Any], response_body)
    if isinstance(response_body, list):
        return response_body
    return str(response_body)


def _load_json_mapping(request_json: RawJson) -> dict[str, Any]:
    if not isinstance(request_json, str):
        raise TypeError("submit requires serialized JSON text, not a Python mapping")
    try:
        request_body = json.loads(request_json)
    except json.JSONDecodeError as exc:
        raise ValueError("submit requires valid serialized JSON text") from exc
    if not isinstance(request_body, dict):
        raise ValueError("submit requires serialized JSON object text")
    return cast(dict[str, Any], request_body)


def _url(submit_url: str, submission_id: str | None = None, endpoint: str | None = None) -> str:
    base = submit_url.rstrip("/") + "/"
    return base if submission_id is None else f"{base}{submission_id}/{endpoint}/"


__all__ = [
    "submit",
]
