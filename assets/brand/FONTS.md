# Brand typography

Poppins is the shared font across marketing, merchant admin, platform admin,
storefront, and payments. It replaces the earlier Sreda selection; no font upload
is needed. The raster MSHOPPA logo is unchanged.

`packages/ui/src/fonts.css` defines the 400, 500, 600, and 700 upright weights.
The WOFF2 files live in `assets/brand/fonts/poppins/`. Latin, Latin Extended, and
Devanagari subsets use Unicode ranges so browsers fetch only the needed subsets.
Angular emits content-hashed font assets for each app. `font-display: swap` keeps
text visible while loading, with a system sans-serif fallback. There are no
runtime Google Fonts requests.

Font files: Google Fonts Poppins v24, downloaded 2026-09-05 from
https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap

Upstream: https://github.com/itfoundry/Poppins

License: SIL Open Font License 1.1, preserved in `fonts/poppins/OFL.txt` from
https://github.com/google/fonts/blob/main/ofl/poppins/OFL.txt
