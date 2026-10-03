# Master Scholarship Hunter

An Apify Actor for evidence-first scholarship research for one fixed profile:
a Beninese citizen currently studying in India, seeking a fully funded Master's
degree in Computer Science, IT, AI, or a closely related computing field.

It is deliberately a precision-oriented research tool, not a claim to search
every scholarship worldwide. Its current discovery adapter crawls
WeMakeScholars listings. For an explicitly labelled external application,
official-website, programme, or admissions link, it fetches the linked source,
keeps its evidence separate, and evaluates the official evidence first.

## What qualifies as a strong match

An item is a `strong_match` only when all hard gates pass:

- Master's eligibility is explicit.
- The scholarship itself supports a target computing field.
- Benefits explicitly cover both tuition and living expenses or a stipend.
- Benin is eligible through an explicit country list or a clearly applicable
  broad official rule.
- The structured destination is one of the target countries.
- The rules explicitly permit applying from abroad; a local-residency or
  already-enrolled requirement excludes the item.
- A deadline is active or upcoming.
- The evidence comes from an official government, programme, university, or
  document source (`verification_status: verified`).

`fully funded` alone does not verify funding. An unclear requirement produces
`possible_match`, never a strong match. WMS remains a discovery source: it is
verified only after a qualified official page is fetched and analysed.

## Input

- `start_urls` (optional): Direct programme pages or supported discovery
  listing URLs. When omitted, the Actor starts with the configured
  WeMakeScholars Master's computing listing.
- `max_requests_per_crawl` (default `100`): Maximum discovery/verification
  pages processed in one run.

No credentials are supplied through Actor input. SMTP settings use
`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, and `EMAIL_TO` environment variables.

## Output

Each dataset item preserves extracted source fields and includes:

- identity and provenance: `title`, `discovery_url`, `official_url`,
  `canonical_url`, source domains/types, and `verification_status`;
- decisions and evidence for degree, field, funding, nationality, destination,
  application location, and deadline;
- `match_status` (`strong_match`, `possible_match`, or `rejected`),
  `recommendation`, reasons, warnings, and the profile rule version.

Every evidence item is an object with `claim`, `source_url`, `source_type`, and
`confidence`. The Actor does not invent missing eligibility facts.

## Email behavior

Gmail SMTP is preserved. The emailer sends recommendations only where both
`recommendation == "include"` and `match_status == "strong_match"`.
When there are no strong matches, it sends “No verified strong matches this
run” with run diagnostics for discovered, verified, rejected, possible,
expired, and unknown-evidence records.

## Local development

```bash
apify validate-schema
apify run
python -m unittest discover -s tests -v
```

For a local Actor run, place input in
`storage/key_value_stores/default/INPUT.json`. Results are written to the local
default dataset. Local storage is not uploaded to Apify Console.

## Source coverage and limitations

`my_actor/sources.py` is an explicit source registry for WeMakeScholars,
Erasmus Mundus, DAAD, Chevening, Commonwealth, Swedish Institute, VLIR-UOS,
ARES, Government of Ireland, MEXT, and Mastercard Foundation. Only WMS has a
listing/detail discovery adapter today. It verifies only clearly labelled
outbound official/application links; social, tracking, and unrelated links are
rejected. The registry's other official entries remain disabled until each has
a dedicated discovery adapter.

The normal pipeline is discovery, normalization, deduplication, structured
extraction, official-link verification, evidence analysis, and final gating.
