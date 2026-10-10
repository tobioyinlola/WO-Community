# 0016. Sign in with Google

Status: accepted (Stage 1)

## Decisions

- **The browser does the Google part; we only check the result.** Google Identity Services gives
  the page an ID token, and the page sends it to `POST /auth/google`. We never handle a Google
  password and need no client secret, only the public client id (`GOOGLE_CLIENT_ID`). Leaving it
  empty switches the feature off (the endpoint answers 404).
- **A token is accepted only if** its signature is Google's (keys fetched from Google and cached
  for an hour), it was issued for our client id, the issuer is Google, it has not expired and, when
  the page sent a `nonce`, the nonce matches. Only RS256 is allowed. Google's address must be
  marked verified, with a real boolean `true`. If Google's keys cannot be fetched the answer is 503,
  never a silent pass.
- **Verification sits behind an adapter** (`GOOGLE_TOKEN_VERIFIER`): the real one, and a fake for
  tests and local work that accepts `fake|subject|email|1|name`. Production refuses to start with
  the fake once a client id is set. The interface lives in `core/identity.py` because `accounts`
  and `integrations` cannot import each other.
- **Who we recognise a person by is Google's stable `sub`**, stored in `SocialIdentity` (unique per
  provider and subject, and one Google login per account). The email address is used once, to find
  an existing account the first time. After that a changed address at Google does not matter.
- **Existing members.** A Google login for an address that already has an account links to it and
  signs the member in. This is safe because Google has proved the mailbox. One trap is closed: if
  the existing account's address was never confirmed, whoever created it may not own the mailbox
  (they could have registered a victim's address with a password they know). Linking then marks the
  address confirmed, **discards that password** and **ends every session** on the account.
  Suspended, removed and rejected accounts cannot sign in this way and are not linked; they get the
  same 401 as a wrong password.
- **New people still wait for an admin.** A Google address we do not know gets
  `409 registration_required` with the address and name Google gave, and nothing is created. The
  page collects the consents and sign-up details and sends them with the same token. The account is
  then created pending, exactly like a password registration: same consents, same profile and
  startup details, same admin approval. It is signed in (as pending) straight away, and no
  verification email is sent because Google already confirmed the address. A valid invitation for
  that address approves it on the spot, as it does for password sign-up.
- **Second factor still applies.** After Google, an account with MFA gets the same `202` challenge
  as a password login and finishes at `POST /auth/mfa/verify`. Google never counts as a second
  factor. Admin accounts therefore still need MFA before any admin action.
- **Accounts created with Google have no password** (unusable until they use "forgot password",
  which still works and gives them one).
- **Rate limit** 30 per minute per client (`auth_google`), on top of the anonymous limit.

## Consequences

Google is the only provider; `SocialIdentity.provider` leaves room for others. Unlinking a Google
login, and the admin console showing which members use it, are not built. The browser side
(button, nonce generation) is the frontend's job: it should generate a random `nonce`, pass it to
Google and to us.
