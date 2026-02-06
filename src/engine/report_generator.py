import json
from datetime import datetime
from pathlib import Path
from typing import Any


class WorkflowReportGenerator:
    def __init__(self):
        self.events: list[dict] = []
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.workflow_name: str = ""
        self.client_name: str = ""

    def start_workflow(self, workflow_name: str, client_name: str = ""):
        self.workflow_name = workflow_name
        self.client_name = client_name
        self.start_time = datetime.now()
        self.events.append({
            "type": "workflow_start",
            "workflow": workflow_name,
            "client": client_name,
            "timestamp": self.start_time.isoformat(),
            "time": self.start_time.strftime("%H:%M:%S")
        })

    def log_step(self, step_id: str, action: str, description: str, status: str, details: dict = None):
        self.events.append({
            "type": "step",
            "step_id": step_id,
            "action": action,
            "description": description,
            "status": status,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
            "time": datetime.now().strftime("%H:%M:%S")
        })

    def log_filter(self, filter_name: str, value: str):
        self.events.append({
            "type": "filter",
            "filter_name": filter_name,
            "value": value,
            "timestamp": datetime.now().isoformat(),
            "time": datetime.now().strftime("%H:%M:%S")
        })

    def log_navigation(self, from_url: str, to_url: str):
        self.events.append({
            "type": "navigation",
            "from": from_url,
            "to": to_url,
            "timestamp": datetime.now().isoformat(),
            "time": datetime.now().strftime("%H:%M:%S")
        })

    def log_download(self, filename: str, path: str):
        self.events.append({
            "type": "download",
            "filename": filename,
            "path": path,
            "timestamp": datetime.now().isoformat(),
            "time": datetime.now().strftime("%H:%M:%S")
        })

    def log_skip(self, reason: str, context: str = ""):
        self.events.append({
            "type": "skip",
            "reason": reason,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "time": datetime.now().strftime("%H:%M:%S")
        })

    def log_validation(self, passed: list, errors: list):
        self.events.append({
            "type": "validation",
            "passed": passed,
            "errors": errors,
            "timestamp": datetime.now().isoformat(),
            "time": datetime.now().strftime("%H:%M:%S")
        })

    def log_error(self, step_id: str, error: str, fatal: bool = False):
        self.events.append({
            "type": "error",
            "step_id": step_id,
            "error": error,
            "fatal": fatal,
            "timestamp": datetime.now().isoformat(),
            "time": datetime.now().strftime("%H:%M:%S")
        })

    def end_workflow(self, status: str, variables: dict = None):
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds() if self.start_time else 0
        self.events.append({
            "type": "workflow_end",
            "status": status,
            "variables": variables or {},
            "duration_seconds": duration,
            "timestamp": self.end_time.isoformat(),
            "time": self.end_time.strftime("%H:%M:%S")
        })

    def generate_html_report(self, output_path: str = None) -> str:
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"downloads/workflow_report_{timestamp}.html"

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        html = self._build_html()
        Path(output_path).write_text(html)
        return output_path

    def _build_html(self) -> str:
        events_json = json.dumps(self.events, indent=2)

        workflow_start = next((e for e in self.events if e["type"] == "workflow_start"), {})
        workflow_end = next((e for e in self.events if e["type"] == "workflow_end"), {})

        steps = [e for e in self.events if e["type"] == "step"]
        filters = [e for e in self.events if e["type"] == "filter"]
        downloads = [e for e in self.events if e["type"] == "download"]
        errors = [e for e in self.events if e["type"] == "error"]
        skips = [e for e in self.events if e["type"] == "skip"]
        validations = [e for e in self.events if e["type"] == "validation"]

        success_count = len([s for s in steps if s["status"] == "success"])
        fail_count = len([s for s in steps if s["status"] == "error"])
        skip_count = len(skips)

        duration = workflow_end.get("duration_seconds", 0)
        duration_str = f"{int(duration // 60)}m {int(duration % 60)}s" if duration >= 60 else f"{duration:.1f}s"

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Workflow Report - {workflow_start.get("workflow", "Unknown")}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
            padding: 2rem;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}

        .header {{
            background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
            border-radius: 16px;
            padding: 2rem;
            margin-bottom: 2rem;
            border: 1px solid #475569;
        }}
        .header h1 {{ font-size: 1.75rem; margin-bottom: 0.5rem; color: #f8fafc; }}
        .header .subtitle {{ color: #94a3b8; font-size: 0.95rem; }}

        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: #1e293b;
            border-radius: 12px;
            padding: 1.25rem;
            text-align: center;
            border: 1px solid #334155;
        }}
        .stat-card .value {{ font-size: 2rem; font-weight: 700; }}
        .stat-card .label {{ color: #94a3b8; font-size: 0.85rem; margin-top: 0.25rem; }}
        .stat-card.success .value {{ color: #4ade80; }}
        .stat-card.error .value {{ color: #f87171; }}
        .stat-card.skip .value {{ color: #fbbf24; }}
        .stat-card.info .value {{ color: #60a5fa; }}

        .section {{
            background: #1e293b;
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid #334155;
        }}
        .section h2 {{
            font-size: 1.1rem;
            margin-bottom: 1rem;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .flow-container {{
            position: relative;
            padding: 1rem 0;
        }}
        .flow-line {{
            position: absolute;
            left: 24px;
            top: 0;
            bottom: 0;
            width: 2px;
            background: linear-gradient(to bottom, #3b82f6, #8b5cf6, #10b981);
        }}

        .flow-item {{
            position: relative;
            padding-left: 60px;
            padding-bottom: 1.5rem;
        }}
        .flow-item:last-child {{ padding-bottom: 0; }}

        .flow-node {{
            position: absolute;
            left: 12px;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            z-index: 1;
        }}
        .flow-node.success {{ background: #166534; border: 2px solid #4ade80; }}
        .flow-node.error {{ background: #991b1b; border: 2px solid #f87171; }}
        .flow-node.skip {{ background: #92400e; border: 2px solid #fbbf24; }}
        .flow-node.filter {{ background: #1e40af; border: 2px solid #60a5fa; }}
        .flow-node.download {{ background: #065f46; border: 2px solid #34d399; }}
        .flow-node.validation {{ background: #5b21b6; border: 2px solid #a78bfa; }}
        .flow-node.nav {{ background: #374151; border: 2px solid #9ca3af; }}

        .flow-content {{
            background: #0f172a;
            border-radius: 8px;
            padding: 1rem;
            border: 1px solid #334155;
        }}
        .flow-content .time {{
            font-size: 0.75rem;
            color: #64748b;
            margin-bottom: 0.25rem;
        }}
        .flow-content .title {{
            font-weight: 600;
            color: #f8fafc;
            margin-bottom: 0.25rem;
        }}
        .flow-content .description {{
            font-size: 0.875rem;
            color: #94a3b8;
        }}
        .flow-content .details {{
            margin-top: 0.5rem;
            padding-top: 0.5rem;
            border-top: 1px solid #334155;
            font-size: 0.8rem;
            color: #64748b;
        }}
        .flow-content .tag {{
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .tag.success {{ background: #166534; color: #4ade80; }}
        .tag.error {{ background: #991b1b; color: #f87171; }}
        .tag.skip {{ background: #92400e; color: #fbbf24; }}
        .tag.filter {{ background: #1e40af; color: #60a5fa; }}
        .tag.download {{ background: #065f46; color: #34d399; }}

        .filters-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1rem;
        }}
        .filter-card {{
            background: #0f172a;
            border-radius: 8px;
            padding: 1rem;
            border: 1px solid #334155;
        }}
        .filter-card .name {{ color: #94a3b8; font-size: 0.85rem; }}
        .filter-card .value {{ color: #60a5fa; font-weight: 600; margin-top: 0.25rem; }}

        .downloads-list {{
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }}
        .download-item {{
            display: flex;
            align-items: center;
            gap: 1rem;
            background: #0f172a;
            border-radius: 8px;
            padding: 1rem;
            border: 1px solid #334155;
        }}
        .download-item .icon {{
            width: 40px;
            height: 40px;
            background: #065f46;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #34d399;
        }}
        .download-item .info .filename {{ font-weight: 600; color: #f8fafc; }}
        .download-item .info .path {{ font-size: 0.8rem; color: #64748b; margin-top: 0.25rem; }}

        .mermaid-container {{
            background: #0f172a;
            border-radius: 8px;
            padding: 2rem;
            overflow-x: auto;
        }}

        .variables-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 0.75rem;
        }}
        .var-item {{
            background: #0f172a;
            border-radius: 6px;
            padding: 0.75rem;
            border: 1px solid #334155;
        }}
        .var-item .key {{ color: #94a3b8; font-size: 0.8rem; }}
        .var-item .val {{ color: #f8fafc; font-weight: 500; word-break: break-all; }}

        .summary-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 0.5rem;
        }}
        .summary-table th {{
            background: #334155;
            color: #f8fafc;
            padding: 0.75rem 1rem;
            text-align: left;
            font-weight: 600;
            font-size: 0.85rem;
        }}
        .summary-table td {{
            padding: 0.75rem 1rem;
            border-bottom: 1px solid #334155;
            font-size: 0.9rem;
        }}
        .summary-table tr:hover td {{
            background: #1e293b;
        }}
        .summary-table .report-name {{
            color: #f8fafc;
            font-weight: 500;
        }}
        .summary-table .filter-value {{
            color: #60a5fa;
        }}
        .summary-table .status-yes {{
            color: #4ade80;
            font-weight: 600;
        }}
        .summary-table .status-no {{
            color: #f87171;
            font-weight: 600;
        }}
        .summary-table .status-skip {{
            color: #fbbf24;
            font-weight: 600;
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Workflow Execution Report</h1>
            <div class="subtitle">
                {workflow_start.get("workflow", "Unknown Workflow")}
                {f' • Client: {workflow_start.get("client")}' if workflow_start.get("client") else ''}
                • {workflow_start.get("time", "")} - {workflow_end.get("time", "")}
            </div>
        </div>

        <div class="stats">
            <div class="stat-card success">
                <div class="value">{success_count}</div>
                <div class="label">Steps Completed</div>
            </div>
            <div class="stat-card error">
                <div class="value">{fail_count}</div>
                <div class="label">Errors</div>
            </div>
            <div class="stat-card skip">
                <div class="value">{skip_count}</div>
                <div class="label">Skipped</div>
            </div>
            <div class="stat-card info">
                <div class="value">{len(downloads)}</div>
                <div class="label">Downloads</div>
            </div>
            <div class="stat-card info">
                <div class="value">{len(filters)}</div>
                <div class="label">Filters Set</div>
            </div>
            <div class="stat-card info">
                <div class="value">{duration_str}</div>
                <div class="label">Duration</div>
            </div>
        </div>

        {self._build_report_summary_section()}

        {self._build_filters_section(filters)}

        {self._build_mermaid_diagram()}

        {self._build_flow_section()}

        {self._build_downloads_section(downloads)}

        {self._build_variables_section(workflow_end.get("variables", {}))}
    </div>

    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'dark',
            themeVariables: {{
                primaryColor: '#3b82f6',
                primaryTextColor: '#f8fafc',
                primaryBorderColor: '#60a5fa',
                lineColor: '#64748b',
                secondaryColor: '#1e293b',
                tertiaryColor: '#0f172a'
            }}
        }});
    </script>
</body>
</html>'''

    def _build_report_summary_section(self) -> str:
        report_names = {
            'trial_balance_report': 'Trial Balance',
            'profit_and_loss': 'Profit & Loss',
            'aged_receivables_detail': 'Aged Receivables',
            'aged_payables_detail': 'Aged Payables',
            'account_transactions': 'Account Transactions',
            'receivable_invoice_detail': 'Receivable Invoice Detail',
            'payable_invoice_detail': 'Payable Invoice Detail',
            'vat_returns_export': 'VAT Returns',
            'login_and_redirect': 'Login',
            'navigate_to_reports': 'Navigate to Reports',
            'get_financial_year_end': 'Get Financial Year',
        }

        friendly_filter_names = {
            'financial_year_start_date': 'Start Date',
            'financial_year_end_date': 'End Date',
            'report_end_date': 'End Date',
            'selected_client': 'Client',
            'company_name': 'Company',
            'vat_return_period': 'VAT Period',
            'vat_return_start_date': 'VAT Start',
            'vat_return_end_date': 'VAT End',
        }

        reports = []
        current_report = None
        current_filters = {}
        current_downloaded = False
        current_skipped = False

        for event in self.events:
            if event["type"] == "workflow_start":
                if current_report:
                    reports.append({
                        "name": current_report,
                        "filters": current_filters.copy(),
                        "downloaded": current_downloaded,
                        "skipped": current_skipped
                    })
                workflow_name = event.get("workflow", "")
                current_report = report_names.get(workflow_name, workflow_name)
                current_filters = {}
                current_downloaded = False
                current_skipped = False

            elif event["type"] == "filter":
                filter_name = event.get("filter_name", "")
                filter_value = event.get("value", "")
                friendly_name = friendly_filter_names.get(filter_name, filter_name.replace('_', ' ').title())
                current_filters[friendly_name] = filter_value

            elif event["type"] == "download":
                current_downloaded = True

            elif event["type"] == "skip":
                current_skipped = True

        if current_report:
            reports.append({
                "name": current_report,
                "filters": current_filters.copy(),
                "downloaded": current_downloaded,
                "skipped": current_skipped
            })

        report_workflows = ['Trial Balance', 'Profit & Loss', 'Aged Receivables', 'Aged Payables',
                           'Account Transactions', 'Receivable Invoice Detail', 'Payable Invoice Detail', 'VAT Returns']
        reports = [r for r in reports if r["name"] in report_workflows]

        if not reports:
            return ""

        rows = ""
        for r in reports:
            if r["filters"]:
                filter_items = []
                for k, v in r["filters"].items():
                    if k not in ['Client', 'Company']:
                        filter_items.append(f"<b>{k}:</b> {v}")
                filter_str = "<br>".join(filter_items) if filter_items else "-"
            else:
                filter_str = "-"

            if r["skipped"]:
                status = '<span class="status-skip">SKIPPED</span>'
            elif r["downloaded"]:
                status = '<span class="status-yes">Y</span>'
            else:
                status = '<span class="status-no">N</span>'

            rows += f'''
            <tr>
                <td class="report-name">{r["name"]}</td>
                <td class="filter-value">{filter_str}</td>
                <td style="text-align: center;">{status}</td>
            </tr>'''

        return f'''
        <div class="section">
            <h2>📋 Report Summary</h2>
            <table class="summary-table">
                <thead>
                    <tr>
                        <th style="width: 200px;">Report Name</th>
                        <th>Filters Selected</th>
                        <th style="text-align: center; width: 100px;">Downloaded</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>'''

    def _build_filters_section(self, filters: list) -> str:
        if not filters:
            return ""

        cards = ""
        for f in filters:
            cards += f'''
            <div class="filter-card">
                <div class="name">{f["filter_name"]}</div>
                <div class="value">{f["value"]}</div>
            </div>'''

        return f'''
        <div class="section">
            <h2>🎛️ Filters Applied</h2>
            <div class="filters-grid">{cards}</div>
        </div>'''

    def _build_mermaid_diagram(self) -> str:
        steps = [e for e in self.events if e["type"] in ["step", "workflow_start", "workflow_end", "skip", "download"]]

        if len(steps) < 2:
            return ""

        nodes = []
        connections = []
        prev_id = None

        for i, event in enumerate(steps):
            node_id = f"N{i}"

            if event["type"] == "workflow_start":
                label = f"Start: {event.get('workflow', 'Workflow')}"
                nodes.append(f'{node_id}["{label}"]')
                nodes.append(f"style {node_id} fill:#1e40af,stroke:#60a5fa")
            elif event["type"] == "workflow_end":
                status = event.get("status", "complete")
                label = f"End: {status.title()}"
                nodes.append(f'{node_id}["{label}"]')
                color = "#166534" if status == "completed" else "#991b1b"
                stroke = "#4ade80" if status == "completed" else "#f87171"
                nodes.append(f"style {node_id} fill:{color},stroke:{stroke}")
            elif event["type"] == "skip":
                label = event.get("reason", "Skipped")[:30]
                nodes.append(f'{node_id}[/"⏭️ {label}"/]')
                nodes.append(f"style {node_id} fill:#92400e,stroke:#fbbf24")
            elif event["type"] == "download":
                label = event.get("filename", "Download")[:25]
                nodes.append(f'{node_id}[("📥 {label}")]')
                nodes.append(f"style {node_id} fill:#065f46,stroke:#34d399")
            else:
                status = event.get("status", "success")
                desc = event.get("description", event.get("step_id", "Step"))[:35]
                if status == "success":
                    nodes.append(f'{node_id}["{desc}"]')
                    nodes.append(f"style {node_id} fill:#166534,stroke:#4ade80")
                else:
                    nodes.append(f'{node_id}["{desc}"]')
                    nodes.append(f"style {node_id} fill:#991b1b,stroke:#f87171")

            if prev_id is not None:
                connections.append(f"{prev_id} --> {node_id}")
            prev_id = node_id

        diagram = "graph TD\n    " + "\n    ".join(nodes + connections)

        return f'''
        <div class="section">
            <h2>🔀 Workflow Flow Diagram</h2>
            <div class="mermaid-container">
                <pre class="mermaid">{diagram}</pre>
            </div>
        </div>'''

    def _build_flow_section(self) -> str:
        items = ""
        for event in self.events:
            if event["type"] == "workflow_start":
                items += self._flow_item("success", "▶️", event["time"],
                    f"Started: {event.get('workflow', 'Workflow')}",
                    f"Client: {event.get('client', 'N/A')}")
            elif event["type"] == "workflow_end":
                status_class = "success" if event.get("status") == "completed" else "error"
                items += self._flow_item(status_class, "⏹️", event["time"],
                    f"Finished: {event.get('status', 'Unknown').title()}",
                    f"Duration: {event.get('duration_seconds', 0):.1f}s")
            elif event["type"] == "step":
                icon = "✓" if event["status"] == "success" else "✗"
                items += self._flow_item(event["status"], icon, event["time"],
                    event.get("description", event.get("step_id", "Step")),
                    f"Action: {event.get('action', 'N/A')}", event["status"])
            elif event["type"] == "filter":
                items += self._flow_item("filter", "🎛️", event["time"],
                    f"Filter: {event['filter_name']}", event["value"])
            elif event["type"] == "download":
                items += self._flow_item("download", "📥", event["time"],
                    f"Downloaded: {event['filename']}", event.get("path", ""))
            elif event["type"] == "skip":
                items += self._flow_item("skip", "⏭️", event["time"],
                    f"Skipped", event["reason"])
            elif event["type"] == "validation":
                passed = len(event.get("passed", []))
                errors = len(event.get("errors", []))
                status = "success" if errors == 0 else "error"
                items += self._flow_item(status, "✔", event["time"],
                    f"Validation: {passed} passed, {errors} issues",
                    ", ".join(event.get("errors", [])[:3]))
            elif event["type"] == "error":
                items += self._flow_item("error", "❌", event["time"],
                    f"Error in {event.get('step_id', 'Unknown')}", event["error"])

        return f'''
        <div class="section">
            <h2>📋 Execution Timeline</h2>
            <div class="flow-container">
                <div class="flow-line"></div>
                {items}
            </div>
        </div>'''

    def _flow_item(self, node_class: str, icon: str, time: str, title: str, description: str, tag: str = None) -> str:
        tag_html = f'<span class="tag {tag}">{tag}</span>' if tag else ""
        return f'''
        <div class="flow-item">
            <div class="flow-node {node_class}">{icon}</div>
            <div class="flow-content">
                <div class="time">{time}</div>
                <div class="title">{title} {tag_html}</div>
                <div class="description">{description}</div>
            </div>
        </div>'''

    def _build_downloads_section(self, downloads: list) -> str:
        if not downloads:
            return ""

        items = ""
        for d in downloads:
            items += f'''
            <div class="download-item">
                <div class="icon">📄</div>
                <div class="info">
                    <div class="filename">{d["filename"]}</div>
                    <div class="path">{d["path"]}</div>
                </div>
            </div>'''

        return f'''
        <div class="section">
            <h2>📥 Downloaded Files</h2>
            <div class="downloads-list">{items}</div>
        </div>'''

    def _build_variables_section(self, variables: dict) -> str:
        if not variables:
            return ""

        items = ""
        for k, v in variables.items():
            val = str(v)[:100] + "..." if len(str(v)) > 100 else str(v)
            items += f'''
            <div class="var-item">
                <div class="key">{k}</div>
                <div class="val">{val}</div>
            </div>'''

        return f'''
        <div class="section">
            <h2>📦 Captured Variables</h2>
            <div class="variables-grid">{items}</div>
        </div>'''
