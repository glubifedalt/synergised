"""
call_sheet.py – Synergy Teacher Dashboard
Generates a printable/saveable HTML call sheet for a class or all students.
Designed for use on trips when offline – print before you go.
"""

from datetime import datetime
from typing import List, Dict


_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 11pt;
    color: #1a1a2e;
    background: #fff;
    padding: 20px;
}
h1 {
    font-size: 18pt;
    font-weight: 800;
    color: #0d1f3c;
    border-bottom: 3px solid #1a3d7c;
    padding-bottom: 8px;
    margin-bottom: 4px;
}
.meta {
    font-size: 9pt;
    color: #4a6fa5;
    margin-bottom: 20px;
}
.student-card {
    border: 1px solid #c0cfe8;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 14px;
    page-break-inside: avoid;
    background: #f8faff;
}
.student-card.flagged {
    border-color: #e07030;
    background: #fff8f2;
}
.student-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 8px;
}
.student-name {
    font-size: 14pt;
    font-weight: 700;
    color: #0d1f3c;
}
.student-meta {
    font-size: 9pt;
    color: #4a6fa5;
}
.badges {
    margin-left: auto;
    display: flex;
    gap: 8px;
}
.badge {
    font-size: 9pt;
    font-weight: 700;
    border-radius: 20px;
    padding: 2px 10px;
}
.badge-praise    { background: #d4f5e2; color: #1a6a30; }
.badge-sanction  { background: #ffe8cc; color: #7a3010; }
.badge-alert     { background: #ffd0d0; color: #8b0000; }
.phones {
    font-size: 10.5pt;
    color: #1a3d7c;
    font-weight: 600;
    margin-bottom: 6px;
}
.phone-row { display: flex; gap: 20px; flex-wrap: wrap; }
.phone-item { white-space: nowrap; }
.phone-label { color: #4a6fa5; font-size: 9pt; font-weight: 400; }
.notes-label {
    font-size: 9pt;
    color: #4a6fa5;
    font-weight: 600;
    margin-top: 6px;
    text-transform: uppercase;
    letter-spacing: .5px;
}
.notes-text { font-size: 10pt; color: #333; }
.call-box {
    border: 1px dashed #b0c0d8;
    border-radius: 6px;
    padding: 6px 12px;
    margin-top: 8px;
    min-height: 40px;
    background: #fff;
}
.call-box-label {
    font-size: 8pt;
    color: #8ab0d8;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .5px;
}
.behaviour-log {
    margin-top: 8px;
    font-size: 9pt;
    color: #333;
}
.behaviour-log table {
    width: 100%;
    border-collapse: collapse;
    font-size: 9pt;
}
.behaviour-log th {
    background: #e8eef8;
    color: #4a6fa5;
    padding: 3px 8px;
    text-align: left;
    font-weight: 600;
}
.behaviour-log td {
    padding: 3px 8px;
    border-bottom: 1px solid #e0e8f0;
}
.praise-row   { color: #1a6a30; }
.sanction-row { color: #7a3010; }
.section-divider {
    margin: 28px 0 16px;
    border-bottom: 2px solid #c0cfe8;
    padding-bottom: 4px;
    font-size: 12pt;
    font-weight: 700;
    color: #1a3d7c;
}
@media print {
    body { padding: 8px; }
    .student-card { page-break-inside: avoid; }
    @page { margin: 15mm; }
}
"""


def _phone_html(phones: List[str]) -> str:
    if not phones:
        return '<span style="color:#aaa;font-style:italic;">No phone numbers recorded</span>'
    items = "".join(
        f'<span class="phone-item"><span class="phone-label">📞 </span>{p}</span>'
        for p in phones
    )
    return f'<div class="phone-row">{items}</div>'


def _behaviour_table_html(behaviours: List[Dict], limit: int = 10) -> str:
    if not behaviours:
        return ""
    rows = ""
    for b in behaviours[:limit]:
        cls = "praise-row" if b["btype"] == "praise" else "sanction-row"
        icon = "✅" if b["btype"] == "praise" else "⚠️"
        date = str(b.get("event_date", ""))[:10]
        reason = b.get("reason", "") or "—"
        pts = b.get("points", 1)
        rows += f'<tr class="{cls}"><td>{icon} {b["btype"].upper()}</td><td>{pts}</td><td>{reason}</td><td>{date}</td></tr>'
    return f"""
    <div class="behaviour-log">
        <table>
            <tr><th>Type</th><th>Pts</th><th>Reason</th><th>Date</th></tr>
            {rows}
        </table>
    </div>"""


def generate_call_sheet(
    students: List[Dict],
    title: str = "Parent Call Sheet",
    include_behaviour_log: bool = True,
    include_call_notes_box: bool = True,
    flagged_threshold: int = 5,
) -> str:
    """
    Build a self-contained HTML string.
    Each student dict must have:
      name, year_group, form_class, phones (list),
      praise, sanctions, notes, behaviours (list of dicts)
    """
    now = datetime.now().strftime("%A %d %B %Y, %H:%M")
    count = len(students)

    # Sort: most sanctions first, then alphabetical
    students = sorted(students, key=lambda s: (-s.get("sanctions", 0), s.get("name", "")))

    cards_html = ""
    for s in students:
        name       = s.get("name", "Unknown")
        year       = s.get("year_group", "")
        form       = s.get("form_class", "")
        phones     = s.get("phones", [])
        praise     = s.get("praise", 0)
        sanctions  = s.get("sanctions", 0)
        notes      = s.get("notes", "") or ""
        behaviours = s.get("behaviours", [])
        flagged    = sanctions >= flagged_threshold

        badge_praise   = f'<span class="badge badge-praise">✅ {praise} praise</span>'
        badge_sanction = f'<span class="badge badge-sanction">⚠ {sanctions} sanctions</span>'
        badge_alert    = (
            f'<span class="badge badge-alert">🚨 High concern</span>'
            if flagged else ""
        )

        notes_section = ""
        if notes:
            notes_section = f'<div class="notes-label">Notes</div><div class="notes-text">{notes}</div>'

        call_box = ""
        if include_call_notes_box:
            call_box = """
            <div class="call-box">
                <div class="call-box-label">Call notes</div>
            </div>"""

        behaviour_section = ""
        if include_behaviour_log and behaviours:
            behaviour_section = _behaviour_table_html(behaviours)

        card_class = "student-card flagged" if flagged else "student-card"
        cards_html += f"""
        <div class="{card_class}">
            <div class="student-header">
                <span class="student-name">{name}</span>
                <span class="student-meta">Year {year} &nbsp;|&nbsp; {form}</span>
                <div class="badges">{badge_praise}{badge_sanction}{badge_alert}</div>
            </div>
            <div class="phones">{_phone_html(phones)}</div>
            {notes_section}
            {behaviour_section}
            {call_box}
        </div>"""

    flagged_count = sum(1 for s in students if s.get("sanctions", 0) >= flagged_threshold)
    summary_bar = f"""
    <div style="background:#f0f4ff;border:1px solid #c0cfe8;border-radius:8px;
                padding:10px 16px;margin-bottom:20px;display:flex;gap:24px;font-size:10pt;">
        <span><b>{count}</b> students</span>
        <span style="color:#7a3010;"><b>{flagged_count}</b> flagged (≥{flagged_threshold} sanctions)</span>
        <span style="color:#4a6fa5;">Generated: {now}</span>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">Generated {now} &nbsp;·&nbsp; {count} students</div>
{summary_bar}
{cards_html}
</body>
</html>"""
