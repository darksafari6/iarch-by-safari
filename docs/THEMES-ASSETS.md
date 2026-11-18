# Dynamic themes: assets and legal policy

Dynamic packs are data and assets, not installation scripts. Validate every pack
before use, and apply the import limits and path restrictions in the pack format.
The reference pack is a format example, not a finished theme or a promise of
screenshot parity.

## Wallpapers and previews

Create original procedural wallpaper recipes and deterministic renders; record
seeds and generator versions with their output. Preview images must be generated
from redistributable assets. Anime wallpapers and album artwork visible in
reference screenshots are not included: a screenshot is not a licence to
redistribute its contents. Users may select their own wallpaper locally without
committing or redistributing it. Wallpaper recipe ingestion is not implemented
yet; the current pack validator refuses recipe files rather than accepting an
unvalidated format.

## Sounds, fonts and icons

Produce original synthesized sounds and document their generation. No sounds
are bundled by the Part 1 skeleton. Vendor fonts only with a verified SIL Open
Font License and the corresponding licence files; use openly licensed icons and
include their notices. Record third-party components in `data/licenses.json` and
link pack credits to component identifiers there. Check the actual licences of
each asset before redistribution, not merely a package description.

## Adapting third-party work

Identify the upstream project, version, source, author and licence before copying
or adapting code. Preserve required copyright notices, comply with source and
licence obligations, and document local modifications. If the licence or rights
cannot be established, do not ship the material. See `THIRD_PARTY_NOTICES.md`
for the current inventory and `docs/UNVERIFIED.md` for unresolved questions.
