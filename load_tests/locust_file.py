import time
import uuid
from locust import HttpUser, task, between, events

TEST_REQUEST_BODY = {
    "request": "Source 500 units of Conference electronics unit and ship to Europe, 200 kg"
}

# Track admission-control specific outcomes separately from normal failures
admission_rejections = 0
completed_count = 0
failed_count = 0


class SupplyChainUser(HttpUser):
    wait_time = between(1, 3)  # gap between a user's successive requests

    @task
    def submit_and_wait_for_completion(self):
        global admission_rejections, completed_count, failed_count

        start = time.time()

        # Step 1: submit — this call itself is fast, Locust times it natively
        with self.client.post("/submit", json=TEST_REQUEST_BODY, catch_response=True, name="/submit") as submit_resp:
            if submit_resp.status_code != 200:
                submit_resp.failure(f"Submit failed: {submit_resp.status_code}")
                failed_count += 1
                return
            request_id = submit_resp.json().get("request_id")
            if not request_id:
                submit_resp.failure("No request_id returned")
                failed_count += 1
                return
            submit_resp.success()

        # Step 2: poll for completion — record as a separate custom timing
        # so p50/p95 reflects true end-to-end latency, not just the submit call
        poll_start = time.time()
        status = "queued"
        max_wait = 300  # 5 minutes ceiling per request
        result_data = None

        while status not in ("done",) and (time.time() - poll_start) < max_wait:
            time.sleep(2)
            resp = self.client.get(f"/result/{request_id}", name="/result/[id]")
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "unknown")
                result_data = data

        total_elapsed_ms = (time.time() - start) * 1000

        if status == "done":
            error_in_result = result_data.get("result", {}).get("error") if result_data else None
            if error_in_result and "admission timeout" in str(error_in_result):
                admission_rejections += 1
                events.request.fire(
                    request_type="E2E",
                    name="end_to_end_completion",
                    response_time=total_elapsed_ms,
                    response_length=0,
                    exception=Exception("admission_rejected"),
                )
            else:
                completed_count += 1
                events.request.fire(
                    request_type="E2E",
                    name="end_to_end_completion",
                    response_time=total_elapsed_ms,
                    response_length=0,
                    exception=None,
                )
        else:
            failed_count += 1
            events.request.fire(
                request_type="E2E",
                name="end_to_end_completion",
                response_time=total_elapsed_ms,
                response_length=0,
                exception=Exception(f"did_not_complete_status={status}"),
            )


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n=== CUSTOM SUMMARY ===")
    print(f"Fully completed: {completed_count}")
    print(f"Admission-rejected: {admission_rejections}")
    print(f"Failed/incomplete: {failed_count}")