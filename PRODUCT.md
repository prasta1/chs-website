# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences. **When their needs conflict, the local community wins.**

1. **Local community (primary).** Residents of Cambridge and Jeffersonville, Vermont, and nearby towns. They check the next monthly program, join or renew a membership, buy a book, donate an item, or arrange a visit to the Warner Lodge. Many are older, so legibility and simple navigation are hard requirements, not preferences.
2. **Genealogists and researchers (secondary).** Often remote. They hunt for ancestors in cemetery, vital, land and town records, and read back issues of the Harkener. They're served well, but they don't displace the community's front door.

The prototype also has an audience of its own: the **CHS board**, who will decide whether to adopt it.

## Product Purpose

A website for the Cambridge Historical Society (Jeffersonville, VT). CHS is a volunteer nonprofit, and its mission is "the caring for our collection, interpreting the historical, cultural, economic and technological contexts of these artifacts for a range of audiences."

This repo is a **speculative redesign pitched to the CHS board**. It is not commissioned, and it is not the official site. The live site is the Weebly build at cambridgehistoricalsociety.org. **Success means the board adopts this to replace it.**

## Positioning

The site holds CHS's own material, which no other site has: thirty years of recorded monthly programs, the Harkener newsletter back to Volume I (2001), transcribed town records (Books A, B and C), and a person-level index of those records. The Weebly site lists that material by title. This one makes it findable, starting with a surname search that returns people instead of PDFs.

## Operating Context

- Programs run on the **2nd Wednesday of each month at 7:00 p.m.** at the Warner Lodge, 49 School St, Jeffersonville. They're free, open to the public, and handicap accessible. Many are recorded to YouTube.
- The Warner Lodge is a 19th-century Masonic lodge with a preserved Victorian lodge room, a Masonic artifact collection, and rotating local-history displays. It's **open by appointment only**, or during programs.
- Orders, membership and donations happen by **email, mail and paper form** (PO Box 16, Jeffersonville, VT 05464; info@cambridgehistoricalsociety.org). There's no online card payment. The live site says it's "coming soon."
- The annual meeting and officer elections are in November.

## Capabilities and Constraints

- Seven static pages: Home, Programs, Records, The Harkener, Books, Support, About. Plain HTML, CSS and a little JS, with no build step. Each page carries its own copy of the header and footer on purpose, so occasional non-developer edits stay simple.
- Progressive enhancement: the record and program archives are complete static HTML. JS only filters them.
- The book order box computes a total and hands off to email, because that's how CHS takes orders today.
- **Archive search is designed but not live.** `data/archive.sqlite` indexes 9,665 person appearances from 16 of the 22 record PDFs. The spec (`docs/superpowers/specs/2026-09-09-chs-archive-search-design.md`) proposes Cloudflare Pages + D1, and volunteer editing through `/admin` behind Cloudflare Access.
- **Open decisions, not yet binding:** the Cloudflare D1 stack, browser-based volunteer editing, and whether the "not the official site" footer stays until adoption.

## Brand Commitments

- Name: **Cambridge Historical Society**, located in Jeffersonville, Vermont. The newsletter is ***The Cambridge Harkener***.
- Home: the **Warner Lodge**.
- Officers (per the current site): Joel Page, President; Rick Fletcher, Vice President; Geana Little, Treasurer; Richard Gagne, Secretary. Names and roles come from CHS and must not be invented or reshuffled.

## Evidence on Hand

- Real copy, programs, schedule, officers and the mission come from the live site. There's a reference mirror in `cambridgehistoricalsociety.org/`, which is gitignored.
- 29 past programs, 22 record PDFs, 32 Harkener issues, and a books list. The PDFs are in `pdfs/`, and the pages still hot-link most of them to Weebly.
- Images: `images/greenway-poster.jpg`, `images/gar-marker.jpg`, `images/book-postcard.jpg`.
- Person index: `data/archive.sqlite`.
- **Absent. Do not fabricate:** testimonials, member counts, visitor statistics, donation totals, collection photographs beyond the three above, and cover scans for *Tasteful Traditions* and *Special Places, Special People*. Five Harkener issues 404 at the source: Mar, Jul and Sep 2020, and Jun and Oct 2021. The postcard book's title and co-author name ("Matt" vs "Madison D. Safford") are unconfirmed.

## Product Principles

1. **The community's front door comes first.** The next program, membership and a visit should be obvious within seconds. Records depth sits one step behind.
2. **Readable by an 80-year-old member on an old laptop.** Large type, high contrast, plain words, and navigation that doesn't hide.
3. **Show the board their own society, better.** Real CHS content, faithfully presented. Nothing speculative dressed up as fact.
4. **Don't promise what CHS can't operate.** Match how volunteers actually work (email orders, paper forms, occasional edits) rather than implying systems nobody runs.
5. **The archive is the lasting asset.** Make it findable without making it the headline.

## Accessibility & Inclusion

A large share of the primary audience is older. Treat WCAG 2.2 AA as the floor, and go further on text size, contrast, target size and clarity of navigation. Content must work with JS off.
