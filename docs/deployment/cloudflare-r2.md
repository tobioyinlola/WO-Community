# Media and file storage on Cloudflare R2

Uploaded files go from the browser straight to R2. The API only reserves the upload, checks the file
and serves links. Only you can do these steps (they need your Cloudflare account).

## What is stored where

| Bucket | Contents | Public? |
|--------|----------|---------|
| `wo-quarantine` | a file waits here until it has been scanned and checked | never |
| `wo-media` | covers, avatars, logos and other images, rebuilt from their pixels | yes, through `media.<your domain>` |
| `wo-private` | support attachments and course documents | never. Members get a signed link that lasts a few minutes |
| `wo-anchor` | the daily audit hash | never, and write once (see below) |

Certificates are generated on demand and handed over through a short lived signed link; none of them
sit in a public bucket.

## Steps

1. In Cloudflare open **R2** and create the four buckets above (choose the location closest to your
   members).
2. **Public images**: on `wo-media` open Settings, Custom Domains, and connect `media.<your domain>`
   (the domain must be on Cloudflare DNS). Do **not** turn on the `r2.dev` public URL.
3. **Credentials**: R2, Manage API tokens, create a token with **Object Read & Write** limited to
   those four buckets. Copy the Access Key ID and Secret Access Key (shown once). Note your account id.
4. **CORS** on `wo-quarantine` (browsers upload to it directly). Settings, CORS policy:

   ```json
   [
     {
       "AllowedOrigins": ["https://app.<your domain>"],
       "AllowedMethods": ["PUT", "POST"],
       "AllowedHeaders": ["*"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

5. **Lifecycle**: on `wo-quarantine` add a rule that deletes objects after 1 day, so an abandoned
   upload does not stay.
6. **Audit anchor**: on `wo-anchor` add a **bucket lock rule** that keeps every object for 7 years
   (R2 does not accept the S3 Object Lock headers the code can send, so the rule does the job).

## Variables (API and worker)

```
STORAGE_ADAPTER=apps.integrations.storage.s3.S3Storage
STORAGE_ENDPOINT_URL=https://<account id>.r2.cloudflarestorage.com
STORAGE_REGION=auto
STORAGE_UPLOAD_METHOD=put
STORAGE_ANCHOR_OBJECT_LOCK=false
STORAGE_ACCESS_KEY_ID=<access key id>
STORAGE_SECRET_ACCESS_KEY=<secret access key>
STORAGE_QUARANTINE_BUCKET=wo-quarantine
STORAGE_MEDIA_BUCKET=wo-media
STORAGE_PRIVATE_BUCKET=wo-private
STORAGE_ANCHOR_BUCKET=wo-anchor
MEDIA_BASE_URL=https://media.<your domain>
```

Why `put`: R2 cannot take the browser form upload (presigned POST) that S3 uses. With `put` the API
signs one upload request whose exact size and type are part of the signature.

## Check

Sign in, upload a profile photo or a course cover, and confirm it shows from
`https://media.<your domain>/...`. A support attachment must open only through a link that expires.
