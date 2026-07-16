"""
EduBloom PaddleOCR Ledger Service
Runs on Oracle Cloud VPS — replaces browser-side Groq/Mistral/Together/HF cascade
for ledger scanning. Free forever, no per-token cost, full control.

Endpoint: POST /scan-ledger
Body: { "image": "<base64 jpeg>" }
Returns: { "detected_class": "...", "students": [ {name, balance_bf, termFees, total, fully_paid} ] }
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from paddleocr import PaddleOCR
import base64, io, re, cv2, numpy as np
from PIL import Image

app = FastAPI(title="EduBloom OCR Service")

# Load once at startup — English + structure-aware (PP-Structure for table detection)
ocr_engine = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=False, show_log=False)

class ScanRequest(BaseModel):
    image: str  # base64, no data: prefix

class ScanResponse(BaseModel):
    detected_class: str = ""
    students: list = []
    raw_lines: int = 0

# ── Column-aware ledger parsing ──────────────────────────────────────────
# PaddleOCR returns [ [box_points, (text, confidence)], ... ] — box has
# x,y coordinates. We group by row (similar y) then sort each row by x
# to reconstruct column order — same principle as the browser OpenCV crop,
# but done properly with real coordinate data instead of guessing.

def group_into_rows(ocr_result, y_tolerance=15):
    """Group OCR boxes into rows based on vertical (y) position."""
    items = []
    for box, (text, conf) in ocr_result:
        cy = sum(p[1] for p in box) / 4
        cx = sum(p[0] for p in box) / 4
        items.append({'text': text.strip(), 'x': cx, 'y': cy, 'conf': conf})

    items.sort(key=lambda i: i['y'])
    rows = []
    current_row = []
    last_y = None
    for item in items:
        if last_y is None or abs(item['y'] - last_y) <= y_tolerance:
            current_row.append(item)
        else:
            if current_row:
                rows.append(sorted(current_row, key=lambda i: i['x']))
            current_row = [item]
        last_y = item['y']
    if current_row:
        rows.append(sorted(current_row, key=lambda i: i['x']))
    return rows

NIGERIAN_NAME_HINT = re.compile(r'^[A-Za-z][A-Za-z\'\-]{2,}$')
NUMBER_RE = re.compile(r'^[\d,]+$')

def parse_ledger_rows(rows):
    """
    Heuristic column mapping for the standard ledger layout:
    Col pattern (left to right): Serial | Surname | Firstname | Balance | Fees | Total | ...payments
    We only need columns 1-5 (name + balance + fees).
    """
    students = []
    detected_class = ""

    for row in rows:
        texts = [r['text'] for r in row]
        joined = ' '.join(texts).upper()

        # Header/class line detection
        if 'CLASS' in joined and detected_class == "":
            m = re.search(r'CLASS[:\s]+([A-Z0-9\- ]+)', joined)
            if m: detected_class = m.group(1).strip()
            continue
        if any(kw in joined for kw in ['SERIAL', 'NAMES', 'BALANCE FROM', 'CURRENT TERM', 'YEAR', 'TERM ']):
            continue  # header row

        # Must start with a serial number
        if not texts or not re.match(r'^\d{1,2}\.?$', texts[0]):
            continue

        # Extract name tokens (alphabetic, not pure numbers) from the row,
        # stopping once we hit the first numeric token (start of fee columns)
        name_tokens = []
        remaining = texts[1:]
        idx = 0
        for t in remaining:
            if NUMBER_RE.match(t.replace(',', '')):
                break
            if NIGERIAN_NAME_HINT.match(t):
                name_tokens.append(t)
            idx += 1

        if not name_tokens:
            continue

        name = ' '.join(name_tokens).upper()
        numeric_tokens = [t.replace(',', '') for t in remaining[idx:] if NUMBER_RE.match(t.replace(',', ''))]
        nums = [int(n) for n in numeric_tokens if n.isdigit()]

        balance_bf = nums[0] if len(nums) >= 3 else 0
        term_fees  = nums[1] if len(nums) >= 3 else (nums[0] if nums else 0)
        total      = nums[2] if len(nums) >= 3 else term_fees
        fully_paid = 'FULLY' in joined or 'PAID' in joined

        students.append({
            "name": name,
            "balance_bf": balance_bf,
            "termFees": term_fees,
            "total": total,
            "fully_paid": fully_paid
        })

    return detected_class, students

@app.post("/scan-ledger", response_model=ScanResponse)
async def scan_ledger(req: ScanRequest):
    try:
        img_bytes = base64.b64decode(req.image)
        pil_img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # Light preprocessing — grayscale + CLAHE contrast, same principle
        # as the earlier browser OpenCV step, done properly server-side
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        result = ocr_engine.ocr(enhanced_bgr, cls=True)
        if not result or not result[0]:
            return ScanResponse(detected_class="", students=[], raw_lines=0)

        rows = group_into_rows(result[0])
        detected_class, students = parse_ledger_rows(rows)

        return ScanResponse(
            detected_class=detected_class,
            students=students,
            raw_lines=len(rows)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok", "engine": "PaddleOCR"}
