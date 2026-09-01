import asyncio
import uuid
import httpx
from a2a.client import create_client, ClientConfig
from a2a.types import SendMessageRequest, Message, Part, Role, TaskState


async def send_a2a_task(base_url: str, text: str) -> dict:
    long_timeout_client = httpx.AsyncClient(timeout=180.0)
    config = ClientConfig(httpx_client=long_timeout_client)

    client = await create_client(agent=base_url, client_config=config)
    try:
        msg = Message(
            message_id=str(uuid.uuid4()),
            context_id=str(uuid.uuid4()),
            role=Role.ROLE_USER,
            parts=[Part(text=text)],
        )
        request = SendMessageRequest(message=msg)

        final_state = None
        artifact_text = None

        async for response in client.send_message(request):
            if response.status_update:
                final_state = response.status_update.status.state
                if final_state in (TaskState.TASK_STATE_COMPLETED, TaskState.TASK_STATE_FAILED):
                    break
            if response.task:
                final_state = response.task.status.state
                for artifact in response.task.artifacts:
                    for part in artifact.parts:
                        if part.text:
                            artifact_text = part.text
            if response.artifact_update:
                for part in response.artifact_update.artifact.parts:
                    if part.text:
                        artifact_text = part.text

        return {"final_state": final_state, "artifact": artifact_text}
    finally:
        await client.close()
        await long_timeout_client.aclose()


async def main():
    procurement_requests = [
        "Source 500 units of Conference electronics unit",
        "Source 200 units of Employee electronics unit with target price under 400",
        "Source 1000 units of Usually electronics unit",
        "Source 150 units of Throw electronics unit with target price under 150",
        "Source 300 units of Star electronics unit",
        "Source 750 units of Ground electronics unit with target price under 200",
        "Source 100 units of Half electronics unit",
        "Source 400 units of Decide electronics unit with target price under 350",
        "Source 250 units of General electronics unit",
        "Source 600 units of Particularly electronics unit with target price under 150",
    ]

    logistics_requests = [
        "Ship 200 kg to Europe",
        "Ship 500 kg from APAC to LATAM",
        "Ship 50 kg to North America with max transit 5 days",
        "Ship 1000 kg to MEA",
        "Ship 300 kg from Europe to APAC",
        "Ship 75 kg to LATAM with max transit 10 days",
        "Ship 850 kg to North America",
        "Ship 120 kg from MEA to Europe",
        "Ship 400 kg to APAC with max transit 7 days",
        "Ship 60 kg to LATAM",
    ]

    compliance_requests = [
        "Check compliance for supplier Alpha with trust score 0.9, terms net-30, unit price 100, max approved price 150",
        "Check compliance for supplier Beta with trust score 0.4, terms cash-on-delivery, unit price 500, max approved price 200",
        "Check compliance for supplier Gamma with trust score 0.75, terms net-60, unit price 250, max approved price 300",
        "Check compliance for supplier Delta with trust score 0.55, terms prepaid, unit price 80, max approved price 100",
        "Check compliance for supplier Epsilon with trust score 0.3, terms net-15, unit price 600, max approved price 400",
        "Check compliance for supplier Zeta with trust score 0.95, terms net-30, unit price 50, max approved price 60",
        "Check compliance for supplier Eta with trust score 0.65, terms wire-transfer, unit price 200, max approved price 250",
        "Check compliance for supplier Theta with trust score 0.85, terms net-60, unit price 320, max approved price 300",
        "Check compliance for supplier Iota with trust score 0.5, terms net-15, unit price 90, max approved price 120",
        "Check compliance for supplier Kappa with trust score 0.7, terms prepaid, unit price 400, max approved price 350",
    ]

    analytics_requests = [
        "What is the average cost per category?",
        "What are the top suppliers by trust?",
        "How many suppliers are there by country?",
        "What is the average cost per category?",
        "What are the top suppliers by trust?",
        "How many suppliers are there by country?",
        "What is the average cost per category?",
        "What are the top suppliers by trust?",
        "How many suppliers are there by country?",
        "What is the average cost per category?",
    ]

    all_test_cases = (
        [("http://localhost:8202", r) for r in procurement_requests]
        + [("http://localhost:8203", r) for r in logistics_requests]
        + [("http://localhost:8204", r) for r in compliance_requests]
        + [("http://localhost:8205", r) for r in analytics_requests]
    )

    for url, text in all_test_cases:
        print(f"\n=== {url} : {text[:60]} ===")
        try:
            result = await send_a2a_task(url, text)
            print(result)
        except Exception as e:
            print(f"FAILED: {e}")


if __name__ == "__main__":
    asyncio.run(main())