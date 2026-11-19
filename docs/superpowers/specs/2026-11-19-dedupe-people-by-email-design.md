audience: agent

# Dedupe the people list by email, and stop names losing their address

Date: 2026-11-19
Status: approved (user chose "do both" and confirmed the four ambiguous names)

## Intent / why

The people list (人員) in Vinutes fills up with the same colleague under
several spellings, and the mail sheet shows "no email" for many of them.
The user asked to both clean up the current data and change the app so it
stops recurring.

Root cause (confirmed against the user's live data): Vinutes keeps a
separate people list per project and per department/room-booking roster,
and records each person with whatever spelling that meeting used. Two
spellings are only merged when one is written inside the other's brackets
(`name_keys` overlap). So "Phoebe", "林岳穎(phoebe)" and "林岳穎" are
treated as up to three different people, and rosters only ever grow.

"No email" is the same problem from the mail side: `contacts.address_of`
returns '' when a name does not resolve to exactly one directory address.
It fails in three ways seen in the data:
1. A precise name dragged into ambiguity by an English nickname —
   `林岳穎(phoebe)` matches 林岳穎 (phoebelin, one) AND phoebe
   (phoebecheng, another) -> ambiguous -> ''. The plain `林岳穎` resolves.
2. An alphanumeric nickname treated as an "explanation" bracket —
   `陳昱穎(BA0Z)` only tries the whole string, never the name 陳昱穎.
3. A bare first name that genuinely belongs to two people (two Erics,
   two Phoebes, two Sophies). Returning '' here is correct; only the
   user can pick, so these need an alias.

## Goals

- Each person appears once per list, under a canonical spelling.
- A name that identifies one directory person resolves to their email.
- Names going forward auto-merge when they resolve to the same email.

## Non-goals / anti-goals

- Never merge two names that resolve to different (or empty) addresses —
  a wrong merge, or emailing the wrong colleague, is worse than a dup.
- Do not change `name_keys`/`same_name` semantics (wide blast radius; the
  bracket rules are relied on for voice matching, incl. nested
  `高聖哲(Vin(Vincent))`).
- Do not rename a person to the directory's romanized form, which would
  break transcript-speaker matching.

## Approaches considered

- A. Anchor identity on email everywhere; rekey people.json by address.
  Rejected: large refactor of a shipping, main-protected app for little
  extra gain.
- B. Merge by shared name token (split on spaces). Rejected: would merge
  two different Phoebes into one.
- C (chosen). Keep name strings, but (1) make `address_of` resolve
  most-specific-first so a precise name is never dragged into ambiguity,
  (2) make the single add-a-name chokepoint (`briefs.add_name`) also
  merge when two names resolve to the same non-empty address, keeping the
  fuller spelling, and (3) a one-off cleanup of the live data plus
  aliases for the genuinely ambiguous names the user picked. Safe
  (address-anchored, no false merges), contained, test-first.

## The changes

### 1. contacts.address_of — tiered, specific-first

- Treat a bracket whose inside is `[a-z0-9.'-]+` (allow digits, so
  `BA0Z`, `BC`) as a nickname: also try the outside part (the real name).
  A CJK-only bracket (`Amy（悠遊卡）`, `林采瑤(采瑤)`) stays an
  explanation -> whole string only, unchanged.
- Specific keys = { whole, outside-of-nickname-bracket }. Broad keys =
  { nickname inside, tokens of the whole name }.
- Resolve in order, return the moment a tier gives exactly one, '' when a
  tier is itself ambiguous: alias -> name-match(specific) ->
  name-match(broad) -> address-localpart(specific) -> address-localpart(broad).
- Effect: `林岳穎(phoebe)` -> phoebelin (specific wins); `陳昱穎(BA0Z)` ->
  jessiechen; `小 Amiee` -> amieekuo (token broaden); bare `Phoebe`/`Eric`
  stay '' until aliased. All existing contacts tests keep passing.

### 2. briefs.add_name — merge by resolved address

- Lazily import contacts. When the incoming name resolves to a non-empty
  address equal to an existing name's, they are the same person: keep the
  one with more `name_keys` (preserves bracket forms used for voice
  matching), drop the other. Otherwise the current `same_name` behaviour.
- Falls back to name-only when contacts is empty or a name is unresolved
  (both ''), so tests and offline use are unaffected, and two unresolved
  or differently-resolved names are never merged.

### 3. One-off data cleanup (not committed; run against live config)

- Back up people.json, departments.json, contacts.json first.
- Set aliases the user confirmed: Eric->ericzhuang, Phoebe->phoebelin,
  "Sophie Wang"->sophie.wang@tfc101.com.tw, "黃程韋(BC)"->become@fontrip.com;
  plus 采瑤 / 林采瑤(采瑤) -> celialin (certain).
- Rebuild each list with the updated add_name so same-address spellings
  collapse. Remove the nameless "無" roster (14 people, a catch-all built
  from department-less meetings that only grows).
- Show the user a before/after of each list.

## Verification

- `python -m unittest discover -s tests` green, including new cases above.
- Re-resolve every name in the user's live lists: the ones that should
  have an address now do; show the remaining unresolved (if any) with why.

## Left to the builder

- Canonical-pick tie-breaks in cleanup (prefer more name_keys, then
  longer string); the nickname-bracket regex lives in address_of.
