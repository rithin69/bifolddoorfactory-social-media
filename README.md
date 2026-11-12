# Bifold Door Factory social posts

Every Monday morning an agent turns the photos in `inbox/` into draft posts in Buffer for Instagram, TikTok and Facebook. Nothing is posted until someone approves it in the Buffer app.

## Adding photos (from a phone or a computer)
1. Open this repository on github.com and go into the `inbox` folder.
2. Tap **Add file**, then **Upload files**, and choose the photos. Real photos of our own jobs only.
3. **Optional but helpful:** add a note with the same name as the photo, ending in `.txt`. For example, `ealing-kitchen.jpg` gets `ealing-kitchen.txt` containing:
   ```
   Ealing, rear extension. 4 panel Schüco bifold, anthracite grey. Flush threshold.
   ```
   The agent only states facts it's given or can see, so a note makes for a better caption.
4. Give photos of the same job the same start to their names: `ealing-1.jpg`, `ealing-2.jpg`.
5. Tap **Commit changes**.

## Each Monday
- The agent picks up to 3 jobs and edits the photos lightly (crop, straighten, light and colour only).
- It writes a caption for each platform and saves drafts in Buffer for Tuesday, Thursday and Saturday at 6pm.
- Open Buffer, check each draft, edit it if you want, then approve it.
- Photos it didn't use stay in `inbox/` for the following week.
- Photos it turned down go to `rejected/`, with the reason in `log.md`.

## Files
- `AGENT.md`: the agent's step-by-step instructions.
- `brand.md`: facts, voice and the claims we never make. Edit it to change how the posts sound.
- `scripts/edit.py`: the photo editor.
- `log.md`: what happened on each run.
