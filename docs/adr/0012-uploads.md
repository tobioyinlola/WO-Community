# 0012. Uploads and image processing

Status: accepted (Stage 1)

## Flow

1. `POST /uploads` (purpose, declared type, size) validates against an allow-list (JPEG, PNG, WebP;
   1 byte to 5 MB), applies a daily quota (20) and an hourly rate limit (30), and returns a
   pre-signed form. The storage service itself enforces the type and a `content-length-range`
   condition, so the API never proxies bytes and cannot be made to buffer a large file.
2. The browser posts the file to the **quarantine** bucket under a random key
   (`<purpose>/<160 random bits>`). Nothing the client sent (name, owner id) is part of any key.
3. `POST /uploads/{id}/complete` checks the object exists and fits its declared size, then queues
   processing through the outbox (calling it twice queues once).
4. A worker on the `media` queue reads the file and: scans it for malware, checks that the bytes are
   really the declared type and a decodable image, rejects absurd dimensions and decompression
   bombs, applies the EXIF orientation, and **re-encodes** the pixels to WebP in two sizes (1600 px
   and 320 px, never enlarged). Metadata, scripts and data hidden after the image do not survive
   re-encoding. Only the copies are written to the **media** bucket, under a new random key, with
   immutable cache headers. The raw file is then deleted.
5. The owner polls `GET /uploads/{id}`. `urls` appear only when the status is `ready`; a pending,
   processing, rejected or expired upload never exposes an address.
6. `PUT /me/profile/photo` and `PUT /startups/{id}/logo` attach a ready upload. It must be the
   caller's own, made for that purpose, and unused. Replacing or removing an image deletes its
   files (after the change commits) and marks the upload discarded.

## Decisions

- **Failure is closed.** If the scanner cannot answer, nothing is published: the task is retried
  with backoff and, if it never recovers, an hourly job rejects the upload after two hours
  (`processing_timeout`). A scanner outage can delay uploads but never lets one through.
- **Rejections are specific and safe to show:** `type_mismatch`, `not_an_image`,
  `too_large_dimensions`, `size_mismatch`, `malware_detected`, `processing_timeout`. A detection is
  logged and written to the audit log with the signature and owner.
- **Image URLs are stable public addresses**, not signed per request: processed files sit in the media
  bucket behind a separate cookieless domain with unguessable keys, which keeps public pages
  cacheable. Visibility is enforced by whether the API reveals the address (the photo and logo
  belong to the *basics* group). An address that was already shared stays valid until the image is
  replaced or removed, when the object is deleted. This follows the "public assets on a cookieless
  domain" rule; documents or other private files will need signed URLs when they are added.
- **Housekeeping** (hourly): expire uploads that never completed, reject stuck ones, delete ready
  files nobody attached after 24 hours, and purge finished records after 7 days.
- **Adapters.** `ObjectStorage` (S3 compatible: AWS, MinIO, R2) and `MalwareScanner` (ClamAV through
  `clamd`'s INSTREAM protocol) sit behind interfaces with in-memory fakes used by every other test.
  The S3 adapter is tested against botocore's stubber and real request signing; the ClamAV client
  against a local socket that speaks the protocol. Production refuses to start unless
  `STORAGE_ADAPTER`, `MALWARE_SCANNER` and `MEDIA_BASE_URL` are set, so it cannot run on the fakes.

## Consequences

Setup needed outside the code: a private quarantine bucket with a lifecycle rule that deletes objects
after a day (a backstop for the hourly job), a media bucket served through the CDN on its own domain,
bucket CORS allowing `POST` from the web origin, and a ClamAV daemon reachable from the media
workers. Only images are supported; documents (PDF and office files) for posts and course assets
will reuse the same flow with their own purposes, allow-lists and, for private files, signed URLs.
The completeness scores gained a photo and logo component (15 and 10 points).
