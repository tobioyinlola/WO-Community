# Email health

**Where:** Admin > Email > Email health. **Who:** community and super admins (`email.health`).

- **Last 30 days:** sent, delivered, bounced, complaints, unsubscribed and suppressed.
- **Setup:** whether the provider key and the webhook secret are set, whether account mail and
  newsletters use separate sending domains, whether a reply address and an https logo are set, and the
  hourly limit while the domain warms up.
- **DNS:** for each sending domain, whether SPF, DKIM and DMARC are published (Good, Needs attention,
  Missing, or Could not check). **Check again** looks again. DMARC on `p=none` shows as Needs attention
  until you tighten it.
- **Recent failures:** bounces and complaints reported by the provider.
- **Suppression list:** addresses we no longer send newsletters to (bounced, complained or
  unsubscribed). Addresses are stored as hashes, so search with the full address. A super admin can
  remove an entry after a fresh two step check; it is audited.

This page cannot see whether the provider has verified your domain or what your sender reputation is.
See [email deliverability](../email-deliverability.md) for the steps only the owner can do.
