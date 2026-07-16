# EduBloom OCR Service

PaddleOCR ledger-scanning service. Runs on Oracle Cloud VPS — replaces the
browser-side Groq/Mistral/Together/HuggingFace cascade for reading Nigerian
school fee ledgers.

## Why this exists
The browser-side vision API cascade was unreliable. This service moves OCR
processing to a dedicated server using PaddleOCR, which reads real (x,y)
coordinates for each detected text box — allowing proper column
reconstruction (Serial → Name → Balance → Fees → Total) instead of guessing
column order from linear text output.

## Deploy (one-time setup on a fresh Oracle Ubuntu 22.04 ARM instance)

1. SSH into your instance (or use Cloud Shell in the browser).
2. Clone this repo:
   ```
   git clone https://github.com/KobOmoba/edubloom-ocr-service.git
   cd edubloom-ocr-service
   ```
3. Run the deploy script:
   ```
   bash deploy.sh
   ```
4. In Oracle Cloud Console: **Networking → Virtual Cloud Networks → your VCN
   → Security Lists → Add Ingress Rule** — Source `0.0.0.0/0`, Port `80`.
5. Test from any browser: `http://<your-vps-ip>/health` should return
   `{"status":"ok","engine":"PaddleOCR"}`.

## API

**POST** `/scan-ledger`
```json
{ "image": "<base64-encoded JPEG, no data: prefix>" }
```

Returns:
```json
{
  "detected_class": "K-G",
  "students": [
    {"name":"OLIYIDE GODWIN","balance_bf":0,"termFees":24000,"total":24000,"fully_paid":true}
  ],
  "raw_lines": 14
}
```

## Wiring into bloom-agent-v2
`app.js` calls this endpoint as part of the free-tier cascade (Basic plan),
before falling back to paid vision APIs (GPT-4o-mini) reserved for Premium.
