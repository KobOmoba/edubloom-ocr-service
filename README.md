# EduBloom OCR Service — Handover / Status

> **For any Claude picking this up:** read this section first. It tells you
> exactly where things stand, what's decided, what's blocked, and what to do
> next — without needing the person to re-explain anything.

---

## 🟡 CURRENT STATUS (as of this write)

**Phase:** Service code is built and pushed. **Blocked on Bayo provisioning
the Oracle Cloud VPS** — nothing further can happen until that exists.

**What's done:**
- ✅ `main.py` — PaddleOCR FastAPI service, column-aware ledger parsing
- ✅ `requirements.txt` — pinned deps
- ✅ `deploy.sh` — one-shot install/deploy script for Ubuntu 22.04 ARM
- ✅ Repo created: `github.com/KobOmoba/edubloom-ocr-service`

**What's NOT done yet:**
- ⬜ Oracle VPS is not provisioned yet (Bayo's action — see "What Bayo needs
  to do" below)
- ⬜ Service has never been deployed or tested against a real ledger photo
- ⬜ `bloom-agent-v2/app.js` has NOT been wired to call this service yet —
  it still uses the old browser-side Groq/Mistral/Together/HF cascade
- ⬜ Basic vs Premium OCR gating (decided, not yet built — see Decisions
  Log below)

**Next action for whoever picks this up:** ask Bayo if the Oracle VPS is
live yet. If yes, get the public IP, deploy via `deploy.sh`, test
`/health`, then wire `bloom-agent-v2/app.js` to call it. If no, nothing
else to do here yet — don't start rebuilding the cascade logic again.

---

## 📋 DECISIONS LOG (do not re-litigate these — they were explicitly decided)

1. **Browser-side vision API cascade (Groq/Mistral/Together/HuggingFace)
   was abandoned.** It was unreliable in practice across many test rounds.
   Do not resurrect it as the primary approach.
2. **PaddleOCR chosen over EasyOCR** — runs server-side on Oracle VPS
   (free-tier Ampere ARM instance), not in-browser.
3. **Why server-side, not browser:** removes dependency on 4 flaky free
   third-party APIs, removes client-side image-compression bugs that broke
   things repeatedly, gives full control.
4. **Pricing/tier gating (locked decision):**
   - **Basic plan** → free PaddleOCR cascade only (this service)
   - **Premium plan** → PaddleOCR first, falls back to paid GPT-4o-mini
     vision if PaddleOCR returns 0 students
   - **Agent app (signboard + ledger during onboarding) is NOT gated** —
     it's the sales tool that demonstrates OCR value to get principals to
     upgrade, so it must always work regardless of plan.
5. **Manual typing stays a Basic-tier feature, not free** — Basic is not
   the free plan, it's the base paid plan. "Free" was never on the table.
6. **Cost at scale was modeled and is a non-issue:** even at 100,000
   schools nationally, PaddleOCR is $0 (self-hosted) and GPT-4o-mini
   fallback tops out around ₦1.8M total — trivial against revenue at that
   scale. This is why paid fallback is fine to keep, restricted to Premium.
7. **Manual entry OCR (Add Expense, Add Student, etc. in the school app)
   is the eventual goal** — mirrors BOOKKEEPA's snap-to-fill UX — but
   `bloom-school-v2` has no `app.js` yet (only `index.html`). This is
   future work, not current scope.

---

## 🔲 WHAT BAYO NEEDS TO DO (blocking, his action only)

1. Sign up at oracle.com/cloud/free
2. Create instance: Compute → Create Instance → **Ampere A1 (ARM)** →
   Ubuntu 22.04 → shape 4 OCPU / 24GB (Always Free tier)
3. Get the instance's **Public IP**
4. Send that IP to whichever Claude is helping next

Everything after that point is buildable by Claude via deploy.sh + wiring
the app — no further manual steps needed from Bayo except opening port 80
in the Oracle VCN Security List (deploy.sh prints this reminder).

---

## 🏗️ ARCHITECTURE

```
bloom-agent-v2 (browser)
       │
       ▼  POST /scan-ledger  { image: base64 }
Oracle VPS ── nginx :80 → uvicorn :8000 → PaddleOCR service (this repo)
       │
       ▼
{ detected_class, students: [...] }
```

**Why coordinate-based parsing works where the old approach didn't:**
PaddleOCR returns the actual (x,y) pixel location of every detected text
box. `main.py` groups boxes into rows by y-position, then sorts each row
by x-position — reconstructing true column order (Serial → Surname →
Firstname → Balance → Fees → Total) from real geometry. The old
browser-side vision-LLM cascade only had linear text output with no
column guarantees, which is why it failed on 14-column ledgers.

---

## 🚀 DEPLOY (once Oracle IP exists)

```bash
git clone https://github.com/KobOmoba/edubloom-ocr-service.git
cd edubloom-ocr-service
bash deploy.sh
```
Then open port 80 in Oracle Console: **Networking → Virtual Cloud
Networks → your VCN → Security Lists → Add Ingress Rule** — Source
`0.0.0.0/0`, Port `80`.

Test: `http://<vps-ip>/health` → should return `{"status":"ok","engine":"PaddleOCR"}`

---

## 📡 API

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

---

## 🔜 AFTER DEPLOY — remaining build steps in order

1. Deploy + test `/health` and `/scan-ledger` against a real ledger photo
2. Wire `bloom-agent-v2/app.js`: replace/augment the ledger cascade to
   call this VPS endpoint first
3. Add Basic/Premium gate: Premium falls back to GPT-4o-mini if
   PaddleOCR returns 0 students; Basic does not
4. Bump `index.html` cache version (`app.js?v=N` → `N+1`) — required
   every time `app.js` changes or Bayo's browser won't see the update
5. Once proven stable on agent app, revisit school-app OCR entry points
   (blocked until `bloom-school-v2/app.js` exists)
