"""HTML rendering of a Report - used for saved reports and the Gradio web app (fern theme, light)."""
import html
from src.app.verdict import SEV_LABEL

# severity colours are separate from the brand green (spec v2, section 6)
SEV_COLOR = {"acceptable": "#0f7a5c", "minor": "#a86f12", "major": "#cf5a24", "critical": "#c23a3a"}
SEV_ICON = {"acceptable": "✓", "minor": "!", "major": "!!", "critical": "✕"}
NEUTRAL = "#4d5c52"       # "no defects detected" / "cannot analyse": never green


def verdict_html(rep) -> str:
    v, e = rep.verdict, html.escape
    col = SEV_COLOR[v["severity"]] if v["severity"] else ("#c23a3a" if v["state"] == "cannot" else NEUTRAL)
    chip = (f"<span style='background:{col};color:#fff;padding:2px 8px;font-size:8pt'>"
            f"<b>{SEV_LABEL[v['severity']].upper()}</b></span>&nbsp; ") if v["severity"] else ""
    return (f"<p style='margin:0 0 8px 0'>{chip}<b style='font-size:12pt;color:{col if not v['severity'] else '#15211a'}'>"
            f"{e(v['title'])}</b><br><span style='color:{NEUTRAL}'>{e(v['detail'])}</span></p>")


def report_html(rep, sec="#4d5c52", mut="#6d7a70", max_items=3) -> str:
    """sec / mut: colours for secondary and muted text (choose to suit light or dark background)."""
    e = html.escape
    out = ["<div style='font-family:Segoe UI,system-ui,sans-serif;font-size:10pt;line-height:1.35'>", verdict_html(rep)]
    for r in rep.items:
        col = SEV_COLOR[r["severity"]]
        conf = f" &nbsp;·&nbsp; confidence {r['confidence']:.0%}" if r.get("confidence") is not None else ""
        pts = f" &nbsp;·&nbsp; {r['points']} pt" if r.get("points") is not None else ""
        out.append(f"<table width='100%' cellspacing='0' cellpadding='6' style='margin-bottom:8px;border:none'>"
                   f"<tr><td style='background:{col};width:5px;padding:0'></td><td style='border:none'>"
                   f"<b>#{r['index']} {e(r['name'])}</b> &nbsp;<b style='color:{col}'>"
                   f"{SEV_LABEL[r['severity']].upper()}</b>{pts}{conf}<br>"
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
    if rep.items:
        out.append(f"<p style='color:{mut};font-size:8pt'>Causes and remedies come from the rule-based "
                   "knowledge base (most common causes for this defect type) - confirm on the production line. "
                   "Full lists are in the downloadable report.</p>")
    out.append("</div>")
    return "".join(out)
