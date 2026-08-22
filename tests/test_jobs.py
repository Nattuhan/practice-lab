import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from practice_lab import app as app_module
from practice_lab import services


class JobRecoveryApiTests(unittest.TestCase):
    def setUp(self):
        self.job_id = "test-recovery-job"
        with services.JOB_LOCK:
            services.JOBS[self.job_id] = {
                "id": self.job_id,
                "stage": "interrupted",
                "message": "Application restarted; resume when ready",
                "description": "Queued cloud sync",
                "kind": "cloud-sync",
                "done": True,
                "interrupted": True,
                "resumable": True,
                "spec": {"type": "cloud_sync", "jobId": self.job_id},
            }

    def tearDown(self):
        with services.JOB_LOCK:
            services.JOBS.pop(self.job_id, None)

    def test_lists_only_recoverable_jobs(self):
        client = TestClient(app_module.create_app())
        response = client.get("/jobs?recoverable=true")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.job_id, [job["id"] for job in response.json()])

    def test_resume_uses_persisted_job_spec(self):
        client = TestClient(app_module.create_app())
        with patch.object(
            app_module,
            "submit_job_spec",
            return_value={"jobId": self.job_id, "stage": "queued", "message": "Queued cloud sync"},
        ) as submit:
            response = client.post(f"/jobs/{self.job_id}/resume")

        self.assertEqual(response.status_code, 200)
        submit.assert_called_once_with({"type": "cloud_sync", "jobId": self.job_id})

    def test_cancels_interrupted_job_permanently(self):
        client = TestClient(app_module.create_app())
        with patch.object(services, "persist_jobs_locked"):
            response = client.delete(f"/jobs/{self.job_id}/cancel-interrupted")

        self.assertEqual(response.status_code, 200)
        job = services.get_job_status(self.job_id)
        self.assertTrue(job["canceled"])
        self.assertFalse(job["resumable"])
        self.assertFalse(job["interrupted"])
        self.assertNotIn("spec", job)
        self.assertNotIn(self.job_id, [item["id"] for item in services.list_job_statuses(recoverable_only=True)])

    def test_archived_attempt_is_not_recoverable(self):
        archived_id = f"{self.job_id}:history:1"
        with services.JOB_LOCK:
            services.JOBS[archived_id] = {
                **services.JOBS[self.job_id],
                "id": archived_id,
                "archived": True,
            }
        try:
            recoverable = services.list_job_statuses(recoverable_only=True)
            self.assertNotIn(archived_id, [job["id"] for job in recoverable])
        finally:
            with services.JOB_LOCK:
                services.JOBS.pop(archived_id, None)

    def test_history_includes_duration_without_result_payload(self):
        with services.JOB_LOCK:
            services.JOBS[self.job_id].update({
                "started_at": 100.0,
                "updated_at": 112.5,
                "finished_at": 112.5,
                "result": {"large": "payload"},
            })
        client = TestClient(app_module.create_app())
        response = client.get("/jobs/history")

        self.assertEqual(response.status_code, 200)
        job = next(item for item in response.json() if item["id"] == self.job_id)
        self.assertEqual(job["duration_seconds"], 12.5)
        self.assertIsNone(job["result"])


if __name__ == "__main__":
    unittest.main()
