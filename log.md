# Run log

Each weekly run adds an entry here: what it drafted, what it skipped and why.

## 2026-11-12
- No real Ideas found. Only the two default Buffer welcome Ideas exist (skipped/rejected, recorded in processed.json). No drafts created.

## 2026-11-12 (second run)
- Idea 6af5ec90da1a7c9c3c8ae258 ("schuco bi fold doors installation for a house"), 4 photos, all used. Slot: Tue 2026-11-17 18:00 Europe/London (this week's Tuesday had passed).
- Captions: "Five panels fold back..." Schüco bifold doors on a house extension, roof lantern, home website. No place given, so no place hashtag.
- Drafts: Instagram 6af5ed4a6b041da7276034fd, Facebook 6af5ed4ed95eb37c36f3e8f4, TikTok 6af5ed516b041da7276036b6.
- Edits (originals in /tmp, not committed): photo 1 focus 0.3,0.55 contrast 1.05; photo 2 focus 0.5,0.55; photo 3 focus 0.62,0.5 brightness 1.08; photo 4 focus 0.5,0.45 brightness 1.08.
- Note: the system PIL was broken, so a venv was used to run scripts/edit.py. Only one new Idea existed, so Thursday and Saturday slots were unused.

## 2026-11-17
- No new Ideas. The only Idea in Buffer (6af5ec90da1a7c9c3c8ae258) was already drafted on 2026-11-12 but had not been recorded in processed.json; it is now recorded as drafted with its three post ids. No drafts created.
- Its three drafts are still in draft status (due Tue 2026-11-17 18:00), awaiting owner approval. Their images are on main, not a media branch, so there is nothing to clear in step 9.

## 2026-11-17 (weekly run)
- Idea 6afc3e4625d8078bf6d3547b ("Schüco bifold doors, house extension"), 4 photos, all used (same job as the 12 Nov Idea, re-run with the new editor as the note asks). Building site in the photos (rubble, paint pots, a child's bike inside): worth the owner's eye.
- Slot: Thu 2026-11-19 18:00 Europe/London (GMT). Used Thursday rather than Tuesday because the three older drafts from the 12 Nov run already sit in Tuesday 18:00 with the same photos; two posts of the same job at one time seemed worse. Only one new Idea, so Saturday is unused.
- Captions: "Five panels fold back to open the whole extension to the garden." Schüco bifold doors, house extension, roof lantern, home website. No place given, so no place hashtag.
- Drafts: Instagram 6afc3e9e9d7d4c6b7858a0a0 (4-photo carousel), Facebook 6afc3ea2b9fb95e12d026984, TikTok 6afc3ea66d6484cf6f1784d6.
- Edits (all landscape, so --feed native): photo 1 highlights 0.2, keystone 0.023; photo 2 (exterior, glazed) highlights 0.2, rotate -0.44, keystone 0.051; photo 3 (interior) shadows 0.35, highlights 0.35, rotate 0.63, keystone -0.07; photo 4 (interior, doors open) shadows 0.35, highlights 0.35. Photo 2 shows a faint, unrecognisable reflection of a person in the glass; kept.
- Media branch: media-2026-11-17 (all URLs returned 200 image/jpeg).
- Step 9: no media-<date> branch older than 14 days; nothing deleted. The 12 Nov images are on main (pre-branch layout), so nothing to clear.

## 2026-11-17 (third run)
- Idea 6afc4753d5c4b0408070d6e0 ("art deco bi fold doors cortizo. ral 1013 special colour art deco bottom panels"), 8 photos, 3 used.
- Dropped photos 1-4 (the outside shots of the back of the house): each shows people inside with recognisable faces (two people in the kitchen in 2 and 3, a face through the glass in 1, people and the photographer's reflection in 4), and the note doesn't say they agreed. Dropped photo 6 as a near-duplicate of photo 7. Used interiors 5 (doors folded open), 7 and 8 (doors closed). A person's arm and shoulder show at the right edge of photo 7, no face.
- Slot: Sat 2026-11-21 18:00 Europe/London (GMT). Tuesday 18:00 already holds the 12 Nov drafts and Thursday 18:00 holds this morning's drafts, so Saturday was the free slot.
- Captions: "Art deco bifold doors in a special RAL 1013 colour." Cortizo aluminium bifolds, solid art deco bottom panels, slim glazing bars, kitchen opens to the garden; home website. No place given, so no place hashtag.
- Drafts: Instagram 6afc482bbea63ad8bdd0d30c (3-photo carousel), Facebook 6afc483055207cffaee93940, TikTok 6afc4835b7c36a6dabfb3068.
- Edits (all landscape, so --feed native; interiors looking out): photo 5 shadows 0.35, highlights 0.35, keystone -0.098, clarity 0.4, saturation 1.08; photo 7 shadows 0.35, highlights 0.4, rotate 0.85, keystone -0.039, clarity 0.4, saturation 1.04; photo 8 shadows 0.35, highlights 0.35, rotate 1.57, clarity 0.4, saturation 1.04. TikTok versions show the whole photo on a blurred 9:16 background.
- Media branch: media-2026-11-17 (added files; all 6 URLs returned 200 image/jpeg).
- Step 9: no media-<date> branch older than 14 days; nothing deleted.

## 2026-11-17 (fourth run)
- One new Idea: 6afc4e3d1c282b5aeb935d6c ("art deco bi fold doors cortizo. ral 1013 special volour art deco bottom panels..."), 8 photos. It holds exactly the same 8 photos as Idea 6afc4753d5c4b0408070d6e0, which is already drafted for Sat 2026-11-21 18:00.
- Skipped, no drafts created. The 4 outside shots (1, 2, 3, 8) show people inside with recognisable faces and the note doesn't say they agreed, so step 3b applies. scripts/people.py failed on every photo: it could not download the Mask R-CNN model from download.pytorch.org ("Tunnel connection failed: 403 Forbidden"; the environment's network policy blocks that host). PyTorch itself installed. Without the tool those 4 photos can't be used. The usable photos left (interiors 4, 5, 7; photo 6 shows an arm) are the ones already in Saturday's drafts, so a second post with them would be a duplicate.
- Fix: allow download.pytorch.org in the cloud environment's network settings, then delete this Idea's entry from processed.json (or save the Idea again) so the next run retries it.
- All three slots this week (Tue 17, Thu 19, Sat 21 Nov, 18:00) already hold earlier drafts.
- Step 9: only branch is media-2026-11-17 (not older than 14 days); nothing deleted.

## 2026-11-17 (fifth run)
- Retried Idea 6afc4e3d1c282b5aeb935d6c (art deco Cortizo bifolds, RAL 1013, 8 photos), whose entry had been cleared so it could go through the people tool.
- download.pytorch.org now serves the model files, but the PyTorch wheel host (download-r2.pytorch.org) is still blocked, so torch and torchvision were installed from PyPI instead. scripts/people.py then ran on the 4 outside shots (1, 2, 3, 8).
- Results: photo 1: 1 person removed, 1 blurred. It failed the check: the fill where the woman was removed is smeared, and the blurred man looks ghostly. Photo 2: 2 blurred, the blurred figures stand in the middle of the opening and are the first thing you notice. Photo 3: 3 blurred (reflections in the glass). Photo 8: 4 blurred, with a visible blocky patch on one reflection.
- During the run the owner said that if anything fails with the people photos, stop. Photo 1 failed, so the run stopped: none of the people photos were used and no drafts were created. The interiors left (4, 5, 7) are already in Saturday's art deco drafts. Marked skipped.
- Step 9: only media-2026-11-17 exists (not older than 14 days); nothing deleted.
