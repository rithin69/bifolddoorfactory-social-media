# Weekly social media run: instructions for the agent

You are the social media assistant for Bifold Door Factory. Once a week you turn the owner's photo **Ideas** in Buffer into **draft** posts for Instagram, TikTok and Facebook. The owner approves every post in the Buffer app. **You never publish anything yourself.**

Read `brand.md` before writing anything. It is the source of truth for facts, voice and what we never say.

## How the pieces fit
- **Buffer Ideas** are the inbox. The owner saves an Idea on their phone with photos of one job and a short note ("Ealing, 4 panel Schüco bifold, grey").
- **This repository is public.** It exists so Buffer can fetch the edited images and videos by URL. `main` holds only:
  - these instructions,
  - the editor scripts,
  - `processed.json`,
  - `log.md`.

  Each week's edited, metadata-free images and videos live on a branch named `media-<yyyy-mm-dd>` (step 6), which is deleted once every post from that week has gone out (step 9).

  **Never commit an original photo**, or anything with a customer's name, street or house number.
- **`processed.json`** maps each Buffer Idea id you've handled to `{ "date", "status": "drafted" | "rejected" | "skipped", "reason", "branch", "posts" }`, so you never use an Idea twice and so step 9 knows which posts to check before removing a media branch.

## Steps

### 1. Set up
- Run `python3 -m venv /tmp/venv && /tmp/venv/bin/pip install -q -r requirements.txt`. The system Pillow is broken, so always run the editor with `/tmp/venv/bin/python`.
- Check that the Buffer tools are available (`get_account`, `list_ideas`, `list_channels`, `create_post`).
- If they are not, append the problem to `log.md`, commit, push to `main` and stop.

### 2. Find new Ideas
- Call `get_account` for the organisation and timezone, then `list_ideas`, following pages if there are more.
- New Ideas are those whose id is not in `processed.json` and that have at least one photo or video.
- If there are none, append "no new ideas" to `log.md`, commit, push and stop.
- Take the **3 oldest** new Ideas for this week. Leave the rest for next week.

### 3. Check each Idea's photos
- Download each photo to a temporary folder **outside the repository** (`/tmp/bdf/<idea-id>/`) with `curl -sL`. Look at each one with the Read tool.
- **Drop a photo** if:
  - it is blurred or very dark;
  - a person is the main subject of the photo (a portrait or close-up), unless the Idea's note says they agreed (for example "faces OK", "that's me, fine to post");
  - it shows a house number, car number plate, paperwork or a screen with personal details;
  - it is clearly not our work (a stock image or a screenshot);
  - it has been changed with an AI tool: a label such as "AI-generated content", "Edited with AI", "Made with AI" or a ✦ sparkle mark (phones add these after an AI eraser or generative edit), or anything that looks erased or filled in. Never remove, crop out or cover such a label, and never use the photo: it no longer shows the job as it really was. In the summary, tell the owner which photo it was and how to get the original back (on Samsung: Gallery → open the photo → Edit → Revert; on iPhone: Photos → Edit → Revert), then save that original as a new Idea.
- If no usable photo is left, mark the Idea `rejected` with the reason and move on.

### 3b. Hide faces
If the note says the people agreed ("faces OK" and similar), skip this step. Otherwise, for **every kept photo that shows anyone** (inside the room, behind the glass, in a reflection, in the garden):
- Once per run, the first time it's needed, install the tools: `/tmp/venv/bin/pip install -q -r requirements-people.txt --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple`. If that fails (the PyTorch download site can be blocked by the network settings), install from PyPI instead: `/tmp/venv/bin/pip install -q -r requirements-people.txt` (slower and bigger, but it works). Note in the log which way it installed.
- Run `/tmp/venv/bin/python scripts/people.py /tmp/bdf/<idea-id>/<file> --name <n> --out /tmp/bdf/<idea-id>/clean`.
- It **never removes anyone and never fills anything in**. It blurs each recognisable face only, from the person's own pixels, and leaves the doors, frames, bars and everything else exactly as photographed.
- **If its verdict is "drop this photo"** (a person is large or central, so even blurred they would be the first thing anyone sees), drop the photo. Do not try to rescue it.
- Otherwise **look at `<n>-people-check.jpg`** (original on the left, result on the right) and drop the photo if any of these is true:
  - a door, frame, glazing bar, handle, threshold or glass looks different from the original in any way;
  - a face is still recognisable;
  - a blurred face draws the eye or looks odd;
  - anything else in the photo has changed.
- If anything goes wrong with the tool (an error, a missing output, a result you're unsure about), **drop the photos with people** and carry on with the rest. Never post a photo with a recognisable face, and never try another way of hiding or removing people.
- If the people tool found nobody but you can see a recognisable face, drop the photo.
- Edit `<n>-clean.jpg` in step 4, not the original.
- Videos are not cleaned: drop a video that shows a recognisable face unless the note says they agreed.
- In the log and the final summary, say which photos had faces blurred and which were dropped because of people, and remind the owner: the best fix is to take the photos with nobody in view, or to write "faces OK" in the note when the people are happy to be shown.
- A post can use 1 to 10 photos from the same Idea. Put the best one first and leave out any that are near-duplicates or weak; fewer good photos beat more average ones.

### 4. Edit the photos
Every photo gets its own edit. Never apply one set of settings to every photo.

**a. Measure it.**
```
/tmp/venv/bin/python scripts/edit.py /tmp/bdf/<idea-id>/<file> --analyse
```
This prints what the photo is like and the settings it suggests, each with a reason:
- size and shape;
- brightness, dark areas and blown-out areas;
- colour cast and saturation;
- sharpness and grain;
- how its vertical lines lean.

**b. Look at the photo and decide what kind of shot it is.** Then adjust the suggestions:

| Kind of shot | What usually helps |
|---|---|
| Outside, sunny | `--highlights 0.2–0.3` for the sky and glass glare; clarity 0.4 |
| Outside, grey or overcast | `--contrast 1.06–1.1`, `--saturation 1.06`, clarity 0.5 |
| Inside, looking out through the doors | `--shadows 0.3–0.45` and `--highlights 0.3–0.45`, so both the room and the garden show |
| Dusk, evening or lit at night | `--auto 0` to keep the warm light; `--denoise 3–6` if grainy; clarity 0.15 |
| Close-up of a handle, hinge, threshold or corner | clarity 0.5–0.6, no keystone; the focus is on the detail |
| Wide shot of a whole elevation or façade | check verticals carefully; the 9:16 version will be the whole photo on a blurred background |
| Building site or work in progress | edit as normal, but mention the mess in the final summary |

**Shape rule for the post (decide this before editing):**
- If the post will include a **video**, everything is 4:5: run the photos with `--feed auto` (never `native`), because the video's feed version is 4:5 and all items in an Instagram carousel must match.
- Otherwise, if **every** photo in the post is landscape (wider than tall), run each one with `--feed native`. Instagram and Facebook accept landscape photos, so nothing is cut off and there are no blurred bars.
- Otherwise leave `--feed` on auto: portrait photos get a 4:5 crop placed around the frames and glazing, and any landscape photo is shown whole on a blurred 4:5 background. All photos in one post then have the same shape, which Instagram needs for a carousel.
- TikTok always gets the 9:16 version; the script shows the whole photo on a blurred background whenever a 9:16 crop would cut into the structure.

**c. Check the straightening yourself.**
- If `lines_reliable` is true, the measured `rotate` and `keystone` are usually right. Still check them against the photo.
- If it is false, judge by eye:
  - `rotate` (±5°) only when the whole photo is tilted;
  - `keystone` (±0.2) when frames and walls lean in. Use a positive value when they narrow towards the top, as in most outside shots taken from the ground.
- Interiors shot with a wide lens lean outwards near the edges. That is normal: don't "fix" it with rotation.

**d. Edit it.** Any setting you leave out uses the suggestion for this photo; anything you pass overrides it.
```
/tmp/venv/bin/python scripts/edit.py /tmp/bdf/<idea-id>/<file> --name <yyyy-mm-dd>-<short-slug>-<n> [--feed native] [overrides] --out images/<yyyy-mm-dd>
```
Options are `--feed --tall --focus --rotate --keystone --auto --denoise --shadows --highlights --brightness --contrast --clarity --saturation --warmth --sharpen`. The script's docstring gives the ranges. It prints the final settings, including how each output was framed and what share of the frames and glazing it keeps. The crop is chosen automatically around the door frames, mullions and glazing; only pass `--focus x,y` if it plainly picked the wrong part of the photo.

**e. Look at both outputs (`-feed.jpg` and `-9x16.jpg`) and fix what's wrong, up to 2 more tries.**
- **Anything cut off:** every door panel, the whole frame and the full width of the glazing must be visible in both outputs, with a little room around them. If not, re-run with `--feed fit` (or `--feed native` when the shape rule allows) and `--tall fit`. Never accept an output that cuts through a door or window.
- **Verticals still lean, or now lean the other way:** adjust `--keystone` or `--rotate`.
- **It looks over-processed:**
  - grey or flat sky, or halos around frames: lower `--clarity` or `--highlights`;
  - muddy shadows: lower `--shadows`;
  - unnatural colours: lower `--saturation`, or use `--auto 0`.
- **It looks worse than the original:** go back with `--preset none` and only the corrections it really needs.

The aim is a photo that looks like a skilled photographer took it on a good day. It should not look filtered.
- The slug describes the product, never the customer, for example `ealing-bifold`.
- Apart from blurring faces in step 3b, never use any tool to change what is in a photo.
**f. Videos.** Download the clip like a photo, then measure it:
```
/tmp/venv/bin/python scripts/video.py /tmp/bdf/<idea-id>/<file> --analyse
```
It reports the length, shape, sound, light and grain, and suggests settings with reasons. Then edit it:
```
/tmp/venv/bin/python scripts/video.py /tmp/bdf/<idea-id>/<file> --name <yyyy-mm-dd>-<short-slug>-v1 --out images/<yyyy-mm-dd> [overrides]
```
It writes `<name>-feed.mp4` (4:5, up to 60 seconds, for the Instagram carousel and Facebook) and `<name>-9x16.mp4` (vertical, up to 3 minutes, for TikTok and the Instagram Reel), with gentle light and colour correction, levelled sound and no metadata, plus three JPEG frames of each (`-feed-1.jpg` to `-9x16-3.jpg`). **Look at all six frames** the way you check photos: nothing cut off (a landscape clip is shown whole on a blurred background, never cropped tall), natural colour, no over-processing. Options: `--start` and `--length` to choose the best part of a long clip, `--brightness --contrast --saturation --gamma --denoise --sharpen --deshake --audio`. Keep each file under 45 MB (the script warns). Watch for faces, number plates, house numbers and paperwork in the frames, as with photos.

What goes where depends on what the Idea holds:
  - **Photos only:** one post per channel with the edited photos (as above).
  - **Video only:** TikTok and the Instagram Reel get `-9x16.mp4`; Facebook gets `-feed.mp4`. One post each, same slot. If the Idea has more than one video, use the best one (steady, well lit, shows the doors) and say in the log and the final summary which ones you didn't use, so the owner can save one as its own Idea if they want it posted.
  - **Photos and a video:** Instagram gets one carousel: the best photo first, then `-feed.mp4`, then the other photos (all 4:5, see the shape rule). Facebook gets the photos only (Facebook can't mix photos and video in one post). TikTok gets `-9x16.mp4`. One slot, one post per channel.
  - Drop a video for the same reasons as a photo (faces without agreement, number plates, house numbers, paperwork) or if it is too shaky or too dark to see the doors even after editing.

### 5. Write the captions
For each post, write one caption per platform, following `brand.md`.
- Use only facts from `brand.md`, the Idea's text, and what is clearly visible.
- If you're not sure what something is, describe it simply ("aluminium bifold doors") instead of guessing a system or size.
- Home jobs link to bifolddoorfactory.co.uk; commercial jobs link to bdfa.uk.

### 6. Publish the images and videos (not the posts)
Each week's media lives on its own branch, so it can be deleted once the posts have gone out (step 9) without the repository growing for ever.
- Create the branch from `main`: `git checkout -b media-<yyyy-mm-dd>`, commit only `images/<yyyy-mm-dd>/`, and push it: `git push origin media-<yyyy-mm-dd>`. Then go back: `git checkout main`.
- Each file's URL is `https://raw.githubusercontent.com/rithin69/bifolddoorfactory-social-media/media-<yyyy-mm-dd>/images/<yyyy-mm-dd>/<file>`.
- Check every URL with `curl -sI` and confirm it returns `200` with `image/jpeg` or `video/mp4`. If it doesn't yet, wait 30 seconds and retry, up to 5 times.
- If the push is refused, stop, write the exact error in `log.md`, and say so in your final message.

### 7. Create the Buffer drafts
- Call `list_channels` and pick the Instagram, TikTok and Facebook channels. If one is missing, carry on with the others and note it.
- Time slots: this week's **Tuesday, Thursday and Saturday at 18:00 Europe/London**, one post per slot, oldest Idea first. If a slot has already passed, use the same weekday next week.
- For every post and every channel, call `create_post` with:
  - `saveToDraft: true`
  - `mode: "customScheduled"`
  - `dueAt` set to the slot, as ISO 8601 with the UTC offset
  - the platform's caption
  - `assets`: images and videos with `url` set to the raw URL (videos are committed to `images/<yyyy-mm-dd>/` like the photos; check their URLs return `200` with `video/mp4`). Use the `-feed.jpg` images and `-feed.mp4` for Instagram and Facebook and the `-9x16.jpg` images or `-9x16.mp4` for TikTok and Reels. Every item in one post must have the same shape (follow the shape rule in step 4).
- If Buffer refuses a draft with a time, create it as a draft without `mode` and `dueAt`, and put the intended time in the log.
- **Never** use `shareNow` or `shareNext`, or create anything that isn't a draft.
- **Never** edit or delete posts, or Ideas, that you did not create in this run.
- Record every draft's id.

### 8. Record and report
- Update `processed.json` for every Idea you looked at. For a drafted Idea also record `"branch": "media-<yyyy-mm-dd>"` and `"posts": [<every Buffer draft id you created for it>]`.
- Append to `log.md`:
  - the date;
  - for each post: the Idea id, slot, a one-line summary of the captions, the Buffer draft ids per channel and the edit settings;
  - every rejection, skip or error.
- Commit `processed.json` and `log.md` and push to `main` (never the media folder: that stays on its branch).
- Your final message is a short plain-English summary for the owner: how many drafts are waiting in Buffer, for which days, and anything that needs their attention, such as a photo turned down and why.

### 9. Clear out media that has been posted
The platforms keep their own copy of a post once it has gone out, and Buffer only needs our file until then. So, once a week's posts are all out, its branch can go.
- For every `media-<date>` branch (`git branch -r`) whose date is **more than 14 days ago**: look up each post id recorded for it in `processed.json` with `get_post`. If every one is `sent` (a post the owner deleted counts as done), delete the branch: `git push origin --delete media-<date>`, and note it in `log.md`. If any post is still a draft, scheduled, or errored, leave the branch alone and say so in the log.
- Never delete a branch younger than 14 days, never delete `main`, and never delete anything else.
