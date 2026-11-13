"""HTML rendering of a Report - shared by the Windows app and the web app (same output everywhere)."""
import html

SEV_COLOR = {"acceptable": "#0ca30c", "minor": "#b07800", "major": "#d0612f", "critical": "#d03b3b"}
SEV_ICON = {"acceptable": "✓", "minor": "!", "major": "!!", "critical": "✕"}


def report_html(rep, sec="#52514e", mut="#6d6c66", max_items=3) -> str:
    """sec / mut: colours for secondary and muted text (choose to suit light or dark background)."""
    e = html.escape
    out = [f"<div style='font-family:Segoe UI,system-ui,sans-serif;font-size:10pt;line-height:1.35'>"
           f"<p><b>Overall: <span style='color:{SEV_COLOR[rep.worst]}'>{SEV_ICON[rep.worst]} "
           f"{rep.worst.upper()}</span></b></p>"]
    for r in rep.items:
        col = SEV_COLOR[r["severity"]]
        conf = f" &nbsp;·&nbsp; confidence {r['confidence']:.0%}" if r.get("confidence") is not None else ""
        out.append(f"<table width='100%' cellspacing='0' cellpadding='6' style='margin-bottom:8px;border:none'>"
                   f"<tr><td style='background:{col};width:5px;padding:0'></td><td style='border:none'>"
                   f"<b>#{r['index']} {e(r['name'])}</b> &nbsp;<b style='color:{col}'>"
                   f"{SEV_ICON[r['severity']]} {r['severity'].upper()}</b>{conf}<br>"
                   f"<span style='color:{sec}'>{e(r['severity_basis'])}</span>")
        if r.get("measure"):
            out.append(f"<br><span style='color:{sec}'>{e(r['measure'])}</span>")
        if r["severity"] != "acceptable":
            out.append("<br><b>Likely causes</b><ul style='margin:2px 0'>" + "".join(
                f"<li><i>{e(c['stage'])}</i>: {e(c['cause'])}</li>" for c in r["causes"][:max_items]) + "</ul>")
            out.append("<b>Remedy</b><ul style='margin:2px 0'>" + "".join(
                f"<li>{e(x)}</li>" for x in r["remedy"][:max_items]) + "</ul>")
            out.append("<b>Prevention</b><ul style='margin:2px 0'>" + "".join(
                f"<li>{e(x)}</li>" for x in r["prevention"][:max_items]) + "</ul>")
        out.append("</td></tr></table>")
    for n in rep.notes:
        out.append(f"<p style='color:{sec}'>ℹ {e(n)}</p>")
    out.append(f"<p style='color:{mut};font-size:8pt'>Causes and remedies come from the rule-based "
               "knowledge base (most common causes for this defect type) - confirm on the production line. "
               "Full lists are in the downloadable report.</p></div>")
    return "".join(out)
