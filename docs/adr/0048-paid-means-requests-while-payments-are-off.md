# 0048. While payments are off, paid means a request the owner confirms

Status: accepted

## Context

Courses and mentoring sessions can carry a price, but online payment is not switched on
(`FEATURE_PAYMENTS_ENABLED` is false). A price with nothing to pay it with must not look like a
checkout, and it must not silently give the thing away either.

## Decision

- **Courses.** A paid course shows its price. A member asks for access (`POST /courses/{id}/request-access`),
  an administrator approves or declines, and approval enrols them. Nothing is charged.
- **Mentoring.** A mentor sets Free or Paid, a price per session (and optionally per length) and a currency
  from NGN, USD, KES, GHS, ZAR, EGP, GBP and EUR. A mentee books a paid time exactly like a free one: the
  booking is a request the mentor confirms. The price is shown to the mentee beforehand and kept on the
  session (`price_minor`, `currency`, `payment_mode`), and every screen and notice that mentions it says
  **Payment arranged directly**. The mentor and mentee settle the fee between themselves.
- **One place decides.** `apps.mentorship.setup.quote()` returns the price and how it is settled. Today the
  mode is always `arranged`. When payments arrive, a payment step attaches there, between the request and the
  confirmation, without changing the session model or the booking calls.
- **Prices are whole numbers in the smallest unit** (kobo, cents), never floats.

## Consequences

Nothing is collected, refunded or reconciled by the platform, so there is nothing to certify for payments yet.
Members can see what something costs and ask for it; owners keep control of who gets it.
