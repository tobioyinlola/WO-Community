# Deployment

The back end (`backend/`) runs on Railway, the front end (`frontend/`) on Vercel, mail goes through
Resend and files sit in Cloudflare R2. The app is at `app.<domain>` and the API at `api.<domain>`.

| Read | For |
|------|-----|
| [audit.md](audit.md) | What assumed a developer machine, and what was changed |
| [railway.md](railway.md) | API, worker (Celery and scheduler), PostgreSQL, Redis, ClamAV, variables |
| [vercel.md](vercel.md) | The front end and `VITE_API_URL` |
| [cloudflare-r2.md](cloudflare-r2.md) | Buckets, public images, private files, CORS |
| [resend.md](resend.md) | Sending, webhook, suppression, warm up |
| [dns.md](dns.md) | Every DNS record |
| [go-live-checklist.md](go-live-checklist.md) | The order to do it in, the smoke test, rollback |
| [local-production-run.md](local-production-run.md) | Running production style settings on your machine |
| [../deployment.md](../deployment.md) | What the app needs from any host (processes, buckets, egress) |
| [../email-deliverability.md](../email-deliverability.md) | SPF, DKIM, DMARC and warm up in depth |

Every variable, with a comment, is in `backend/.env.example` and `frontend/.env.example`.
