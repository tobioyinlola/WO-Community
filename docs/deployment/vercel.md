# Deploying the front end on Vercel

The React app in `frontend/` is a static site. Vercel builds it and serves it at `app.<your domain>`.
Only you can do these steps (they need your Vercel account).

## 1. Import the project

1. In Vercel choose **Add New, Project** and import this repository.
2. Set the **Root Directory** to `frontend`. Vercel detects Vite. `frontend/vercel.json` already sets
   the build command (`npm run build`), the output folder (`dist`), the single page app rewrite (every
   path returns `index.html`, so a refresh on `/app/jobs` works), long caching for built assets and
   basic security headers.
3. Set the production branch to `main`.

## 2. The one variable

| Name | Value | Environments |
|------|-------|--------------|
| `VITE_API_URL` | `https://api.<your domain>` | Production, Preview |

No trailing slash, no path. The build **stops with a clear message** if it is missing, empty, not
https, or points at localhost. That is on purpose: a build without it would call the front end's own
host and get the web page back instead of data.

Vite puts `VITE_` values into the files the browser downloads, so never put a secret in one.

Preview deployments: the API only accepts requests from the origins in `CORS_ALLOWED_ORIGINS`, so a
preview URL cannot sign in unless you add it. Use previews for looking at screens, or add the preview
host to the list while you test.

## 3. The domain

In the project's **Settings, Domains** add `app.<your domain>`. Vercel shows the DNS record to publish
(see [dns.md](dns.md)). It issues the certificate by itself.

## 4. Check

1. Open `https://app.<your domain>` and reload on a deep link such as `/login`. It must show the page,
   not a 404.
2. Open the browser's network tab, sign in, and confirm the requests go to `https://api.<your domain>`
   and succeed (no CORS error).
3. In the browser's cookies for `api.<your domain>` there is a `wo_refresh` cookie that is Secure and
   HttpOnly.

## Build locally the same way

```
cd frontend
VITE_API_URL=https://api.example.com npm run build
```
