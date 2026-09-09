# chs-website

A design prototype for the Cambridge Historical Society (Jeffersonville, Vermont), built
from a Claude Design artboard and served as a static site on GitHub Pages.

**This is not the official CHS site.** The live site is
[cambridgehistoricalsociety.org](https://cambridgehistoricalsociety.org). Every page here
carries a footer note saying so.

Main CHS working repo: [prasta1/cambridge-historical-society](https://github.com/prasta1/cambridge-historical-society)

## What's here

Plain static HTML — no build step, no framework, no dependencies. Open any file and edit it.

| File | Page |
|---|---|
| `index.html` | Home |
| `programs.html` | Monthly programs + searchable archive of 29 past programs |
| `records.html` | 22 cemetery, vital, land and town records (free PDFs) |
| `harkener.html` | The Cambridge Harkener newsletter, 32 issues back to 2001 |
| `books.html` | Books for sale, with running order total |
| `support.html` | Membership, donations, donating an item |
| `about.html` | Mission, officers and directors, the Warner Lodge |
| `style.css` | All styling — design tokens live in `:root` |
| `app.js` | Record/program filtering and the book order total |

The seven pages each carry their own copy of the header, nav and footer. That's deliberate:
a 7-page site edited occasionally by non-developers is easier to maintain as plain files
than behind a template step.

## The design source

The layout, type scale and colour come from a Claude Design project
(`Cambridge Historical Society.dc.html`). That file is a canvas artboard — a React-runtime
prototype with `<x-dc>` templates and `<sc-if>` conditionals — so it was used as the visual
spec, not copied. The seven canvas "screens" became seven real pages with real URLs, and
the design's button-driven navigation became ordinary links.

Type is Newsreader + JetBrains Mono from Google Fonts; everything else is self-contained.

## Progressive enhancement

The record and program archives are written into the HTML as static rows. `app.js` only
shows and hides them, so both archives are fully readable — and indexable — with JavaScript
off. Filtering, the video-only toggle and the order total are the enhancement.

## Known gaps

- **PDFs are hot-linked** to `cambridgehistoricalsociety.org/uploads/...` rather than
  hosted here, keeping the repo small. They break if the Weebly site goes away; copying
  ~78MB of PDFs into the repo is the fix when that matters.
- **Five Harkener issues 404 on the source site** (Jul 2020, Jun 2021, Mar 2020, Oct 2021,
  Sep 2020). They're listed struck-through rather than linked to a dead file.
- **Book covers** for *Tasteful Traditions* and *Special Places, Special People* are
  placeholders — no scans exist on the current site.
- **Online card payment doesn't exist yet.** The design mocked a Square checkout against a
  placeholder URL; the live site says "coming soon". The order box computes the total and
  hands off to email, matching how CHS actually takes orders today.
- **Postcard book title** is taken from the cover art
  (*Cambridge, Vermont: From the Lens of a Camera... to a Postcard*). The current site
  never states a title, and names the co-author "Matt Safford" where the cover reads
  "Madison D. Safford" — worth confirming with CHS.

## Local preview

```
python3 -m http.server 8000
```

Then open <http://localhost:8000>.
