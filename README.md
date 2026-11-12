# Bifold Door Factory social posts

Every Monday at 8am (UK time) a Claude agent turns new photo **Ideas** in Buffer into draft posts for Instagram, TikTok and Facebook. Nothing is posted until someone approves it in the Buffer app.

## For the owner: adding photos
1. Open the Buffer app and tap **Create**, then **Idea**.
2. Add the photos of one job and a short note, for example "Ealing, rear extension, 4 panel Schüco bifold, anthracite grey".
3. Tap **Save**.

On Monday the drafts appear in Buffer for Tuesday, Thursday and Saturday at 6pm. Check them, edit anything you want, and approve.

## What's in this repository
This repository is public so that Buffer can fetch the edited images. It never holds original photos or customer details.

- `AGENT.md`: the agent's step-by-step instructions.
- `brand.md`: facts, voice and the claims we never make. Edit it to change how the posts sound.
- `scripts/edit.py`: the light photo editor. It crops, straightens and corrects light and colour, and strips location data.
- `images/`: the edited images, one folder per week.
- `processed.json`: the Buffer Ideas already used.
- `log.md`: what happened on each run.
