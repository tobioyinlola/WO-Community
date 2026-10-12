# Referrals

**Sign up.** The last step of the sign up form asks "Who referred you?" before the agreements. It is
optional. The choices are a WO Community member, social media, an event or demo day, a partner
organisation, a search engine, the newsletter, or other. For a member the person searches by name (or
by an email address typed in full) and picks them; if they cannot be found they can type a name. The
other choices that make sense take a few words (which platform, which event). A wrong or half filled
answer never blocks the registration: it is simply not kept.

**Links.** Every account has a short code (eight characters, no 0, 1, I or O). `/join?ref=CODE`
keeps the code for the visit and opens sign up with "A WO Community member" and that member chosen;
the applicant can change it. The code that was used is stored even if they change the answer. A
member sees the link, a Copy link button and the people who joined through them on their home page
and on their profile, with a plain line such as "3 members joined through you". Nothing is ranked.

**Finding a member while signing up.** The search is open to people with no account, so it is narrow:
at least three characters, at most five answers, only members whose name is public (a member who
keeps their name from visitors cannot be found, but their link still works), and an email address
finds someone only when typed in full. It is throttled by address (30 an hour). `GET
/members/referrer-by-code` tells the form who a link belongs to, under the same throttle.

**Credit.** A referral counts for the referrer once the person is approved. Waiting people are shown
as a count only. A member cannot be their own referrer.

**The console.** The dashboard has a Referrals figure (this month against last month, and the share
of sign ups that were referred), a breakdown of where people heard of us, and the top referrers by
approved referrals. The members table has Source and Referred by columns and a filter; the approvals
table has a Heard of us column; the approval drawer has a Referred by row with an Edit button, so an
admin can correct the source, the detail and the referring member (audited as
`member.referral_edited`).

**Data.** On `accounts.User`: `referral_code` (unique), `referral_source`, `referral_detail`,
`referred_by`, `referral_code_used`. Migrations 0008 (add), 0009 (give existing accounts a code),
0010 (unique). The analytics event `referral_captured` carries only the source.

**API.** Public: `GET /members/search-referrer?q=`, `GET /members/referrer-by-code?code=`.
Member: `GET /me/referrals`. Console: `GET /admin/referrals/summary`, `GET /admin/referrals/top`,
`PATCH /admin/members/{id}/referral`; the members list takes `referral_source` and `referred_by`.
Registration (email and Google) takes an optional `referral` object: `kind`, `detail`, `referred_by`,
`code`.
