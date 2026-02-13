import asyncio
import base64
import json
import os
import queue
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv, set_key
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.engine.workflow_engine import WorkflowEngine, WorkflowState
from src.engine.report_generator import WorkflowReportGenerator
from src.engine.docx_report import generate_docx_report


class WebSocketLogHandler:
    def __init__(self):
        self.connections: list[WebSocket] = []
        self.log_queue: queue.Queue = queue.Queue()
        self.screencast_enabled = True

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.connections[:]:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

    async def broadcast_frame(self, frame_data: str):
        message = {"type": "frame", "data": frame_data}
        for connection in self.connections[:]:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


log_handler = WebSocketLogHandler()
workflow_task: asyncio.Task | None = None
workflow_running = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Xero Workflow Automation", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


def get_available_workflows() -> list[dict]:
    workflows_dir = Path("workflows")
    workflows = []
    for f in sorted(workflows_dir.glob("*.yaml")):
        workflows.append({
            "name": f.stem,
            "path": str(f),
            "display_name": f.stem.replace("_", " ").title()
        })
    return workflows


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html") as f:
        return f.read()


@app.get("/api/workflows")
async def list_workflows():
    return get_available_workflows()


@app.get("/api/downloads")
async def list_downloads(subpath: str = ""):
    downloads_dir = Path("downloads")
    target_dir = downloads_dir / subpath if subpath else downloads_dir

    if not target_dir.exists():
        return {"path": str(downloads_dir.absolute()), "subpath": subpath, "items": [], "error": "Directory not found"}

    items = []

    for item in sorted(target_dir.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        rel_path = item.relative_to(downloads_dir)
        if item.is_dir():
            file_count = sum(1 for _ in item.rglob("*") if _.is_file())
            items.append({
                "name": item.name,
                "path": str(rel_path),
                "type": "folder",
                "file_count": file_count
            })
        else:
            items.append({
                "name": item.name,
                "path": str(rel_path),
                "type": "file",
                "size": item.stat().st_size,
                "modified": item.stat().st_mtime
            })

    return {
        "path": str(downloads_dir.absolute()),
        "subpath": subpath,
        "parent": str(Path(subpath).parent) if subpath and subpath != "." else None,
        "items": items
    }


@app.get("/api/downloads/view/{file_path:path}")
async def view_file(file_path: str):
    from fastapi.responses import FileResponse
    downloads_dir = Path("downloads")
    full_path = downloads_dir / file_path

    if not full_path.exists() or not full_path.is_file():
        return {"error": "File not found"}

    return FileResponse(full_path, filename=full_path.name)


@app.delete("/api/downloads/{file_path:path}")
async def delete_file(file_path: str):
    import shutil
    downloads_dir = Path("downloads")
    full_path = downloads_dir / file_path

    if not full_path.exists():
        return {"error": "File not found", "success": False}

    try:
        if full_path.is_dir():
            shutil.rmtree(full_path)
        else:
            full_path.unlink()
        return {"success": True, "deleted": file_path}
    except Exception as e:
        return {"error": str(e), "success": False}


class CredentialsInput(BaseModel):
    email: str
    password: str


@app.get("/api/credentials/check")
async def check_credentials():
    email = os.getenv("XERO_EMAIL", "").strip()
    password = os.getenv("XERO_PASSWORD", "").strip()
    has_credentials = bool(email and password)
    return {
        "configured": has_credentials,
        "email": email if has_credentials else None
    }


@app.post("/api/credentials/save")
async def save_credentials(creds: CredentialsInput):
    os.environ["XERO_EMAIL"] = creds.email
    os.environ["XERO_PASSWORD"] = creds.password

    try:
        env_path = Path(".env")
        if not env_path.exists():
            env_path.touch()
        set_key(str(env_path), "XERO_EMAIL", creds.email)
        set_key(str(env_path), "XERO_PASSWORD", creds.password)
    except OSError:
        pass

    return {"success": True, "email": creds.email}


@app.get("/api/status")
async def get_status():
    global workflow_running
    return {"running": workflow_running}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await log_handler.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("action") == "start":
                workflow_names = msg.get("workflows", [])
                clients = msg.get("clients", [])
                reports = msg.get("reports", [])
                await start_workflow(workflow_names, clients, reports)
            elif msg.get("action") == "stop":
                await stop_workflow()

    except WebSocketDisconnect:
        log_handler.disconnect(websocket)


async def send_log(level: str, message: str, **kwargs):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        "type": "log",
        "timestamp": timestamp,
        "level": level,
        "message": message,
        "data": kwargs
    }
    await log_handler.broadcast(log_entry)


async def send_status(status: str, **kwargs):
    await log_handler.broadcast({
        "type": "status",
        "status": status,
        **kwargs
    })


async def send_variables(variables: dict):
    await log_handler.broadcast({
        "type": "variables",
        "variables": variables
    })


async def run_workflow_chain(workflow_names: list[str], clients: list[str] = None, reports: list[str] = None):
    global workflow_running
    workflow_running = True

    from playwright.async_api import async_playwright

    master_report = WorkflowReportGenerator()
    master_report.start_workflow("Workflow Chain", ", ".join(clients) if clients else "All")

    await send_status("running")

    if clients:
        await send_log("info", f"Selected clients: {', '.join(clients)}")
    await send_log("info", f"Starting workflow chain: {', '.join(workflow_names)}")

    report_workflows = {
        'trial_balance_report', 'profit_and_loss', 'aged_receivables_detail',
        'aged_payables_detail', 'account_transactions', 'receivable_invoice_detail',
        'payable_invoice_detail'
    }
    navigate_workflow = Path("workflows/navigate_to_reports.yaml")

    workflow_paths = []
    for idx, name in enumerate(workflow_names):
        yaml_path = Path(f"workflows/{name}.yaml")
        if yaml_path.exists():
            if name in report_workflows and idx > 0 and navigate_workflow.exists():
                prev_name = workflow_names[idx - 1] if idx > 0 else None
                if prev_name in report_workflows:
                    workflow_paths.append(navigate_workflow)
            workflow_paths.append(yaml_path)
        else:
            await send_log("error", f"Workflow not found: {name}")

    if not workflow_paths:
        await send_log("error", "No valid workflows to run")
        await send_status("idle")
        workflow_running = False
        return

    playwright = None
    context = None
    cdp_session = None

    async def handle_screencast_frame(params):
        if log_handler.screencast_enabled and workflow_running:
            frame_data = params.get("data", "")
            session_id = params.get("sessionId", 0)
            await log_handler.broadcast_frame(frame_data)
            if cdp_session:
                try:
                    await cdp_session.send("Page.screencastFrameAck", {"sessionId": session_id})
                except Exception:
                    pass

    try:
        playwright = await async_playwright().start()

        downloads_dir = Path("downloads").absolute()
        downloads_dir.mkdir(exist_ok=True)

        context = await playwright.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            headless=False,
            viewport={"width": 1280, "height": 800},
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            cdp_session = await page.context.new_cdp_session(page)
            await cdp_session.send("Browser.setDownloadBehavior", {
                "behavior": "allow",
                "eventsEnabled": True
            })
            cdp_session.on("Page.screencastFrame", lambda params: asyncio.create_task(handle_screencast_frame(params)))
            await cdp_session.send("Page.startScreencast", {
                "format": "jpeg",
                "quality": 60,
                "maxWidth": 1280,
                "maxHeight": 800,
                "everyNthFrame": 2
            })
            await send_log("info", "Browser streaming started")
        except Exception as e:
            await send_log("warning", f"Screencast/CDP setup: {str(e)}")

        clients_to_process = clients if clients else [None]

        for client_idx, client_name in enumerate(clients_to_process):
            if not workflow_running:
                await send_log("warning", "Workflow stopped by user")
                break

            if client_name:
                await send_log("info", f"Processing client {client_idx + 1}/{len(clients_to_process)}: {client_name}")

            for i, workflow_path in enumerate(workflow_paths):
                if not workflow_running:
                    await send_log("warning", "Workflow stopped by user")
                    break

                current_url = page.url.lower()
                workflow_name = workflow_path.stem

                if workflow_name == "login_and_redirect" and "reporting.xero.com" in current_url:
                    await send_log("info", f"Already on reporting page, skipping login workflow")
                    continue

                if workflow_name == "navigate_to_reports" and "reporting.xero.com" in current_url and "/home" in current_url:
                    await send_log("info", f"Already on reports page, skipping navigation")
                    continue

                await send_log("info", f"Running workflow {i+1}/{len(workflow_paths)}: {workflow_name}")
                await send_status("running", current_workflow=workflow_name, progress=i, total=len(workflow_paths), client=client_name)

                engine = WorkflowEngine(workflow_path)
                engine.log_callback = send_log
                engine.variable_callback = send_variables

                if client_name:
                    engine.state.variables["selected_client"] = client_name

                state = await engine.run(context=context, page=page)
                master_report.events.extend(engine.report.events)

                if state.variables:
                    vars_summary = {k: v for k, v in state.variables.items() if k in ['company_name', 'downloaded_file', 'report_end_date']}
                    if vars_summary:
                        await send_log("info", "Variables captured", **vars_summary)

                has_fatal_error = any(e.get('fatal') for e in state.errors)

                if has_fatal_error:
                    for error in state.errors:
                        await send_log("error", f"Error in {error.get('step')}: {error.get('error')}")

                    if workflow_name == "login_and_redirect":
                        await send_log("error", "Login/client selection failed - stopping workflow chain")
                        break
                else:
                    await send_log("success", f"Completed: {workflow_path.stem}",
                                  completed_steps=len(state.completed_steps),
                                  variables=state.variables)

                if state.errors and not has_fatal_error:
                    for error in state.errors:
                        await send_log("warning", f"Non-fatal error in {error.get('step')}: {error.get('error')}")

            if workflow_running and client_name:
                await send_log("success", f"All reports completed for: {client_name}")

        # All clients and workflows completed successfully
        if workflow_running:
            await send_status("completed")
            await send_log("success", "All workflows completed successfully")

            # Generate workflow execution report
            master_report.end_workflow("completed", {})
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = f"downloads/workflow_report_{timestamp}.html"
            master_report.generate_html_report(report_path)
            await send_log("info", f"📊 Execution report generated: {report_path}")
            docx_path = f"downloads/execution_summary_{timestamp}.docx"
            generate_docx_report(master_report.events, docx_path)
            await send_log("info", f"📄 Execution summary generated: {docx_path}")

    except asyncio.CancelledError:
        await send_log("warning", "Workflow cancelled")
        master_report.end_workflow("cancelled", {})
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"downloads/workflow_report_{timestamp}.html"
        master_report.generate_html_report(report_path)
        await send_log("info", f"📊 Execution report generated: {report_path}")
        docx_path = f"downloads/execution_summary_{timestamp}.docx"
        generate_docx_report(master_report.events, docx_path)
        await send_log("info", f"📄 Execution summary generated: {docx_path}")
    except Exception as e:
        await send_log("error", f"Workflow failed: {str(e)}")
        master_report.end_workflow("failed", {})
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"downloads/workflow_report_{timestamp}.html"
        master_report.generate_html_report(report_path)
        await send_log("info", f"📊 Execution report generated: {report_path}")
        docx_path = f"downloads/execution_summary_{timestamp}.docx"
        generate_docx_report(master_report.events, docx_path)
        await send_log("info", f"📄 Execution summary generated: {docx_path}")
    finally:
        if cdp_session:
            try:
                await cdp_session.send("Page.stopScreencast")
            except Exception:
                pass
        if context:
            await context.close()
        if playwright:
            await playwright.stop()
        workflow_running = False
        await send_status("idle")
        await send_log("info", "Workflow chain finished")


async def start_workflow(workflow_names: list[str], clients: list[str] = None, reports: list[str] = None):
    global workflow_task, workflow_running

    if workflow_running:
        await send_log("warning", "Workflow already running")
        return

    workflow_task = asyncio.create_task(run_workflow_chain(workflow_names, clients or [], reports or []))


async def stop_workflow():
    global workflow_task, workflow_running

    if workflow_task and workflow_running:
        workflow_running = False
        workflow_task.cancel()
        await send_log("warning", "Stopping workflow...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
