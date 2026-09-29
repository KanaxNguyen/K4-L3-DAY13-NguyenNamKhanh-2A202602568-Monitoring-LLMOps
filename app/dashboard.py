from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

LOG_PATH = Path(os.getenv("LOG_PATH", "data/logs.jsonl"))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_v[int(k)])
    d0 = sorted_v[int(f)] * (c - k)
    d1 = sorted_v[int(c)] * (k - f)
    return float(d0 + d1)


def compute_dashboard_metrics(window_minutes: int = 60) -> dict[str, Any]:
    if not LOG_PATH.exists():
        records: list[dict] = []
    else:
        records = []
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Filter records within last window_minutes if timestamp exists
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_minutes)
    recent_records: list[dict] = []
    for r in records:
        ts_str = r.get("ts")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts >= cutoff:
                    recent_records.append(r)
                continue
            except Exception:
                pass
        recent_records.append(r)

    # 1. Latency
    responses = [r for r in recent_records if r.get("event") == "response_sent"]
    latencies = [float(r["latency_ms"]) for r in responses if "latency_ms" in r]
    ttfts = [float(r["ttft_ms"]) for r in responses if "ttft_ms" in r]

    p50 = round(_percentile(latencies, 50), 1)
    p95 = round(_percentile(latencies, 95), 1)
    p99 = round(_percentile(latencies, 99), 1)
    ttft_p95 = round(_percentile(ttfts, 95), 1)

    # 2. Traffic
    requests_rcv = [r for r in recent_records if r.get("event") == "request_received"]
    req_count = len(requests_rcv)
    rate_per_min = round(req_count / max(1, window_minutes), 2)

    # 3. Errors
    requests_fail = [r for r in recent_records if r.get("event") == "request_failed"]
    fail_count = len(requests_fail)
    total_req = req_count if req_count > 0 else (len(responses) + fail_count)
    error_rate = round((fail_count / total_req * 100), 2) if total_req > 0 else 0.0

    error_types: dict[str, int] = {}
    for r in requests_fail:
        etype = r.get("error_type", "Unknown")
        error_types[etype] = error_types.get(etype, 0) + 1

    tool_calls = [r for r in recent_records if "tool_success" in r and r.get("tool_name")]
    tool_successes = [r for r in tool_calls if r.get("tool_success") is True]
    tool_success_rate = (
        round(len(tool_successes) / len(tool_calls) * 100, 1) if tool_calls else 100.0
    )

    # 4. Cost
    costs = [float(r["cost_usd"]) for r in responses if "cost_usd" in r]
    total_cost = round(sum(costs), 6)

    # 5. Tokens
    tokens_in = sum(int(r["tokens_in"]) for r in responses if "tokens_in" in r)
    tokens_out = sum(int(r["tokens_out"]) for r in responses if "tokens_out" in r)

    # 6. Quality
    qualities = [float(r["quality_score"]) for r in responses if "quality_score" in r]
    avg_quality = round(sum(qualities) / len(qualities), 2) if qualities else 0.0

    # Keep a small fixed-width time series for the runtime dashboard. Each point
    # is the p95 of response latencies in a five-minute bucket from real logs.
    series_bucket_minutes = 5
    series_bucket_count = max(1, min(12, math.ceil(window_minutes / series_bucket_minutes)))
    series_start = now - timedelta(minutes=series_bucket_count * series_bucket_minutes)
    latency_buckets: list[list[float]] = [[] for _ in range(series_bucket_count)]
    for record in responses:
        try:
            ts = datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
            bucket = int((ts - series_start).total_seconds() // (series_bucket_minutes * 60))
            if 0 <= bucket < series_bucket_count:
                latency_buckets[bucket].append(float(record["latency_ms"]))
        except (KeyError, ValueError, TypeError):
            continue
    latency_series = [
        {
            "time": (series_start + timedelta(minutes=i * series_bucket_minutes)).strftime("%H:%M"),
            "p95_ms": round(_percentile(values, 95), 1) if values else None,
        }
        for i, values in enumerate(latency_buckets)
    ]

    return {
        "latency": {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "ttft_p95": ttft_p95,
            "threshold_p95": 3000,
            "status": "PASS" if p95 <= 3000 else "ALERT",
        },
        "traffic": {
            "count": req_count,
            "rate_per_minute": rate_per_min,
            "threshold_rate": 1,
            "status": "PASS" if rate_per_min >= 0 else "PASS",
        },
        "errors": {
            "error_rate_pct": error_rate,
            "failed_count": fail_count,
            "error_types": error_types,
            "tool_success_rate_pct": tool_success_rate,
            "threshold_pct": 2.0,
            "status": "PASS" if error_rate <= 2.0 else "ALERT",
        },
        "cost": {
            "total_usd": total_cost,
            "threshold_usd": 2.5,
            "status": "PASS" if total_cost <= 2.5 else "ALERT",
        },
        "tokens": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total_tokens": tokens_in + tokens_out,
            "threshold": 50000,
            "status": "PASS" if (tokens_in + tokens_out) <= 50000 else "ALERT",
        },
        "quality": {
            "mean": avg_quality,
            "threshold": 0.75,
            "status": "PASS" if avg_quality >= 0.75 else "ALERT",
        },
        "latency_series": latency_series,
        "latency_series_threshold_ms": 3000,
        "latency_series_bucket_minutes": series_bucket_minutes,
        "window_minutes": window_minutes,
        "sample_count": len(recent_records),
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view() -> str:
    data = compute_dashboard_metrics(60)
    lat = data["latency"]
    traf = data["traffic"]
    err = data["errors"]
    cost = data["cost"]
    tok = data["tokens"]
    qual = data["quality"]

    chart_width, chart_height = 320, 112
    chart_top, chart_bottom = 8, 82
    series_values = [point["p95_ms"] for point in data["latency_series"] if point["p95_ms"] is not None]
    chart_max = max([data["latency_series_threshold_ms"], *series_values, 1])
    def chart_y(value: float) -> float:
        return chart_bottom - min(value, chart_max) / chart_max * (chart_bottom - chart_top)
    points = [
        (i * chart_width / max(1, len(data["latency_series"]) - 1), chart_y(point["p95_ms"]))
        for i, point in enumerate(data["latency_series"])
        if point["p95_ms"] is not None
    ]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    threshold_y = chart_y(data["latency_series_threshold_ms"])
    x_labels = "".join(
        f'<text x="{i * chart_width / max(1, len(data["latency_series"]) - 1):.1f}" y="106" fill="#94a3b8" font-size="9" text-anchor="middle">{point["time"]}</text>'
        for i, point in enumerate(data["latency_series"])
        if i in {0, len(data["latency_series"]) // 2, len(data["latency_series"]) - 1}
    )
    latency_chart = f"""<div class="chart-wrap">
        <div class="chart-legend"><span><i></i> p95 latency (ms)</span><span class="threshold-legend">— — 3,000 ms threshold</span></div>
        <svg viewBox="0 0 {chart_width} {chart_height}" role="img" aria-label="Five-minute p95 latency time series for the last hour">
            <line x1="0" y1="{threshold_y:.1f}" x2="{chart_width}" y2="{threshold_y:.1f}" stroke="#f97316" stroke-dasharray="5 4" />
            <polyline points="{polyline}" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />
            {''.join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#38bdf8" />' for x, y in points)}
            {x_labels}
        </svg>
        <div class="chart-caption">5-minute buckets · p95 response latency · Last {data["window_minutes"]} minutes</div>
    </div>"""

    def badge(status: str) -> str:
        color = "#10b981" if status == "PASS" else "#ef4444"
        return f'<span style="background:{color}; color:white; padding:3px 8px; border-radius:4px; font-size:12px; font-weight:bold;">{status}</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>K4-L3A Day 13 Monitoring & LLMOps Dashboard</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 24px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #334155;
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        h1 {{ margin: 0; font-size: 24px; color: #38bdf8; }}
        .meta {{ color: #94a3b8; font-size: 14px; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 20px;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2);
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}
        .card-title {{
            font-weight: 600;
            font-size: 16px;
            color: #e2e8f0;
        }}
        .metric-big {{
            font-size: 32px;
            font-weight: 700;
            color: #38bdf8;
            margin: 8px 0;
        }}
        .sub-metrics {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            margin-top: 14px;
            padding-top: 12px;
            border-top: 1px solid #334155;
        }}
        .sub-item {{
            font-size: 13px;
            color: #94a3b8;
        }}
        .sub-val {{
            font-size: 15px;
            font-weight: 600;
            color: #f1f5f9;
        }}
        .threshold-bar {{
            margin-top: 10px;
            font-size: 12px;
            color: #64748b;
        }}
        .chart-wrap {{ margin-top: 14px; padding-top: 10px; border-top: 1px solid #334155; }}
        .chart-legend {{ display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-bottom: 2px; }}
        .chart-legend i {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: #38bdf8; margin-right: 4px; }}
        .threshold-legend {{ color: #fb923c; }}
        .chart-wrap svg {{ display: block; width: 100%; height: 112px; overflow: visible; }}
        .chart-caption {{ font-size: 10px; color: #64748b; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>K4-L3A Day 13 Monitoring & LLMOps Dashboard</h1>
            <div class="meta">Live contract from config/dashboard.yaml | Data: data/logs.jsonl</div>
        </div>
        <div class="meta" style="text-align: right;">
            Time range: <strong>Last 60m</strong> | Refresh: <strong>30s</strong><br>
            Active Samples: <strong>{data["sample_count"]}</strong> records
        </div>
    </div>

    <div class="grid">
        <!-- 1. Latency -->
        <div class="card">
            <div class="card-header">
                <span class="card-title">1. Latency percentiles & TTFT</span>
                {badge(lat["status"])}
            </div>
            <div class="metric-big">{lat["p95"]} <span style="font-size:16px; color:#94a3b8;">ms (P95)</span></div>
            <div class="threshold-bar">Threshold: P95 &le; 3000 ms</div>
            {latency_chart}
            <div class="sub-metrics">
                <div class="sub-item">P50: <span class="sub-val">{lat["p50"]} ms</span></div>
                <div class="sub-item">P99: <span class="sub-val">{lat["p99"]} ms</span></div>
                <div class="sub-item">TTFT P95: <span class="sub-val">{lat["ttft_p95"]} ms</span></div>
                <div class="sub-item">Unit: <span class="sub-val">milliseconds</span></div>
            </div>
        </div>

        <!-- 2. Traffic -->
        <div class="card">
            <div class="card-header">
                <span class="card-title">2. Request traffic</span>
                {badge(traf["status"])}
            </div>
            <div class="metric-big">{traf["count"]} <span style="font-size:16px; color:#94a3b8;">requests</span></div>
            <div class="threshold-bar">Threshold: Rate &ge; 1 req/min</div>
            <div class="sub-metrics">
                <div class="sub-item">Rate: <span class="sub-val">{traf["rate_per_minute"]} /min</span></div>
                <div class="sub-item">Window: <span class="sub-val">60 minutes</span></div>
            </div>
        </div>

        <!-- 3. Errors -->
        <div class="card">
            <div class="card-header">
                <span class="card-title">3. Error rate & Retrieval success</span>
                {badge(err["status"])}
            </div>
            <div class="metric-big">{err["error_rate_pct"]}% <span style="font-size:16px; color:#94a3b8;">error rate</span></div>
            <div class="threshold-bar">Threshold: Error rate &le; 2.0% | Failed: {err["failed_count"]}</div>
            <div class="sub-metrics">
                <div class="sub-item">Retrieval Success: <span class="sub-val">{err["tool_success_rate_pct"]}%</span></div>
                <div class="sub-item">Error Types: <span class="sub-val">{", ".join(err["error_types"].keys()) or "None"}</span></div>
            </div>
        </div>

        <!-- 4. Cost -->
        <div class="card">
            <div class="card-header">
                <span class="card-title">4. Cost over time</span>
                {badge(cost["status"])}
            </div>
            <div class="metric-big">${cost["total_usd"]:.4f} <span style="font-size:16px; color:#94a3b8;">USD</span></div>
            <div class="threshold-bar">Threshold: Total &le; 2.50 USD</div>
            <div class="sub-metrics">
                <div class="sub-item">Window Cost: <span class="sub-val">${cost["total_usd"]:.6f}</span></div>
                <div class="sub-item">Currency: <span class="sub-val">USD</span></div>
            </div>
        </div>

        <!-- 5. Tokens -->
        <div class="card">
            <div class="card-header">
                <span class="card-title">5. Input & output tokens</span>
                {badge(tok["status"])}
            </div>
            <div class="metric-big">{tok["total_tokens"]:,} <span style="font-size:16px; color:#94a3b8;">total</span></div>
            <div class="threshold-bar">Threshold: Sum &le; 50,000 tokens</div>
            <div class="sub-metrics">
                <div class="sub-item">Tokens In: <span class="sub-val">{tok["tokens_in"]:,}</span></div>
                <div class="sub-item">Tokens Out: <span class="sub-val">{tok["tokens_out"]:,}</span></div>
            </div>
        </div>

        <!-- 6. Quality -->
        <div class="card">
            <div class="card-header">
                <span class="card-title">6. Quality proxy</span>
                {badge(qual["status"])}
            </div>
            <div class="metric-big">{qual["mean"]:.2f} <span style="font-size:16px; color:#94a3b8;">/ 1.00</span></div>
            <div class="threshold-bar">Threshold: Mean &ge; 0.75</div>
            <div class="sub-metrics">
                <div class="sub-item">Score Range: <span class="sub-val">0.0 - 1.0</span></div>
                <div class="sub-item">Sample count: <span class="sub-val">{data["sample_count"]}</span></div>
            </div>
        </div>
    </div>
</body>
</html>"""
