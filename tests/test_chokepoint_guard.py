import pytest

from nala.tools import ToolInvokedOutsideChokepoint
from nala.tools.archive_task import archive_task
from nala.tools.capture_task import capture_task
from nala.tools.memory_recall import memory_recall
from nala.tools.memory_write import memory_write
from nala.tools.report_status import report_status


def test_capture_task_direct_call_raises():
    with pytest.raises(ToolInvokedOutsideChokepoint):
        capture_task(title="x", project="life_os", priority="low", category="chore", client_ref="abc")


def test_report_status_direct_call_raises():
    with pytest.raises(ToolInvokedOutsideChokepoint):
        report_status()


def test_archive_task_direct_call_raises():
    with pytest.raises(ToolInvokedOutsideChokepoint):
        archive_task(task_id=1)


def test_memory_write_direct_call_raises():
    with pytest.raises(ToolInvokedOutsideChokepoint):
        memory_write(op="upsert_node", kind="person", label="Priya", purpose_scope="people")


def test_memory_recall_direct_call_raises():
    with pytest.raises(ToolInvokedOutsideChokepoint):
        memory_recall(label="Priya")
