from __future__ import annotations

import json
import math
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import nbformat as nbf
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "synthetic_deals.csv"


def ensure_dirs() -> None:
    for rel in ["docs", "bpmn", "dashboard", "risk", "economics", "presentation", "notebooks", "data/processed"]:
        (ROOT / rel).mkdir(parents=True, exist_ok=True)


def load_deals() -> pd.DataFrame:
    time_cols = [
        "request_time",
        "quote_time",
        "client_accept_time",
        "limit_check_time",
        "trade_capture_time",
        "confirmation_time",
        "settlement_time",
    ]
    return pd.read_csv(DATA_PATH, parse_dates=time_cols)


def compute_metrics(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    stages = [
        ("request_to_quote", "request_time", "quote_time"),
        ("quote_to_accept", "quote_time", "client_accept_time"),
        ("accept_to_limit_check", "client_accept_time", "limit_check_time"),
        ("limit_check_to_capture", "limit_check_time", "trade_capture_time"),
        ("capture_to_confirmation", "trade_capture_time", "confirmation_time"),
        ("confirmation_to_settlement", "confirmation_time", "settlement_time"),
    ]
    for name, start, end in stages:
        df[name + "_minutes"] = (df[end] - df[start]).dt.total_seconds() / 60
    df["total_minutes"] = (df["settlement_time"] - df["request_time"]).dt.total_seconds() / 60
    df["first_pass"] = (df["deal_status"] == "settled") & (df["rework_count"] == 0)
    df["stp"] = ~df["manual_processing_flag"]
    df["processing_cost_usd"] = 12 + df["manual_steps_count"] * 8 + df["rework_count"] * 18

    summary = {
        "deal_count": len(df),
        "avg_total_minutes": df["total_minutes"].mean(),
        "median_total_minutes": df["total_minutes"].median(),
        "sla_met_rate": 1 - df["sla_breach"].mean(),
        "sla_breach_rate": df["sla_breach"].mean(),
        "stp_rate": df["stp"].mean(),
        "manual_processing_rate": df["manual_processing_flag"].mean(),
        "avg_rework_count": df["rework_count"].mean(),
        "registration_error_rate": (df["exception_type"] == "manual_reentry_error").mean(),
        "settlement_issue_rate": (df["exception_type"] == "settlement_fail").mean(),
        "avg_manual_steps": df["manual_steps_count"].mean(),
        "avg_processing_cost_usd": df["processing_cost_usd"].mean(),
        "first_pass_yield": df["first_pass"].mean(),
    }

    stage_rows = []
    for name, _, _ in stages:
        s = df[name + "_minutes"]
        stage_rows.append(
            {
                "stage": name,
                "avg_minutes": s.mean(),
                "median_minutes": s.median(),
                "p90_minutes": s.quantile(0.90),
                "share_of_total_wait": s.sum() / df["total_minutes"].sum(),
            }
        )
    stage_metrics = pd.DataFrame(stage_rows)

    exception_metrics = (
        df.groupby("exception_type")
        .agg(
            deal_count=("deal_id", "count"),
            sla_breach_rate=("sla_breach", "mean"),
            avg_rework_count=("rework_count", "mean"),
            avg_manual_steps=("manual_steps_count", "mean"),
            avg_total_minutes=("total_minutes", "mean"),
        )
        .sort_values("deal_count", ascending=False)
        .reset_index()
    )

    summary_df = pd.DataFrame([{"metric": k, "value": v} for k, v in summary.items()])
    summary_df.to_csv(ROOT / "data" / "processed" / "as_is_summary_metrics.csv", index=False)
    stage_metrics.to_csv(ROOT / "data" / "processed" / "stage_metrics.csv", index=False)
    exception_metrics.to_csv(ROOT / "data" / "processed" / "exception_metrics.csv", index=False)
    return stage_metrics, exception_metrics, summary


def pct(v: float) -> str:
    return f"{v:.1%}"


def markdown_table(df: pd.DataFrame, floatfmt: str = ".2f") -> str:
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        values = []
        for value in row:
            if isinstance(value, float):
                values.append(format(value, floatfmt))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_docs(stage_metrics: pd.DataFrame, exception_metrics: pd.DataFrame, summary: dict[str, float]) -> None:
    worst_stage = stage_metrics.sort_values("avg_minutes", ascending=False).iloc[0]
    limit_row = exception_metrics[exception_metrics["exception_type"] == "limit_delay"].iloc[0]
    ssi_row = exception_metrics[exception_metrics["exception_type"] == "incomplete_ssi"].iloc[0]
    settlement_row = exception_metrics[exception_metrics["exception_type"] == "settlement_fail"].iloc[0]

    (ROOT / "docs" / "as_is_metrics.md").write_text(
        f"""# AS-IS Metrics

| Metric | Value |
|---|---:|
| Deal count | {summary['deal_count']:,.0f} |
| Average total processing time, minutes | {summary['avg_total_minutes']:.1f} |
| Median total processing time, minutes | {summary['median_total_minutes']:.1f} |
| SLA met rate | {pct(summary['sla_met_rate'])} |
| SLA breach rate | {pct(summary['sla_breach_rate'])} |
| STP rate | {pct(summary['stp_rate'])} |
| Manual processing rate | {pct(summary['manual_processing_rate'])} |
| Average rework count | {summary['avg_rework_count']:.2f} |
| Registration error rate | {pct(summary['registration_error_rate'])} |
| Settlement issue rate | {pct(summary['settlement_issue_rate'])} |
| Average manual steps per deal | {summary['avg_manual_steps']:.2f} |
| Average processing cost, USD | {summary['avg_processing_cost_usd']:.2f} |
| First Pass Yield | {pct(summary['first_pass_yield'])} |

## Time Decomposition

{markdown_table(stage_metrics)}

The largest average waiting block is `{worst_stage['stage']}` at {worst_stage['avg_minutes']:.1f} minutes.
""",
        encoding="utf-8",
    )

    (ROOT / "docs" / "bottleneck_analysis.md").write_text(
        f"""# Bottleneck Analysis

## Confirmed Problems

1. Limit checks are a major delay source. `limit_delay` represents {limit_row['deal_count']:,.0f} deals and has an SLA breach rate of {pct(limit_row['sla_breach_rate'])}.
2. Settlement instructions are not validated early enough. `incomplete_ssi` represents {ssi_row['deal_count']:,.0f} deals and averages {ssi_row['avg_rework_count']:.2f} rework loops.
3. Manual re-entry remains material. Manual processing rate is {pct(summary['manual_processing_rate'])}, with {summary['avg_manual_steps']:.2f} manual steps per deal on average.
4. Settlement exceptions are lower frequency but high impact. `settlement_fail` represents {settlement_row['deal_count']:,.0f} deals and has an average total time of {settlement_row['avg_total_minutes']:.1f} minutes.
5. SLA monitoring is reactive. SLA breach rate is {pct(summary['sla_breach_rate'])}, and the process has no dedicated early-warning step in AS-IS.

## Interpretation

The main value of the redesign is not changing FX pricing. It is reducing waiting time, duplicate manual entry, late validation and exception handling effort.
""",
        encoding="utf-8",
    )

    (ROOT / "docs" / "business_rules.md").write_text(
        """# Business Rules

| ID | Rule |
|---|---|
| BRULE-001 | A deal cannot be confirmed when the available client trading limit is insufficient. |
| BRULE-002 | A change to notional, currency pair, value date or direction after client acceptance requires repeated client approval. |
| BRULE-003 | Deals above the high-value threshold require additional Middle Office control. |
| BRULE-004 | A quote expires if the client does not accept within the configured validity window. |
| BRULE-005 | Settlement cannot start until SSI completeness has been validated. |
| BRULE-006 | Retried requests must reuse the original client request reference to prevent duplicate deals. |
""",
        encoding="utf-8",
    )

    (ROOT / "docs" / "change_register.md").write_text(
        """# Change Register

| AS-IS problem | TO-BE change | Requirement | Metric |
|---|---|---|---|
| Repeated manual entry | Automatic transfer of accepted deal data to trade capture | FR-004 | Manual processing rate, manual steps per deal |
| Late limit check | Pre-trade limit check before trader quote request | FR-002 | Rejected-after-quote rate, quote effort lost |
| Incomplete settlement instructions | Mandatory SSI validation in request form | FR-001 | Rework rate, settlement fail rate |
| No SLA early warning | SLA timer and notification service | FR-006 | SLA breach rate |
| Standard and problem deals share one route | Exception queue with owner, type and due time | FR-005 | Exception aging, first pass yield |
| Duplicate client requests | Idempotent request handling and single deal ID | FR-003, NFR-003 | Duplicate request rate |
""",
        encoding="utf-8",
    )

    (ROOT / "docs" / "to_be_design.md").write_text(
        """# TO-BE Design

The target process moves validation earlier and separates standard flow from exceptions.

## Key Changes

- Single digital request form for Sales and client-originated requests.
- Automatic mandatory-field validation.
- Pre-trade client and limit check before trader involvement.
- Single deal identifier from request creation to settlement.
- Automatic data transfer to trade capture after client acceptance.
- Standard deals follow an STP route.
- Exceptions are routed to a dedicated queue with owner, SLA and reason code.
- Confirmation is generated automatically from captured deal data.
- SLA timer sends alerts before breach.
- Every material change is written to audit log.

## Expected Effect

The target operating model does not remove Sales, Trader, Risk, Middle Office or Operations. It changes their focus: employees handle exceptions and controls, while standard deals move through the process with fewer manual handoffs.
""",
        encoding="utf-8",
    )


def write_bpmn_file(path: Path, process_id: str, process_name: str, tasks: list[str]) -> None:
    ET.register_namespace("bpmn", "http://www.omg.org/spec/BPMN/20100524/MODEL")
    ET.register_namespace("bpmndi", "http://www.omg.org/spec/BPMN/20100524/DI")
    ET.register_namespace("dc", "http://www.omg.org/spec/DD/20100524/DC")
    ET.register_namespace("di", "http://www.omg.org/spec/DD/20100524/DI")
    ns = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
    defs = ET.Element(ns + "definitions", attrib={"id": "Definitions_1", "targetNamespace": "fx-process-analysis"})
    collab = ET.SubElement(defs, ns + "collaboration", attrib={"id": f"Collaboration_{process_id}"})
    ET.SubElement(collab, ns + "participant", attrib={"id": f"Participant_{process_id}", "name": "OTC FX Front-to-Back Process", "processRef": process_id})
    ET.SubElement(defs, ns + "message", attrib={"id": "Message_ClientConfirmation", "name": "Client confirmation"})
    ET.SubElement(defs, ns + "error", attrib={"id": "Error_SettlementFailure", "name": "Settlement failure"})
    process = ET.SubElement(defs, "{http://www.omg.org/spec/BPMN/20100524/MODEL}process", attrib={"id": process_id, "name": process_name, "isExecutable": "false"})
    lane_set = ET.SubElement(process, ns + "laneSet", attrib={"id": "LaneSet_1"})
    lanes = ["Client", "Sales", "Trader", "Risk_Compliance", "Middle_Office", "Operations", "System"]
    lane_nodes = {lane: ET.SubElement(lane_set, ns + "lane", attrib={"id": f"Lane_{lane}", "name": lane.replace("_", "/")}) for lane in lanes}
    ET.SubElement(process, ns + "startEvent", attrib={"id": "StartEvent_1", "name": "Client request received"})
    ET.SubElement(lane_nodes["Client"], ns + "flowNodeRef").text = "StartEvent_1"
    prev = "StartEvent_1"
    for i, task in enumerate(tasks, start=1):
        task_id = f"Task_{i:02d}"
        kind = "serviceTask" if any(w in task.lower() for w in ["auto", "system", "validate", "notify", "audit"]) else "userTask"
        ET.SubElement(process, ns + kind, attrib={"id": task_id, "name": task})
        lane_name = lanes[min(i // 2, len(lanes) - 1)]
        ET.SubElement(lane_nodes[lane_name], ns + "flowNodeRef").text = task_id
        ET.SubElement(process, ns + "sequenceFlow", attrib={"id": f"Flow_{i:02d}", "sourceRef": prev, "targetRef": task_id})
        prev = task_id
        if i in {2, 5, 9}:
            gw = f"Gateway_{i:02d}"
            ET.SubElement(process, ns + "exclusiveGateway", attrib={"id": gw, "name": "Exception?"})
            ET.SubElement(lane_nodes["System"], ns + "flowNodeRef").text = gw
            ET.SubElement(process, ns + "sequenceFlow", attrib={"id": f"Flow_GW_{i:02d}", "sourceRef": prev, "targetRef": gw})
            prev = gw
    parallel_id = "Gateway_Parallel_Settlement_Reconciliation"
    ET.SubElement(process, ns + "parallelGateway", attrib={"id": parallel_id, "name": "Settlement and reconciliation"})
    ET.SubElement(lane_nodes["Operations"], ns + "flowNodeRef").text = parallel_id
    ET.SubElement(process, ns + "sequenceFlow", attrib={"id": "Flow_Parallel", "sourceRef": prev, "targetRef": parallel_id})

    timer_event = ET.SubElement(process, ns + "intermediateCatchEvent", attrib={"id": "TimerEvent_SLA", "name": "SLA timer"})
    ET.SubElement(timer_event, ns + "timerEventDefinition")
    ET.SubElement(lane_nodes["System"], ns + "flowNodeRef").text = "TimerEvent_SLA"
    ET.SubElement(process, ns + "sequenceFlow", attrib={"id": "Flow_Timer", "sourceRef": parallel_id, "targetRef": "TimerEvent_SLA"})

    message_event = ET.SubElement(process, ns + "intermediateCatchEvent", attrib={"id": "MessageEvent_Client", "name": "Client message"})
    ET.SubElement(message_event, ns + "messageEventDefinition", attrib={"messageRef": "Message_ClientConfirmation"})
    ET.SubElement(lane_nodes["Client"], ns + "flowNodeRef").text = "MessageEvent_Client"
    ET.SubElement(process, ns + "sequenceFlow", attrib={"id": "Flow_Message", "sourceRef": "TimerEvent_SLA", "targetRef": "MessageEvent_Client"})

    boundary = ET.SubElement(process, ns + "boundaryEvent", attrib={"id": "ErrorEvent_Settlement", "name": "Settlement error", "attachedToRef": tasks and f"Task_{len(tasks):02d}" or "Task_01"})
    ET.SubElement(boundary, ns + "errorEventDefinition", attrib={"errorRef": "Error_SettlementFailure"})
    ET.SubElement(lane_nodes["Operations"], ns + "flowNodeRef").text = "ErrorEvent_Settlement"

    ET.SubElement(process, ns + "endEvent", attrib={"id": "EndEvent_1", "name": "Deal completed or rejected"})
    ET.SubElement(lane_nodes["Operations"], ns + "flowNodeRef").text = "EndEvent_1"
    ET.SubElement(process, ns + "sequenceFlow", attrib={"id": "Flow_End", "sourceRef": "MessageEvent_Client", "targetRef": "EndEvent_1"})
    ET.ElementTree(defs).write(path, encoding="utf-8", xml_declaration=True)


def draw_process_png(path: Path, title: str, lanes: list[str], steps: list[tuple[int, str]], color: str) -> None:
    fig, ax = plt.subplots(figsize=(18, 10))
    ax.set_xlim(0, 18)
    ax.set_ylim(0, len(lanes))
    ax.axis("off")
    ax.set_title(title, fontsize=18, weight="bold", pad=18)
    for idx, lane in enumerate(lanes):
        y = len(lanes) - idx - 1
        ax.add_patch(plt.Rectangle((0, y), 18, 1, fill=False, edgecolor="#8a8a8a", linewidth=1))
        ax.text(0.15, y + 0.5, lane, va="center", ha="left", fontsize=10, weight="bold")
    x_positions = np.linspace(2.2, 16.7, len(steps))
    prev = None
    for x, (lane_idx, label) in zip(x_positions, steps):
        y = len(lanes) - lane_idx - 0.5
        ax.add_patch(plt.Rectangle((x - 0.55, y - 0.22), 1.1, 0.44, facecolor=color, edgecolor="#253238", linewidth=1.2))
        ax.text(x, y, "\n".join(textwrap.wrap(label, 14)), va="center", ha="center", fontsize=8, color="#101820")
        if prev:
            ax.annotate("", xy=(x - 0.62, y), xytext=prev, arrowprops={"arrowstyle": "->", "lw": 1.2, "color": "#253238"})
        prev = (x + 0.62, y)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def create_bpmn() -> None:
    lanes = ["Client", "Sales", "Trader", "Risk/Compliance", "Middle Office", "Operations", "System"]
    as_is_tasks = [
        (0, "Send request"),
        (1, "Check completeness"),
        (3, "Client and limit check"),
        (2, "Prepare quote"),
        (1, "Send quote"),
        (0, "Accept terms"),
        (1, "Manual trade capture"),
        (4, "Deal control"),
        (5, "Prepare confirmation"),
        (5, "Check SSI"),
        (5, "Settlement"),
        (5, "Reconciliation"),
        (5, "Handle errors"),
    ]
    to_be_tasks = [
        (0, "Submit digital request"),
        (6, "Auto validate fields"),
        (6, "Pre-trade limit check"),
        (2, "Prepare quote"),
        (0, "Accept terms"),
        (6, "Auto trade capture"),
        (4, "Risk-based control"),
        (6, "Auto confirmation"),
        (6, "SLA monitoring"),
        (5, "Settlement"),
        (6, "Auto reconciliation"),
        (5, "Exception queue"),
    ]
    write_bpmn_file(ROOT / "bpmn" / "as_is_process.bpmn", "Process_AS_IS", "AS-IS OTC FX Spot Process", [x[1] for x in as_is_tasks])
    write_bpmn_file(ROOT / "bpmn" / "to_be_process.bpmn", "Process_TO_BE", "TO-BE OTC FX Spot Process", [x[1] for x in to_be_tasks])
    draw_process_png(ROOT / "bpmn" / "as_is_process.png", "AS-IS OTC FX Spot Process", lanes, as_is_tasks, "#F5C6A5")
    draw_process_png(ROOT / "bpmn" / "to_be_process.png", "TO-BE OTC FX Spot Process", lanes, to_be_tasks, "#B9DCC4")


def create_dashboard(df: pd.DataFrame, stage_metrics: pd.DataFrame, exception_metrics: pd.DataFrame, summary: dict[str, float]) -> None:
    fig = plt.figure(figsize=(16, 9), facecolor="#F7F8FA")
    gs = fig.add_gridspec(3, 4, hspace=0.55, wspace=0.35)
    fig.suptitle("OTC FX Spot Process Dashboard", fontsize=20, weight="bold", x=0.04, ha="left")

    kpis = [
        ("Deals", f"{summary['deal_count']:,.0f}"),
        ("Avg minutes", f"{summary['avg_total_minutes']:.1f}"),
        ("SLA breach", pct(summary["sla_breach_rate"])),
        ("STP rate", pct(summary["stp_rate"])),
    ]
    for i, (label, value) in enumerate(kpis):
        ax = fig.add_subplot(gs[0, i])
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, facecolor="white", edgecolor="#D6DAE0"))
        ax.text(0.06, 0.68, label, fontsize=11, color="#59636E", transform=ax.transAxes)
        ax.text(0.06, 0.28, value, fontsize=24, weight="bold", color="#17202A", transform=ax.transAxes)

    ax1 = fig.add_subplot(gs[1, :2])
    sorted_stage = stage_metrics.sort_values("avg_minutes")
    ax1.barh(sorted_stage["stage"], sorted_stage["avg_minutes"], color="#4472C4")
    ax1.set_title("Average Minutes by Stage", loc="left", weight="bold")
    ax1.set_xlabel("minutes")

    ax2 = fig.add_subplot(gs[1, 2:])
    ex = exception_metrics[exception_metrics["exception_type"] != "none"].sort_values("deal_count")
    ax2.barh(ex["exception_type"], ex["deal_count"], color="#ED7D31")
    ax2.set_title("Exception Count", loc="left", weight="bold")

    ax3 = fig.add_subplot(gs[2, :2])
    status = df["deal_status"].value_counts()
    ax3.pie(status.values, labels=status.index, autopct="%1.1f%%", startangle=90, colors=["#70AD47", "#A5A5A5", "#C00000", "#FFC000"])
    ax3.set_title("Deal Status Mix", loc="left", weight="bold")

    ax4 = fig.add_subplot(gs[2, 2:])
    by_channel = df.groupby("request_channel")["manual_processing_flag"].mean().sort_values()
    ax4.bar(by_channel.index, by_channel.values, color="#5B9BD5")
    ax4.set_title("Manual Processing Rate by Channel", loc="left", weight="bold")
    ax4.set_ylim(0, 1)
    ax4.yaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
    fig.savefig(ROOT / "dashboard" / "process_dashboard.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_excel_files(summary: dict[str, float], stage_metrics: pd.DataFrame) -> None:
    import xlsxwriter

    risk_path = ROOT / "risk" / "risk_control_matrix.xlsx"
    wb = xlsxwriter.Workbook(risk_path)
    ws = wb.add_worksheet("Risk Matrix")
    header = wb.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white", "border": 1})
    cell = wb.add_format({"border": 1, "valign": "top"})
    score_fmt = wb.add_format({"border": 1, "num_format": "0", "bg_color": "#FCE4D6"})
    rows = [
        ["Неверная сумма", "Ручной ввод", "Финансовые потери", 3, 4, "Формат-контроль и maker-checker"],
        ["Превышение лимита", "Поздняя проверка", "Отмена сделки", 3, 4, "Автоматическая pre-trade проверка"],
        ["Дублирование сделки", "Повторная отправка", "Двойной расчет", 2, 5, "Единый deal ID и idempotency"],
        ["Ошибка реквизитов", "Неполные SSI", "Settlement fail", 3, 4, "Предварительная валидация SSI"],
        ["Просроченная котировка", "Долгое согласование", "Сделка по неактуальному курсу", 3, 4, "Срок действия котировки"],
        ["Нарушение SLA", "Нет раннего мониторинга", "Просрочка обработки", 3, 3, "SLA timer и уведомления"],
    ]
    headers = ["Риск", "Причина", "Последствие", "Вероятность", "Влияние", "Контроль", "Risk Score"]
    ws.write_row(0, 0, headers, header)
    for r, row in enumerate(rows, start=1):
        ws.write_row(r, 0, row, cell)
        ws.write_formula(r, 6, f"=D{r+1}*E{r+1}", score_fmt)
    ws.set_column("A:C", 24)
    ws.set_column("D:E", 14)
    ws.set_column("F:F", 36)
    ws.set_column("G:G", 12)
    chart = wb.add_chart({"type": "column"})
    chart.add_series({"name": "Risk Score", "categories": ["Risk Matrix", 1, 0, len(rows), 0], "values": ["Risk Matrix", 1, 6, len(rows), 6]})
    chart.set_title({"name": "Risk Score"})
    ws.insert_chart("I2", chart, {"x_scale": 1.2, "y_scale": 1.15})
    wb.close()

    econ_path = ROOT / "economics" / "economic_effect.xlsx"
    wb = xlsxwriter.Workbook(econ_path)
    ws = wb.add_worksheet("Scenarios")
    ws.write_row(0, 0, ["Metric", "Conservative", "Base", "Optimistic"], header)
    deal_count = summary["deal_count"]
    scenarios = {
        "Conservative": [deal_count, 6, 32, 18, 180, 120_000],
        "Base": [deal_count, 12, 38, 34, 220, 150_000],
        "Optimistic": [deal_count, 18, 44, 48, 260, 190_000],
    }
    labels = [
        "Annual deal volume",
        "Minutes saved per deal",
        "Staff hourly cost, USD",
        "Avoided errors",
        "Average error cost, USD",
        "Implementation cost, USD",
        "Labor hours saved",
        "Labor cost saving, USD",
        "Error saving, USD",
        "Annual effect, USD",
        "ROI",
        "Payback months",
    ]
    for i, label in enumerate(labels, start=1):
        ws.write(i, 0, label, cell)
    for c, name in enumerate(scenarios, start=1):
        vals = scenarios[name]
        for r, v in enumerate(vals, start=1):
            ws.write(r, c, v, cell)
        col = xlsxwriter.utility.xl_col_to_name(c)
        ws.write_formula(7, c, f"={col}2*{col}3/60", cell)
        ws.write_formula(8, c, f"={col}8*{col}4", cell)
        ws.write_formula(9, c, f"={col}5*{col}6", cell)
        ws.write_formula(10, c, f"={col}9+{col}10", cell)
        ws.write_formula(11, c, f"=({col}11-{col}7)/{col}7", cell)
        ws.write_formula(12, c, f"={col}7/({col}11/12)", cell)
    ws.set_column("A:A", 28)
    ws.set_column("B:D", 16)
    ws.set_row(0, 22)
    ws.conditional_format("B12:D12", {"type": "3_color_scale"})
    ch = wb.add_chart({"type": "column"})
    ch.add_series({"name": "Annual effect", "categories": ["Scenarios", 0, 1, 0, 3], "values": ["Scenarios", 10, 1, 10, 3]})
    ch.set_title({"name": "Annual Effect by Scenario"})
    ws.insert_chart("F2", ch, {"x_scale": 1.2, "y_scale": 1.15})
    sens = wb.add_worksheet("Volume Sensitivity")
    sens.write_row(0, 0, ["Deal volume", "Annual effect, USD"], header)
    for r, volume in enumerate([5000, 7500, 10000, 12500, 15000, 20000], start=1):
        sens.write(r, 0, volume, cell)
        sens.write_formula(r, 1, f"=A{r+1}*Scenarios!C3/60*Scenarios!C4+Scenarios!C5*Scenarios!C6", cell)
    sens.set_column("A:B", 20)
    wb.close()


def create_notebook() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        nbf.v4.new_markdown_cell("# OTC FX Spot Process Analysis\n\nAnalysis notebook for the synthetic process log built on Kaggle market rates."),
        nbf.v4.new_code_cell("import pandas as pd\nimport matplotlib.pyplot as plt\n\ndf = pd.read_csv('../data/synthetic_deals.csv', parse_dates=['request_time','quote_time','client_accept_time','limit_check_time','trade_capture_time','confirmation_time','settlement_time'])\ndf.head()"),
        nbf.v4.new_code_cell("df['total_minutes'] = (df['settlement_time'] - df['request_time']).dt.total_seconds() / 60\nsummary = pd.Series({\n    'deal_count': len(df),\n    'avg_total_minutes': df['total_minutes'].mean(),\n    'median_total_minutes': df['total_minutes'].median(),\n    'sla_breach_rate': df['sla_breach'].mean(),\n    'manual_processing_rate': df['manual_processing_flag'].mean(),\n    'stp_rate': (~df['manual_processing_flag']).mean(),\n    'first_pass_yield': ((df['deal_status'].eq('settled')) & (df['rework_count'].eq(0))).mean(),\n})\nsummary"),
        nbf.v4.new_code_cell("stage_pairs = [('request_to_quote','request_time','quote_time'),('quote_to_accept','quote_time','client_accept_time'),('accept_to_limit','client_accept_time','limit_check_time'),('limit_to_capture','limit_check_time','trade_capture_time'),('capture_to_confirmation','trade_capture_time','confirmation_time'),('confirmation_to_settlement','confirmation_time','settlement_time')]\nstages = pd.DataFrame([{'stage': n, 'avg_minutes': (df[e]-df[s]).dt.total_seconds().mean()/60} for n,s,e in stage_pairs])\nstages.sort_values('avg_minutes').plot.barh(x='stage', y='avg_minutes', legend=False, title='Average minutes by stage')\nplt.xlabel('minutes')"),
        nbf.v4.new_code_cell("df.groupby('exception_type').agg(deals=('deal_id','count'), sla_breach_rate=('sla_breach','mean'), avg_rework=('rework_count','mean')).sort_values('deals', ascending=False)"),
    ]
    nbf.write(nb, ROOT / "notebooks" / "process_analysis.ipynb")


def create_pdf(summary: dict[str, float], stage_metrics: pd.DataFrame) -> None:
    pdf_path = ROOT / "presentation" / "project_summary.pdf"
    with PdfPages(pdf_path) as pdf:
        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        ax.axis("off")
        ax.text(0.05, 0.88, "Анализ и редизайн процесса внебиржевой валютной сделки", fontsize=20, weight="bold")
        ax.text(0.05, 0.78, "Учебный проект на гибридных данных: Kaggle FX rates + synthetic process log", fontsize=13)
        ax.text(0.05, 0.63, f"Deals: {summary['deal_count']:,.0f}\nAvg time: {summary['avg_total_minutes']:.1f} min\nSLA breach: {pct(summary['sla_breach_rate'])}\nManual processing: {pct(summary['manual_processing_rate'])}\nSTP rate: {pct(summary['stp_rate'])}", fontsize=14)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        sorted_stage = stage_metrics.sort_values("avg_minutes")
        ax.barh(sorted_stage["stage"], sorted_stage["avg_minutes"], color="#4472C4")
        ax.set_title("AS-IS Time Decomposition", fontsize=18, weight="bold")
        ax.set_xlabel("Average minutes")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        ax.axis("off")
        bullets = [
            "Move mandatory-field and SSI validation to request creation.",
            "Run limit check before trader quote request.",
            "Use one deal ID across Sales, Trading, Risk, Middle Office and Operations.",
            "Automatically capture accepted deals and generate confirmation.",
            "Route exceptions to a dedicated queue with SLA ownership.",
        ]
        ax.text(0.05, 0.9, "TO-BE Recommendations", fontsize=20, weight="bold")
        ax.text(0.08, 0.75, "\n".join([f"- {b}" for b in bullets]), fontsize=14, va="top")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


def main() -> None:
    ensure_dirs()
    df = load_deals()
    stage_metrics, exception_metrics, summary = compute_metrics(df)
    write_docs(stage_metrics, exception_metrics, summary)
    create_bpmn()
    create_dashboard(df, stage_metrics, exception_metrics, summary)
    write_excel_files(summary, stage_metrics)
    create_notebook()
    create_pdf(summary, stage_metrics)
    print(json.dumps({"status": "ok", "deals": int(summary["deal_count"]), "sla_breach_rate": summary["sla_breach_rate"]}, indent=2))


if __name__ == "__main__":
    main()
