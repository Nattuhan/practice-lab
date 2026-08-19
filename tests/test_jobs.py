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
