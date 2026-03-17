#!/usr/bin/env python3
"""Fetch Home Assistant entity history over SSH and render it as an HTML/SVG graph.

Example:
    python scripts/plot_ha_history.py \
      --ssh-target root@192.168.0.13 \
      --start "2026-03-10 00:00:00" \
      --days 3 \
      --entity sensor.aqara_thp_3_temperature \
      --entity sensor.office_light_switch_1_temperature
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterable


REMOTE_QUERY_PROGRAM = r'''
import json
import sqlite3
import sys

cfg = json.loads(sys.argv[1])
conn = sqlite3.connect(cfg["db_path"])
cur = conn.cursor()

placeholders = ",".join("?" for _ in cfg["entities"])
query = f"""
SELECT
  m.entity_id,
  s.last_updated_ts,
  s.state
FROM states s
JOIN states_meta m ON s.metadata_id = m.metadata_id
WHERE m.entity_id IN ({placeholders})
  AND s.last_updated_ts >= ?
  AND s.last_updated_ts <= ?
  AND s.state NOT IN ('unknown', 'unavailable', 'None', '')
ORDER BY m.entity_id, s.last_updated_ts
"""
params = [*cfg["entities"], cfg["start_ts"], cfg["end_ts"]]
cur.execute(query, params)
rows = cur.fetchall()
print(json.dumps(rows))
'''


CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 24px;
  color: #1f2937;
  background: #f9fafb;
}
.container {
  max-width: 1400px;
  margin: 0 auto;
}
.card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.meta div {
  background: #f3f4f6;
  border-radius: 8px;
  padding: 10px 12px;
}
svg {
  width: 100%;
  height: auto;
  display: block;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.legend-swatch {
  width: 12px;
  height: 12px;
  border-radius: 999px;
}
code {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 6px;
}
.small {
  color: #6b7280;
  font-size: 13px;
}
.chart-wrap {
    position: relative;
}
.chart-tooltip {
    position: absolute;
    display: none;
    min-width: 220px;
    max-width: 320px;
    pointer-events: none;
    background: rgba(17, 24, 39, 0.94);
    color: #f9fafb;
    border-radius: 10px;
    padding: 10px 12px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.18);
    font-size: 13px;
    line-height: 1.4;
    z-index: 10;
}
.chart-tooltip strong {
    display: block;
    margin-bottom: 4px;
    font-size: 13px;
}
.chart-tooltip .muted {
    color: #d1d5db;
}
"""


@dataclass
class Sample:
    entity_id: str
    timestamp: datetime
    value: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch entity history from Home Assistant over SSH and render an HTML graph."
    )
    parser.add_argument(
        "--entity",
        dest="entities",
        action="append",
        required=True,
        help="Entity ID to plot. Repeat for multiple entities.",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Start date/time in ISO format, e.g. '2026-03-10 00:00:00' or '2026-03-10T00:00:00+01:00'.",
    )
    parser.add_argument(
        "--days",
        type=float,
        required=True,
        help="Number of days of history to fetch starting from --start.",
    )
    parser.add_argument(
        "--ssh-target",
        default="root@192.168.0.13",
        help="SSH target for the Home Assistant host.",
    )
    parser.add_argument(
        "--db-path",
        default="/config/home-assistant_v2.db",
        help="Path to the recorder SQLite database on the remote host.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output HTML path. Defaults to ./out/<timestamp>-history.html",
    )
    parser.add_argument(
        "--title",
        default="Home Assistant Entity History",
        help="Title shown in the generated graph.",
    )
    parser.add_argument(
        "--panel-height",
        type=int,
        default=260,
        help="Height of each entity panel in the SVG output.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1200,
        help="SVG width in pixels.",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="Draw all entities on the same graph instead of separate panels.",
    )
    return parser.parse_args()


def parse_start(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def fetch_samples(
    ssh_target: str,
    db_path: str,
    entities: list[str],
    start_ts: float,
    end_ts: float,
) -> list[Sample]:
    payload = {
        "db_path": db_path,
        "entities": entities,
        "start_ts": start_ts,
        "end_ts": end_ts,
    }
    remote_command = f"python3 - {shlex.quote(json.dumps(payload))}"
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            ssh_target,
            remote_command,
        ],
        input=REMOTE_QUERY_PROGRAM,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Remote query failed")

    rows = json.loads(result.stdout)
    samples: list[Sample] = []
    for entity_id, timestamp, state in rows:
        try:
            value = float(state)
        except (TypeError, ValueError):
            continue
        samples.append(
            Sample(
                entity_id=entity_id,
                timestamp=datetime.fromtimestamp(float(timestamp), timezone.utc),
                value=value,
            )
        )
    return samples


def group_samples(samples: Iterable[Sample]) -> dict[str, list[Sample]]:
    grouped: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.entity_id].append(sample)
    return dict(grouped)


def color_for_index(index: int) -> str:
    palette = [
        "#2563eb",
        "#dc2626",
        "#059669",
        "#d97706",
        "#7c3aed",
        "#0891b2",
        "#db2777",
        "#65a30d",
    ]
    return palette[index % len(palette)]


def format_tick(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def build_svg(
    grouped: dict[str, list[Sample]],
    start: datetime,
    end: datetime,
    width: int,
    panel_height: int,
    overlay: bool,
) -> tuple[str, list[tuple[str, str, int]], list[dict[str, Any]]]:
    margin_left = 80
    margin_right = 24
    margin_top = 26
    margin_bottom = 34
    plot_width = width - margin_left - margin_right
    panel_gap = 28
    entities = list(grouped.keys())
    colors: list[tuple[str, str, int]] = []
    interaction_series: list[dict[str, Any]] = []

    panels = [entities] if overlay else [[entity_id] for entity_id in entities]
    total_height = max(1, len(panels)) * panel_height + max(0, len(panels) - 1) * panel_gap
    entity_colors = {entity_id: color_for_index(index) for index, entity_id in enumerate(entities)}

    start_ts = start.timestamp()
    end_ts = end.timestamp()
    span_ts = max(1.0, end_ts - start_ts)

    svg_parts = [
        f'<svg viewBox="0 0 {width} {total_height}" xmlns="http://www.w3.org/2000/svg" role="img">',
        '<rect x="0" y="0" width="100%" height="100%" fill="#ffffff" />',
    ]

    for index, panel_entities in enumerate(panels):
        panel_y = index * (panel_height + panel_gap)
        plot_top = panel_y + margin_top
        plot_height = panel_height - margin_top - margin_bottom
        panel_samples = [sample for entity_id in panel_entities for sample in grouped[entity_id]]
        if panel_samples:
            values = [sample.value for sample in panel_samples]
            min_value = min(values)
            max_value = max(values)
            if math.isclose(min_value, max_value):
                padding = max(0.5, abs(min_value) * 0.05 or 0.5)
            else:
                padding = (max_value - min_value) * 0.08
            y_min = min_value - padding
            y_max = max_value + padding
        else:
            y_min = 0.0
            y_max = 1.0
        y_span = max(1e-9, y_max - y_min)

        title = ", ".join(panel_entities) if overlay else panel_entities[0]

        svg_parts.append(f'<text x="{margin_left}" y="{panel_y + 18}" font-size="16" font-weight="600" fill="#111827">{escape(title)}</text>')
        svg_parts.append(
            f'<rect x="{margin_left}" y="{plot_top}" width="{plot_width}" height="{plot_height}" fill="#ffffff" stroke="#d1d5db" stroke-width="1" rx="6" />'
        )
        svg_parts.append(
            f'<g id="hover-group-{index}" visibility="hidden" pointer-events="none">'
            f'<line id="hover-line-{index}" x1="{margin_left}" y1="{plot_top}" x2="{margin_left}" y2="{plot_top + plot_height}" stroke="#6b7280" stroke-width="1.5" stroke-dasharray="4 4" opacity="0.9" />'
            + ''.join(
                f'<circle id="hover-dot-{index}-{series_idx}" cx="{margin_left}" cy="{plot_top}" r="4.5" fill="{entity_colors[entity_id]}" stroke="#ffffff" stroke-width="2" />'
                for series_idx, entity_id in enumerate(panel_entities)
            )
            + '</g>'
        )

        for tick_index in range(5):
            fraction = tick_index / 4
            y = plot_top + plot_height - fraction * plot_height
            value = y_min + fraction * y_span
            svg_parts.append(
                f'<line x1="{margin_left}" y1="{y:.2f}" x2="{margin_left + plot_width}" y2="{y:.2f}" stroke="#e5e7eb" stroke-width="1" />'
            )
            svg_parts.append(
                f'<text x="{margin_left - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="12" fill="#6b7280">{value:.2f}</text>'
            )

        for tick_index in range(6):
            fraction = tick_index / 5
            x = margin_left + fraction * plot_width
            tick_dt = start + timedelta(seconds=fraction * span_ts)
            svg_parts.append(
                f'<line x1="{x:.2f}" y1="{plot_top}" x2="{x:.2f}" y2="{plot_top + plot_height}" stroke="#f3f4f6" stroke-width="1" />'
            )
            svg_parts.append(
                f'<text x="{x:.2f}" y="{plot_top + plot_height + 18}" text-anchor="middle" font-size="11" fill="#6b7280">{escape(format_tick(tick_dt))}</text>'
            )

        panel_series: list[dict[str, Any]] = []
        has_any_points = False
        for series_idx, entity_id in enumerate(panel_entities):
            color = entity_colors[entity_id]
            colors.append((entity_id, color, len(grouped[entity_id])))
            points: list[str] = []
            sample_points: list[dict[str, Any]] = []
            for sample in grouped[entity_id]:
                x = margin_left + ((sample.timestamp.timestamp() - start_ts) / span_ts) * plot_width
                y = plot_top + plot_height - ((sample.value - y_min) / y_span) * plot_height
                points.append(f"{x:.2f},{y:.2f}")
                sample_points.append(
                    {
                        "x": round(x, 2),
                        "y": round(y, 2),
                        "timestamp": sample.timestamp.isoformat(),
                        "value": sample.value,
                    }
                )

            if points:
                has_any_points = True
                svg_parts.append(
                    f'<polyline fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="{" ".join(points)}" />'
                )
                last_x, last_y = points[-1].split(",")
                svg_parts.append(
                    f'<circle cx="{last_x}" cy="{last_y}" r="3.5" fill="{color}" />'
                )

            panel_series.append(
                {
                    "series_index": series_idx,
                    "entity_id": entity_id,
                    "color": color,
                    "samples": sample_points,
                }
            )

        if not has_any_points:
            svg_parts.append(
                f'<text x="{margin_left + plot_width / 2:.2f}" y="{plot_top + plot_height / 2:.2f}" text-anchor="middle" font-size="14" fill="#9ca3af">No data</text>'
            )

        interaction_series.append(
            {
                "index": index,
                "plot_left": margin_left,
                "plot_right": margin_left + plot_width,
                "plot_top": plot_top,
                "plot_bottom": plot_top + plot_height,
                "plot_width": plot_width,
                "series": panel_series,
            }
        )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts), colors, interaction_series


def default_output_path() -> Path:
    output_dir = Path("out")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return output_dir / f"{timestamp}-ha-history.html"


def render_html(
    title: str,
    ssh_target: str,
    db_path: str,
    start: datetime,
    end: datetime,
    days: float,
    svg: str,
    legend: list[tuple[str, str, int]],
    interaction_series: list[dict[str, Any]],
) -> str:
    legend_html = "\n".join(
        (
            f'<div class="legend-item">'
            f'<span class="legend-swatch" style="background:{color}"></span>'
            f'<span>{escape(entity)} <span class="small">({count} points)</span></span>'
            f'</div>'
        )
        for entity, color, count in legend
    )
    interaction_json = json.dumps(interaction_series)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>{escape(title)}</h1>
      <div class="meta">
        <div><strong>Source</strong><br><code>{escape(ssh_target)}</code></div>
        <div><strong>Database</strong><br><code>{escape(db_path)}</code></div>
        <div><strong>Start</strong><br>{escape(format_tick(start))}</div>
        <div><strong>End</strong><br>{escape(format_tick(end))}</div>
        <div><strong>Days</strong><br>{days}</div>
      </div>
      <div class="legend">{legend_html}</div>
    </div>
    <div class="card">
            <div class="chart-wrap">
                {svg}
                <div id="chart-tooltip" class="chart-tooltip"></div>
            </div>
    </div>
  </div>
    <script>
        const chartPanels = {interaction_json};
        const svg = document.querySelector('svg');
        const tooltip = document.getElementById('chart-tooltip');
        const chartWrap = document.querySelector('.chart-wrap');

        function svgPointFromEvent(event) {{
            const point = svg.createSVGPoint();
            point.x = event.clientX;
            point.y = event.clientY;
            return point.matrixTransform(svg.getScreenCTM().inverse());
        }}

        function findNearestSample(samples, x) {{
            if (!samples.length) return null;
            let low = 0;
            let high = samples.length - 1;
            while (low < high) {{
                const mid = Math.floor((low + high) / 2);
                if (samples[mid].x < x) {{
                    low = mid + 1;
                }} else {{
                    high = mid;
                }}
            }}
            const candidate = samples[low];
            const previous = samples[Math.max(0, low - 1)];
            if (Math.abs(previous.x - x) <= Math.abs(candidate.x - x)) {{
                return previous;
            }}
            return candidate;
        }}

        function hideHover() {{
            tooltip.style.display = 'none';
            for (const panel of chartPanels) {{
                const group = document.getElementById(`hover-group-${{panel.index}}`);
                if (group) group.setAttribute('visibility', 'hidden');
            }}
        }}

        function renderTooltip(rows, cursorTime, event) {{
            const rowHtml = rows.map((row) => `
                <div><span style="color:${{row.color}};font-weight:600">${{row.entity_id}}</span>: ${{Number(row.value).toFixed(3)}} <span class="muted">(${{new Date(row.timestamp).toLocaleString()}})</span></div>
            `).join('');
            tooltip.innerHTML = `
                <strong>${{new Date(cursorTime).toLocaleString()}}</strong>
                ${{rowHtml}}
            `;
            tooltip.style.display = 'block';

            const wrapRect = chartWrap.getBoundingClientRect();
            const tooltipRect = tooltip.getBoundingClientRect();
            let left = event.clientX - wrapRect.left + 16;
            let top = event.clientY - wrapRect.top - tooltipRect.height - 16;
            if (left + tooltipRect.width > wrapRect.width - 8) {{
                left = wrapRect.width - tooltipRect.width - 8;
            }}
            if (top < 8) {{
                top = event.clientY - wrapRect.top + 16;
            }}
            tooltip.style.left = `${{Math.max(8, left)}}px`;
            tooltip.style.top = `${{Math.max(8, top)}}px`;
        }}

        svg.addEventListener('mousemove', (event) => {{
            const point = svgPointFromEvent(event);
            const activePanel = chartPanels.find((panel) =>
                point.x >= panel.plot_left &&
                point.x <= panel.plot_right &&
                point.y >= panel.plot_top &&
                point.y <= panel.plot_bottom
            );

            if (!activePanel) {{
                hideHover();
                return;
            }}

            const rows = [];
            let hasSample = false;
            const clampedX = Math.min(activePanel.plot_right, Math.max(activePanel.plot_left, point.x));
            const cursorTime = svg.dataset.startTs
                ? (Number(svg.dataset.startTs) + ((clampedX - activePanel.plot_left) / activePanel.plot_width) * Number(svg.dataset.spanTs)) * 1000
                : Date.now();

            for (const series of activePanel.series) {{
                const sample = findNearestSample(series.samples, clampedX);
                const dot = document.getElementById(`hover-dot-${{activePanel.index}}-${{series.series_index}}`);
                if (!sample) {{
                    if (dot) dot.setAttribute('visibility', 'hidden');
                    continue;
                }}
                hasSample = true;
                rows.push({{ entity_id: series.entity_id, color: series.color, value: sample.value, timestamp: sample.timestamp }});
                if (dot) {{
                    dot.setAttribute('visibility', 'visible');
                    dot.setAttribute('cx', sample.x);
                    dot.setAttribute('cy', sample.y);
                }}
            }}

            if (!hasSample) {{
                hideHover();
                return;
            }}

            for (const panel of chartPanels) {{
                const group = document.getElementById(`hover-group-${{panel.index}}`);
                if (!group) continue;
                if (panel.index !== activePanel.index) {{
                    group.setAttribute('visibility', 'hidden');
                    continue;
                }}
                group.setAttribute('visibility', 'visible');
                const line = document.getElementById(`hover-line-${{panel.index}}`);
                line.setAttribute('x1', clampedX);
                line.setAttribute('x2', clampedX);
            }}

            renderTooltip(rows, cursorTime, event);
        }});

        svg.addEventListener('mouseleave', hideHover);
    </script>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    start = parse_start(args.start)
    end = start + timedelta(days=args.days)
    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        samples = fetch_samples(
            ssh_target=args.ssh_target,
            db_path=args.db_path,
            entities=args.entities,
            start_ts=start.timestamp(),
            end_ts=end.timestamp(),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Error fetching samples: {exc}", file=sys.stderr)
        return 1

    grouped = group_samples(samples)
    ordered_grouped = {entity: grouped.get(entity, []) for entity in args.entities}
    svg, legend, interaction_series = build_svg(
        grouped=ordered_grouped,
        start=start,
        end=end,
        width=args.width,
        panel_height=args.panel_height,
        overlay=args.overlay,
    )
    svg = svg.replace('<svg ', f'<svg data-start-ts="{start.timestamp()}" data-span-ts="{(end - start).total_seconds()}" ', 1)
    html = render_html(
        title=args.title,
        ssh_target=args.ssh_target,
        db_path=args.db_path,
        start=start,
        end=end,
        days=args.days,
        svg=svg,
        legend=legend,
        interaction_series=interaction_series,
    )
    output_path.write_text(html, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
