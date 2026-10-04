# ytmanager — manage your YouTube channel from the command line

`ytm` wraps the official YouTube Data API v3 and YouTube Analytics API v2 so you can
upload and schedule videos, bulk-edit metadata, manage playlists, triage comments,
and pull analytics without clicking through YouTube Studio.

## One-time setup

1. **Create a Google Cloud project** at <https://console.cloud.google.com/>.
2. **Enable APIs:** *YouTube Data API v3* and *YouTube Analytics API*.
3. **OAuth consent screen:** choose *External*, fill in the app name, and add your own
   Google account under *Test users*.
4. **Credentials → Create credentials → OAuth client ID → Desktop app.** Download the
   JSON and save it as `client_secret.json` in the directory you run `ytm` from
   (or point `YTM_CLIENT_SECRET` at it).
5. Install and authorize:

   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   ytm auth            # opens a browser; pick the Google account that owns the channel
   ```

   The token is cached in `token.json` (override with `YTM_TOKEN`). Both files are
   git-ignored. Never commit them.

## Everyday commands

```bash
ytm channel                                   # subscribers / views / video count
ytm videos list --limit 10                    # recent uploads with stats + privacy

# Upload, scheduled to go public at 3pm local time, with thumbnail and playlist
ytm videos upload clip.mp4 --title "My video" --description-file desc.txt \
    --tags "vlog,travel" --publish-at 2026-10-10T15:00 \
    --thumbnail thumb.png --playlist PLxxxx

ytm videos update VIDEO_ID --title "Better title" --add-tags "shorts"
ytm videos update VIDEO_ID --privacy public
ytm videos thumbnail VIDEO_ID thumb.png

# Bulk-edit titles/descriptions/tags/privacy/schedule in a spreadsheet
ytm videos export videos.csv
#   ...edit videos.csv...
ytm videos apply videos.csv --dry-run         # preview
ytm videos apply videos.csv

ytm playlists list
ytm playlists create "Best of 2026" --privacy public
ytm playlists add PLxxxx VIDEO_ID1 VIDEO_ID2

ytm comments list --unanswered                # channel-wide threads you haven't replied to
ytm comments list --status heldForReview      # moderation queue
ytm comments reply COMMENT_ID "Thanks for watching!"
ytm comments moderate COMMENT_ID rejected --ban

ytm analytics                                 # last 28 days summary
ytm analytics top-videos --days 7
ytm analytics daily | traffic | geography
```

Add `--json` to `videos list`, `comments list` or `analytics` to get output you can
pipe into other tools.

## Notes

- Uploads with `--publish-at` are kept *private* until the scheduled time (this is how
  the YouTube API does scheduling).
- `videos update` only changes the fields you pass. Everything else stays as it was.
- The default YouTube API quota is 10,000 units a day. An upload costs about 1,600 and
  each metadata update about 50, so bulk edits of a few hundred videos fit in one day.
- Videos uploaded through an **unverified** Google Cloud project may be locked as
  private until the project passes YouTube's API audit. For personal use, upload
  as private and publish in Studio, or apply for the audit.

## Development

```bash
pip install -e '.[dev]'
pytest
```
