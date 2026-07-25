# Anonymising before you post

Goal: share the *capability* without exposing your real usage, address, meter IDs, or
account figures. Two options.

## Option A — quick redaction (fastest)
Post screenshots of the real dashboard but avoid / crop the few identifying spots:
- **Address** on the header — it's already the placeholder "1 Example Street"; keep it, or
  set it to a generic town.
- **Direct-debit / balance** figures on the DD card — crop out or blur if you'd rather not
  share them.
- Everything else (kWh, seasonal shapes, £ costs) is generic and not identifying.
- Meter IDs (MPAN/MPRN/IHD/GUID) are **already excluded** from the report by design — they
  never appear in a screenshot. ✅

## Option B — a clean demo dataset (recommended for a public article)
Run the tool on synthetic-but-realistic data so *nothing* on screen is yours. Cleanest for
LinkedIn/Medium. I can generate this for you — it would:
- keep the shapes realistic (winter gas peak, falling electricity) so the charts look true,
- perturb every reading/bill by a random ± factor and round, so no figure is your actual,
- set a generic address and a sample direct debit / balance,
- output a `Home_Energy_Inputs.DEMO.xlsx` and a `Energy_Report.DEMO.html` you screenshot from.

Say the word and I'll build the demo generator.

## Screenshot checklist
- [ ] Use the **light theme** for print/article contrast (toggle top-right), or dark for a
      "broadcast" look on LinkedIn — pick one and stay consistent.
- [ ] Capture at a wide window so charts aren't cramped; crop to the card you're describing.
- [ ] One clear screenshot per post/section beats a busy full-page shot.
- [ ] Add a 1-line caption naming what the reader is looking at.
- [ ] Include the disclaimer once per article/first post: *"illustrative / anonymised data."*

## Shots that map to the content
| Use it for | Capture |
|---|---|
| Hook / overview | Header + KPI hero row |
| Forecasting post | Electricity usage & forecast chart (forecast toggle ON, 95% band) |
| Monte-Carlo post | "Cost range & risk" chart (fixed vs tracker) |
| Standing-charge post | Cost breakdown headline + the 5-line chart |
| Weather post | Weather card (gas vs temperature + rainfall) |
| Design post | Year-on-year heat-map + what-if panel |
| Reflection | Full dashboard or the tab bar showing the four tabs |

## Publishing order (suggested)
1. Medium article first (the anchor).
2. LinkedIn Post 1 links to nothing yet — pure hook.
3. Posts 2–5 each teach one idea; link the Medium article in the comments (not the body —
   LinkedIn suppresses posts with external links in the body).
4. Post 6 = reflection + soft "open to opportunities", link the article.

## For contract / your own business
Add a short "How this maps to client work" line to your profile or the article close:
*"The same pattern — frame → model with validation → quantify uncertainty → ship a
decision-ready artefact — is exactly how I'd approach a forecasting or analytics engagement."*
That reframes a hobby project as a service demonstration.
