import json
import uuid
import time
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "eval"))
from logger import log_execution

from fastapi import FastAPI
import uvicorn

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater, InMemoryTaskStore
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes, add_a2a_routes_to_fastapi
from a2a.types import (
    AgentCard, AgentSkill, AgentCapabilities, AgentInterface,
    Message, Part, Role, Task, TaskStatus, TaskState
)

from graph import build_procurement_graph

procurement_graph = build_procurement_graph()


class ProcurementAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        start_time = time.time()

        if context.current_task is None:
            initial_task = Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
            )
            await event_queue.enqueue_event(initial_task)

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()

        user_text = context.get_user_input()

        initial_state = {
            "raw_request": user_text,
            "parsed_request": None,
            "product": None,
            "candidates": [],
            "negotiation_rounds": [],
            "decision": None,
            "error": None,
        }

        try:
            result = procurement_graph.invoke(initial_state)
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            log_execution("procurement", success=False, latency_ms=latency_ms, error=str(e))
            fail_msg = Message(
                message_id=str(uuid.uuid4()),
                context_id=context.context_id,
                role=Role.ROLE_AGENT,
                parts=[Part(text=f"Internal error: {e}")],
            )
            await updater.failed(message=fail_msg)
            return

        if result.get("error"):
            latency_ms = (time.time() - start_time) * 1000
            log_execution("procurement", success=False, latency_ms=latency_ms, error=result["error"])
            fail_msg = Message(
                message_id=str(uuid.uuid4()),
                context_id=context.context_id,
                role=Role.ROLE_AGENT,
                parts=[Part(text=result["error"])],
            )
            await updater.failed(message=fail_msg)
            return

        latency_ms = (time.time() - start_time) * 1000
        log_execution("procurement", success=True, latency_ms=latency_ms, metric_value=result["decision"].final_price)

        decision_json = json.dumps(result["decision"].model_dump())
        await updater.add_artifact([Part(text=decision_json)])
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


agent_card = AgentCard(
    name="procurement-agent",
    description="Sources products from suppliers, negotiates pricing, and returns a procurement decision.",
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=False),
    supported_interfaces=[
        AgentInterface(url="http://localhost:8202", protocol_binding="JSONRPC", protocol_version="1.0")
    ],
    skills=[
        AgentSkill(
            id="procure_product",
            name="Procure Product",
            description="Sources a product from the best available supplier and negotiates pricing/terms.",
            tags=["procurement", "supply-chain"],
            examples=["Source 500 units of Conference electronics unit"],
        )
    ],
)

request_handler = DefaultRequestHandler(
    agent_executor=ProcurementAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)

app = FastAPI(title="Procurement A2A Agent")
add_a2a_routes_to_fastapi(
    app,
    agent_card_routes=create_agent_card_routes(agent_card),
    jsonrpc_routes=create_jsonrpc_routes(request_handler, rpc_url="/"),
)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8202)