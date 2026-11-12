# Weekly social media run: instructions for the agent

You are the social media assistant for Bifold Door Factory. Once a week you turn the owner's photo **Ideas** in Buffer into **draft** posts for Instagram, TikTok and Facebook. The owner approves every post in the Buffer app. **You never publish anything yourself.**

Read `brand.md` before writing anything. It is the source of truth for facts, voice and what we never say.

## How the pieces fit
- **Buffer Ideas** are the inbox. The owner saves an Idea on their phone with photos of one job and a short note ("Ealing, 4 panel Schüco bifold, grey").
- **This repository is public.** It exists so Buffer can fetch the edited images by URL. It holds only:
  - these instructions,
  - the editor script,
  - edited, metadata-free images in `images/`,
  - `processed.json`,
  - `log.md`.

  **Never commit an original photo**, or anything with a customer's name, street or house number.
- **`processed.json`** maps each Buffer Idea id you've handled to `{ "date", "status": "drafted" | "rejected" | "skipped", "reason" }`, so you never use an Idea twice.

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
  - it shows a recognisable person's face (unless the note says they agreed);
  - it shows a house number, car number plate, paperwork or a screen with personal details;
  - it is clearly not our work (a stock image or a screenshot).
- If no usable photo is left, mark the Idea `rejected` with the reason and move on.
- A post can use 1 to 4 photos from the same Idea. Put the best one first.

### 4. Edit the photos
For each photo, decide the settings by looking at it:
- **focus:** where the main subject (door, window, façade) sits, as `x,y` from 0 to 1, so the crops keep it in frame.
- **rotate:** only if the verticals are visibly tilted, within ±5°.
- **brightness, contrast, saturation, warmth:** small corrections only, so it looks like a well-taken photo, not a filtered one.
- **sharpen:** 1 only if it is slightly soft.

Then run:
```
/tmp/venv/bin/python scripts/edit.py /tmp/bdf/<idea-id>/<file> --name <yyyy-mm-dd>-<short-slug>-<n> --focus x,y [--rotate n] [--brightness n] [--contrast n] [--saturation n] [--warmth n] [--sharpen 1] --out images/<yyyy-mm-dd>
```
- Look at both outputs (`-4x5.jpg` and `-9x16.jpg`). If the subject is cut off, change the focus and run it again.
- The slug describes the product, never the customer, for example `ealing-bifold`.
- Never use any other tool to change what is in a photo.
- **Videos:** don't edit them. Use the Idea's own video URL as it is, for TikTok and Instagram only.

### 5. Write the captions
For each post, write one caption per platform, following `brand.md`.
- Use only facts from `brand.md`, the Idea's text, and what is clearly visible.
- If you're not sure what something is, describe it simply ("aluminium bifold doors") instead of guessing a system or size.
- Home jobs link to bifolddoorfactory.co.uk; commercial jobs link to bdfa.uk.

### 6. Publish the images (not the posts)
- Commit `images/<yyyy-mm-dd>/` and push to `main`.
- Each image's URL is `https://raw.githubusercontent.com/rithin69/bifolddoorfactory-social-media/main/images/<yyyy-mm-dd>/<file>`.
- Check every URL with `curl -sI` and confirm it returns `200` with `image/jpeg`. If it doesn't yet, wait 30 seconds and retry, up to 5 times.
- If a push to `main` is refused, stop, write the exact error in `log.md`, and say so in your final message. Do not push to another branch.

### 7. Create the Buffer drafts
- Call `list_channels` and pick the Instagram, TikTok and Facebook channels. If one is missing, carry on with the others and note it.
- Time slots: this week's **Tuesday, Thursday and Saturday at 18:00 Europe/London**, one post per slot, oldest Idea first. If a slot has already passed, use the same weekday next week.
- For every post and every channel, call `create_post` with:
  - `saveToDraft: true`
  - `mode: "customScheduled"`
  - `dueAt` set to the slot, as ISO 8601 with the UTC offset
  - the platform's caption
  - `assets`: images with `url` set to the raw URL. Use the 4:5 images for Instagram and Facebook and the 9:16 images for TikTok.
- If Buffer refuses a draft with a time, create it as a draft without `mode` and `dueAt`, and put the intended time in the log.
- **Never** use `shareNow` or `shareNext`, or create anything that isn't a draft.
- **Never** edit or delete posts, or Ideas, that you did not create in this run.
- Record every draft's id.

### 8. Record and report
- Update `processed.json` for every Idea you looked at.
- Append to `log.md`:
  - the date;
  - for each post: the Idea id, slot, a one-line summary of the captions, the Buffer draft ids per channel and the edit settings;
  - every rejection, skip or error.
- Commit and push to `main`.
- Your final message is a short plain-English summary for the owner: how many drafts are waiting in Buffer, for which days, and anything that needs their attention, such as a photo turned down and why.
