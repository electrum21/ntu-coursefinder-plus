from flask import Flask, request, jsonify, Response, send_from_directory
import requests as req
from bs4 import BeautifulSoup
import json, time, re, os, threading
from datetime import datetime

app = Flask(__name__, static_folder=".")

SSO_STEP1_URL    = "https://sso.wis.ntu.edu.sg/webexe88/owa/sso_login1.asp"
SSO_STEP2_URL    = "https://sso.wis.ntu.edu.sg/webexe88/owa/sso_login2.asp"
SSO_STEP3_URL    = "https://sso.wis.ntu.edu.sg/webexe88/owa/sso.asp"
COURSEFINDER_URL = "https://wis.ntu.edu.sg/pls/lms/instep_past_subj_matching.show_rec2"

DELAY_UNI     = 1.5
DELAY_COUNTRY = 2.0

COUNTRIES = [
    "AUSTRALIA", "AUSTRIA", "BELGIUM", "BRUNEI", "CANADA", "CHINA",
    "CZECHIA", "DENMARK", "FINLAND", "FRANCE", "GERMANY", "HONG KONG",
    "HUNGARY", "INDONESIA", "IRELAND", "ITALY", "JAPAN",
    "KOREA, REPUBLIC OF", "LUXEMBOURG", "MACAO", "NETHERLANDS",
    "NEW ZEALAND", "NORWAY", "POLAND", "SPAIN", "SWEDEN", "SWITZERLAND",
    "TAIWAN", "THAILAND", "TURKIYE", "UNITED KINGDOM",
    "UNITED STATES OF AMERICA", "VIETNAM",
]

_sessions: dict[str, dict] = {}
_lock = threading.Lock()

def _new_http_session() -> req.Session:
    s = req.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return s

@app.route("/")
def index():
    return send_from_directory(".", "coursefinder_viewer.html")

@app.route("/api/countries")
def api_countries():
    return jsonify(COUNTRIES)

@app.route("/api/login", methods=["POST"])
def api_login():
    body       = request.json or {}
    student_id = body.get("student_id", "").strip()
    matric_no  = body.get("matric_no", "").strip()
    password   = body.get("password", "")
    if not student_id or not matric_no or not password:
        return jsonify({"ok": False, "error": "Missing credentials"}), 400
    session = _new_http_session()
    ok, error = _login(session, student_id, password)
    if not ok:
        return jsonify({"ok": False, "error": error}), 401
    import secrets
    token = secrets.token_hex(16)
    with _lock:
        _sessions[token] = {"session": session, "matric_no": matric_no}
    return jsonify({"ok": True, "token": token})

@app.route("/api/universities", methods=["POST"])
def api_universities():
    body    = request.json or {}
    token   = body.get("token", "")
    country = body.get("country", "").strip()
    ctx = _sessions.get(token)
    if not ctx:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    unis = _get_universities(ctx["session"], country, ctx["matric_no"])
    return jsonify({"ok": True, "universities": unis})

@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    body          = request.json or {}
    token         = body.get("token", "")
    plan          = body.get("plan", {})
    course_filter = (body.get("course_filter") or "").strip().upper()
    ctx = _sessions.get(token)
    if not ctx:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    session   = ctx["session"]
    matric_no = ctx["matric_no"]
    total_unis = sum(len(v) for v in plan.values())

    def generate():
        all_records = []
        done_unis   = 0
        def event(kind, **kwargs):
            return f"data: {json.dumps({'type': kind, **kwargs})}\n\n"
        yield event("start", total=total_unis)
        for country, unis in plan.items():
            yield event("country", country=country, count=len(unis))
            for uni in unis:
                yield event("uni_start", country=country, uni=uni)
                records = _scrape(session, country, uni, matric_no)
                if course_filter:
                    records = [r for r in records if r["ntu_code"].upper().startswith(course_filter)]
                all_records.extend(records)
                done_unis += 1
                yield event("uni_done", country=country, uni=uni,
                            count=len(records), done=done_unis, total=total_unis)
                time.sleep(DELAY_UNI)
            time.sleep(DELAY_COUNTRY)
        meta = {
            "scraped_at":    datetime.now().isoformat(),
            "course_filter": course_filter or "ALL",
            "total":         len(all_records),
            "countries":     {c: list(us) for c, us in plan.items()},
        }
        yield event("done", total=len(all_records),
                    data={"meta": meta, "records": all_records})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _login(session, student_id, password):
    try:
        resp1 = session.get(f"{SSO_STEP1_URL}?t=1&p2={COURSEFINDER_URL}", timeout=15)
    except req.RequestException as e:
        return False, f"Could not reach SSO: {e}"
    time.sleep(0.5)
    html1 = resp1.text
    if 'name="pin"' not in html1.lower():
        try:
            resp1 = session.post(SSO_STEP2_URL, data={
                "UserName": student_id, "Domain": "STUDENT", "bOption": "OK",
                "p2": COURSEFINDER_URL, "p2_len": str(len(COURSEFINDER_URL)),
                "t": "2", "extra": "", "extra_len": "0",
                "map": "", "map_len": "0", "pg": "", "pg_len": "0",
                "title": "", "title_len": "0",
            }, timeout=20, allow_redirects=True)
            resp1.raise_for_status()
            html1 = resp1.text
        except req.RequestException as e:
            return False, f"Username step failed: {e}"
    if 'name="pin"' not in html1.lower():
        return False, "Could not reach password form"
    soup = BeautifulSoup(html1, "html.parser")
    form = soup.find("form", {"name": "frmLogin"})
    if not form:
        return False, "Could not find login form"
    hidden = {}
    for inp in form.find_all("input"):
        if inp.get("type", "").lower() == "hidden":
            n = inp.get("name", "")
            if n:
                hidden[n] = inp.get("value", "")
    hidden["UserName"] = student_id
    action = form.get("action", SSO_STEP3_URL)
    if not action.startswith("http"):
        action = "https://sso.wis.ntu.edu.sg/webexe88/owa/" + action
    try:
        resp2 = session.post(action, data={**hidden, "PIN": password, "bOption": "OK"},
                             timeout=20, allow_redirects=True)
        resp2.raise_for_status()
    except req.RequestException as e:
        return False, f"Password step failed: {e}"
    html2 = resp2.text.lower()
    if "invalid" in html2 or "incorrect" in html2 or "login failed" in html2:
        return False, "Wrong Student ID or password"
    if 'name="pin"' in html2 and "coursefinder" not in html2:
        return False, "Login failed — still on password page"
    try:
        session.get(COURSEFINDER_URL, timeout=15, allow_redirects=True)
    except req.RequestException:
        pass
    return True, None


def _get_universities(session, country, matric_no):
    try:
        resp = session.post(COURSEFINDER_URL, data={
            "which_cty": country, "which_uni_val": "", "search_option": "1",
            "which_course": "ALL", "which_course2": "ALL",
            "p1": matric_no, "p2": "", "p_type": "INSTEP",
        }, timeout=20)
        resp.raise_for_status()
    except req.RequestException:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    sel  = soup.find("select", {"name": "which_uni_val"})
    if not sel:
        return []
    return [opt.get("value", "").strip()
            for opt in sel.find_all("option")
            if opt.get("value", "").strip().upper() not in ("", "ALL")]


_LABEL_TO_FIELD = {
    "URL for course info":                                         "url",
    "Course Content/Syllabus":                                     "syllabus",
    "Total number of contact hours for the entire course":         "contact_hours",
    "Prescripted Textbooks & Chapters Covered":                    "textbooks",
    "Mode of Assessment":                                          "assessment",
    "Number of Credits awarded by Host University to this course": "credits",
    "Student's Comments":                                          "comments",
    "Teaching Staff Details":                                      "staff",
    "NTU coordinator remarks":                                     "coordinator_remarks",
}

_DATA_CLASSES = {"row0", "row1"}


def _scrape(session, country, uni, matric_no):
    try:
        resp = session.post(COURSEFINDER_URL, data={
            "which_cty": country, "which_uni_val": uni, "search_option": "1",
            "which_course": "ALL", "which_course2": "ALL",
            "p1": matric_no, "p2": "", "p_type": "INSTEP",
        }, timeout=30)
        resp.raise_for_status()
    except req.RequestException:
        return []
    return _parse(resp.text, country, uni)


def _parse(html, country, uni):
    soup    = BeautifulSoup(html, "html.parser")
    records = []

    for table in soup.find_all("table"):
        all_rows = table.find_all("tr")
        headers  = []

        for idx, row in enumerate(all_rows):
            cells = row.find_all(["td", "th"])
            texts = [c.get_text(" ", strip=True) for c in cells]

            # Header row
            if any(t in texts for t in ["NTU Course Code", "NTU Code",
                                        "Host Course Code", "Status"]):
                headers = texts
                continue

            if not headers:
                continue

            # Must be a data row (class row0/row1)
            cls = set(row.get("class") or [])
            if not (cls & _DATA_CLASSES):
                continue

            # Skip rows with too few cells or an oversized first cell
            if len(texts) < 4 or not texts[0] or len(texts[0]) > 15:
                continue

            # Must contain an approval status somewhere
            status_raw = next(
                (t for t in texts if "approv" in t.lower() or "reject" in t.lower()),
                ""
            )
            if not status_raw:
                continue

            # Column mapping via headers
            ntu_code     = _col(headers, texts, "NTU Course Code", "NTU Code")
            ntu_name     = _col(headers, texts, "NTU Course Name", "NTU Name", "NTU Course")
            ntu_type     = _col(headers, texts, "NTU Course Type", "Course Type", "Type")
            foreign_code = _col(headers, texts, "Foreign Course Code", "Host Course Code",
                                "Foreign Code", "Host Code")
            foreign_name = _col(headers, texts, "Foreign Course Name", "Host Course Name",
                                "Foreign Name", "Host Name")
            au           = _col(headers, texts, "AU", "Academic Unit", "Units")
            status       = _col(headers, texts, "Status", "Outcome", "Approval")
            year         = _col(headers, texts, "Year", "AY")
            sem          = _col(headers, texts, "Semester", "Sem")

            # Positional fallback when headers don't match
            if not ntu_code:
                if len(texts) >= 9:
                    ntu_code, ntu_name, ntu_type = texts[0], texts[1], texts[2]
                    foreign_code, foreign_name   = texts[3], texts[4]
                    au, status, year, sem        = texts[5], texts[6], texts[7], texts[8]
                elif len(texts) >= 6:
                    ntu_code = texts[0]
                    status   = status_raw

            if not ntu_code or len(ntu_code) > 15:
                continue

            sl = (status or "").lower()
            if "approv" not in sl and "reject" not in sl:
                continue

            status = "Approved" if "approv" in sl else "Rejected"
            year_m = re.search(r"\d{4}", str(year))
            year_n = int(year_m.group()) if year_m else 0
            sem_m  = re.search(r"\d", str(sem))
            sem_s  = sem_m.group() if sem_m else ""

            # Look at the next row for a toggleTextN detail block
            details = _empty_details()
            if idx + 1 < len(all_rows):
                next_row   = all_rows[idx + 1]
                next_cells = next_row.find_all("td")
                if (len(next_cells) == 1
                        and next_cells[0].get("colspan") == "10"):
                    div = next_cells[0].find(
                        "div", id=re.compile(r"^toggleText"))
                    if div:
                        details = _extract_details(div)

            records.append({
                "ntu_code":      ntu_code,
                "ntu_name":      ntu_name,
                "ntu_type":      ntu_type,
                "foreign_code":  foreign_code,
                "foreign_name":  foreign_name,
                "au":            au,
                "status":        status,
                "year":          year_n,
                "sem":           sem_s,
                "country":       country,
                "host_uni":      uni,
                **details,
            })

    # De-duplicate
    seen, out = set(), []
    for r in records:
        key = (f"{r['ntu_code']}|{r['foreign_code']}|"
               f"{r['year']}|{r['sem']}|{r['status']}")
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _col(headers, texts, *names):
    """Return texts[i] for the first header that contains any of the given names."""
    for name in names:
        for i, h in enumerate(headers):
            if name.lower() in h.lower() and i < len(texts):
                return texts[i]
    return ""


def _empty_details():
    return {"url": "", "syllabus": "", "contact_hours": "", "textbooks": "",
            "assessment": "", "credits": "", "comments": "", "staff": "",
            "coordinator_remarks": ""}


def _extract_details(div):
    details = _empty_details()

    nodes = list(div.descendants)

    b_positions = []
    for idx, node in enumerate(nodes):
        if getattr(node, "name", None) == "b":
            label = node.get_text(strip=True).rstrip(":").strip()
            field = _LABEL_TO_FIELD.get(label)
            if field:
                b_positions.append((idx, field))

    for pos, (b_idx, field) in enumerate(b_positions):
        next_b_idx = b_positions[pos + 1][0] if pos + 1 < len(b_positions) else len(nodes)

        from bs4 import NavigableString
        fragments = [
            str(nodes[i])
            for i in range(b_idx + 1, next_b_idx)
            if isinstance(nodes[i], NavigableString)
            and getattr(nodes[i].parent, "name", None) != "b"
        ]

        value = " ".join(fragments).split()   # collapse whitespace
        value = " ".join(value).strip()
        # Strip a stray leading colon: "Label: value" → ": value" after <b> removed
        value = re.sub(r"^\s*:\s*", "", value).strip()

        if field == "url":
            if not value.startswith("http"):
                value = ""
            else:
                value = value.split()[0]

        if value and not details[field]:
            details[field] = value

    return details


if __name__ == "__main__":
    print("=" * 55)
    print("  NTU CourseFinder — Local Server")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 55)
    app.run(debug=False, port=5000, threaded=True)