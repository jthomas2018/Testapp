"""`ytm` command-line interface."""

import argparse
import csv
import json
import sys

from . import api, auth


def _split_tags(value):
    return [t.strip() for t in value.split(",") if t.strip()] if value else None


def _print_table(rows, columns):
    if not rows:
        print("(none)")
        return
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    widths = {c: min(w, 60) for c, w in widths.items()}
    print("  ".join(c.ljust(widths[c]) for c in columns))
    for r in rows:
        print("  ".join(str(r.get(c, ""))[:widths[c]].ljust(widths[c]) for c in columns))


def _video_row(v):
    s, st, stats = v["snippet"], v["status"], v.get("statistics", {})
    return {"id": v["id"], "published": s.get("publishedAt", "")[:10],
            "privacy": st["privacyStatus"] + (f" (at {st['publishAt']})" if st.get("publishAt") else ""),
            "views": stats.get("viewCount", ""), "likes": stats.get("likeCount", ""),
            "comments": stats.get("commentCount", ""), "title": s["title"]}


# --- command handlers ------------------------------------------------------------

def cmd_auth(args):
    auth.get_credentials(console=args.no_browser)
    ch = api.my_channel(auth.youtube())
    print(f"Authorized as channel: {ch['snippet']['title']} ({ch['id']})")


def cmd_channel(args):
    ch = api.my_channel(auth.youtube())
    s = ch["statistics"]
    print(f"{ch['snippet']['title']}  ({ch['id']})")
    print(f"Subscribers: {s.get('subscriberCount', 'hidden')}  Views: {s['viewCount']}  Videos: {s['videoCount']}")


def cmd_videos_list(args):
    videos = api.list_videos(auth.youtube(), limit=args.limit)
    if args.json:
        print(json.dumps(videos, indent=2))
    else:
        _print_table([_video_row(v) for v in videos],
                     ["id", "published", "privacy", "views", "likes", "comments", "title"])


def cmd_videos_upload(args):
    def progress(p):
        print(f"\rUploading… {p:.0%}", end="", file=sys.stderr, flush=True)

    yt = auth.youtube()
    desc = open(args.description_file).read() if args.description_file else (args.description or "")
    video = api.upload_video(
        yt, args.file, args.title, desc, tags=_split_tags(args.tags),
        category_id=args.category, privacy=args.privacy, publish_at=args.publish_at,
        made_for_kids=args.made_for_kids, progress=progress,
    )
    print(file=sys.stderr)
    print(f"Uploaded: https://youtu.be/{video['id']}  ({video['status']['privacyStatus']}"
          + (f", publishes {video['status']['publishAt']}" if video["status"].get("publishAt") else "") + ")")
    if args.thumbnail:
        api.set_thumbnail(yt, video["id"], args.thumbnail)
        print("Thumbnail set.")
    if args.playlist:
        api.add_to_playlist(yt, args.playlist, video["id"])
        print(f"Added to playlist {args.playlist}.")


def cmd_videos_update(args):
    desc = open(args.description_file).read() if args.description_file else args.description
    v = api.update_video(
        auth.youtube(), args.video_id, title=args.title, description=desc,
        tags=_split_tags(args.tags), add_tags=_split_tags(args.add_tags),
        category_id=args.category, privacy=args.privacy, publish_at=args.publish_at,
    )
    print(f"Updated {v['id']}: {v['snippet']['title']} [{v['status']['privacyStatus']}]")


def cmd_videos_thumbnail(args):
    api.set_thumbnail(auth.youtube(), args.video_id, args.image)
    print("Thumbnail set.")


def cmd_videos_delete(args):
    if not args.yes and input(f"Permanently delete video {args.video_id}? [y/N] ").lower() != "y":
        print("Aborted.")
        return
    api.delete_video(auth.youtube(), args.video_id)
    print("Deleted.")


EXPORT_FIELDS = ["id", "title", "description", "tags", "privacy", "publish_at"]


def cmd_videos_export(args):
    videos = api.list_videos(auth.youtube(), limit=args.limit)
    with open(args.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_FIELDS)
        w.writeheader()
        for v in videos:
            w.writerow({"id": v["id"], "title": v["snippet"]["title"],
                        "description": v["snippet"].get("description", ""),
                        "tags": ", ".join(v["snippet"].get("tags", [])),
                        "privacy": v["status"]["privacyStatus"],
                        "publish_at": v["status"].get("publishAt", "")})
    print(f"Wrote {len(videos)} videos to {args.csv}. Edit it, then run: ytm videos apply {args.csv}")


def cmd_videos_apply(args):
    yt = auth.youtube()
    with open(args.csv, newline="") as f:
        rows = list(csv.DictReader(f))
    current = {v["id"]: v for v in api.get_videos(yt, [r["id"] for r in rows])}
    changed = 0
    for r in rows:
        v = current.get(r["id"])
        if not v:
            print(f"skip {r['id']}: not found")
            continue
        s, st = v["snippet"], v["status"]
        changes = {}
        if r.get("title") and r["title"] != s["title"]:
            changes["title"] = r["title"]
        if "description" in r and r["description"] != s.get("description", ""):
            changes["description"] = r["description"]
        if "tags" in r:
            new_tags = _split_tags(r["tags"]) or []
            if new_tags != s.get("tags", []):
                changes["tags"] = new_tags
        if r.get("privacy") and r["privacy"] != st["privacyStatus"]:
            changes["privacy"] = r["privacy"]
        if r.get("publish_at") and api.to_rfc3339(r["publish_at"]) != st.get("publishAt"):
            changes["publish_at"] = r["publish_at"]
        if not changes:
            continue
        print(f"{r['id']}: {', '.join(changes)}" + (" (dry run)" if args.dry_run else ""))
        if not args.dry_run:
            api.update_video(yt, r["id"], **changes)
        changed += 1
    print(f"{changed} video(s) {'would change' if args.dry_run else 'updated'}.")


def cmd_playlists_list(args):
    rows = [{"id": p["id"], "items": p["contentDetails"]["itemCount"],
             "privacy": p["status"]["privacyStatus"], "title": p["snippet"]["title"]}
            for p in api.list_playlists(auth.youtube())]
    _print_table(rows, ["id", "items", "privacy", "title"])


def cmd_playlists_create(args):
    p = api.create_playlist(auth.youtube(), args.title, args.description or "", args.privacy)
    print(f"Created playlist {p['id']}: {p['snippet']['title']}")


def cmd_playlists_add(args):
    yt = auth.youtube()
    for vid in args.video_ids:
        api.add_to_playlist(yt, args.playlist_id, vid)
        print(f"Added {vid}")


def cmd_comments_list(args):
    yt = auth.youtube()
    threads = api.list_comments(yt, video_id=args.video, limit=args.limit, moderation=args.status)
    if args.unanswered:
        threads = api.unanswered_comments(yt, api.my_channel(yt)["id"], threads)
    rows = []
    for t in threads:
        c = t["snippet"]["topLevelComment"]["snippet"]
        rows.append({"comment_id": t["id"], "video": t["snippet"].get("videoId", ""),
                     "date": c["publishedAt"][:10], "author": c["authorDisplayName"],
                     "replies": t["snippet"].get("totalReplyCount", 0),
                     "text": c["textDisplay"].replace("\n", " ")})
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        _print_table(rows, ["comment_id", "video", "date", "author", "replies", "text"])


def cmd_comments_reply(args):
    c = api.reply_to_comment(auth.youtube(), args.comment_id, args.text)
    print(f"Replied ({c['id']}).")


def cmd_comments_moderate(args):
    api.moderate_comment(auth.youtube(), args.comment_id, args.status, ban_author=args.ban)
    print(f"Set {args.comment_id} to {args.status}.")


def cmd_comments_delete(args):
    api.delete_comment(auth.youtube(), args.comment_id)
    print("Deleted.")


def cmd_analytics(args):
    ya = auth.analytics()
    if args.report == "summary":
        rows = api.analytics_report(ya, days=args.days)
    elif args.report == "daily":
        rows = api.analytics_report(ya, days=args.days, metrics="views,estimatedMinutesWatched,subscribersGained",
                                    dimensions="day", sort="day")
    elif args.report == "top-videos":
        rows = api.analytics_report(ya, days=args.days, dimensions="video",
                                    metrics="views,estimatedMinutesWatched,averageViewDuration,likes",
                                    sort="-views", limit=args.limit)
        titles = {v["id"]: v["snippet"]["title"]
                  for v in api.get_videos(auth.youtube(), [r["video"] for r in rows])}
        for r in rows:
            r["title"] = titles.get(r["video"], "")
    elif args.report == "traffic":
        rows = api.analytics_report(ya, days=args.days, dimensions="insightTrafficSourceType",
                                    metrics="views,estimatedMinutesWatched", sort="-views")
    elif args.report == "geography":
        rows = api.analytics_report(ya, days=args.days, dimensions="country",
                                    metrics="views,estimatedMinutesWatched", sort="-views", limit=args.limit)
    if args.json:
        print(json.dumps(rows, indent=2))
    elif rows:
        _print_table(rows, list(rows[0].keys()))
    else:
        print("(no data for this period)")


# --- parser ----------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="ytm", description="Manage your YouTube channel from the command line.")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("auth", help="Authorize this tool with your Google account")
    a.add_argument("--no-browser", action="store_true", help="Print the auth URL instead of opening a browser")
    a.set_defaults(func=cmd_auth)

    sub.add_parser("channel", help="Show channel stats").set_defaults(func=cmd_channel)

    # videos
    v = sub.add_parser("videos", help="List, upload, edit and schedule videos").add_subparsers(dest="action", required=True)
    x = v.add_parser("list", help="List recent uploads")
    x.add_argument("--limit", type=int, default=25)
    x.add_argument("--json", action="store_true")
    x.set_defaults(func=cmd_videos_list)

    x = v.add_parser("upload", help="Upload a video (optionally scheduled)")
    x.add_argument("file")
    x.add_argument("--title", required=True)
    x.add_argument("--description")
    x.add_argument("--description-file")
    x.add_argument("--tags", help="Comma-separated")
    x.add_argument("--category", default="22", help="Category ID (22 = People & Blogs)")
    x.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    x.add_argument("--publish-at", help="Schedule, e.g. 2026-10-10T15:00 (local time) — video stays private until then")
    x.add_argument("--made-for-kids", action="store_true")
    x.add_argument("--thumbnail", help="Image to use as the custom thumbnail")
    x.add_argument("--playlist", help="Playlist ID to add the video to")
    x.set_defaults(func=cmd_videos_upload)

    x = v.add_parser("update", help="Edit a video's title, description, tags, privacy or schedule")
    x.add_argument("video_id")
    x.add_argument("--title")
    x.add_argument("--description")
    x.add_argument("--description-file")
    x.add_argument("--tags", help="Replace all tags (comma-separated)")
    x.add_argument("--add-tags", help="Append tags (comma-separated)")
    x.add_argument("--category")
    x.add_argument("--privacy", choices=["private", "unlisted", "public"])
    x.add_argument("--publish-at")
    x.set_defaults(func=cmd_videos_update)

    x = v.add_parser("thumbnail", help="Set a custom thumbnail")
    x.add_argument("video_id")
    x.add_argument("image")
    x.set_defaults(func=cmd_videos_thumbnail)

    x = v.add_parser("delete", help="Permanently delete a video")
    x.add_argument("video_id")
    x.add_argument("--yes", action="store_true")
    x.set_defaults(func=cmd_videos_delete)

    x = v.add_parser("export", help="Export video metadata to CSV for bulk editing")
    x.add_argument("csv")
    x.add_argument("--limit", type=int, default=200)
    x.set_defaults(func=cmd_videos_export)

    x = v.add_parser("apply", help="Apply edits from an exported CSV")
    x.add_argument("csv")
    x.add_argument("--dry-run", action="store_true")
    x.set_defaults(func=cmd_videos_apply)

    # playlists
    pl = sub.add_parser("playlists", help="Manage playlists").add_subparsers(dest="action", required=True)
    pl.add_parser("list").set_defaults(func=cmd_playlists_list)
    x = pl.add_parser("create")
    x.add_argument("title")
    x.add_argument("--description")
    x.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    x.set_defaults(func=cmd_playlists_create)
    x = pl.add_parser("add", help="Add videos to a playlist")
    x.add_argument("playlist_id")
    x.add_argument("video_ids", nargs="+")
    x.set_defaults(func=cmd_playlists_add)

    # comments
    c = sub.add_parser("comments", help="Read, reply to and moderate comments").add_subparsers(dest="action", required=True)
    x = c.add_parser("list")
    x.add_argument("--video", help="Limit to one video (default: whole channel)")
    x.add_argument("--limit", type=int, default=20)
    x.add_argument("--status", choices=["published", "heldForReview", "likelySpam"], default="published")
    x.add_argument("--unanswered", action="store_true", help="Only threads you haven't replied to")
    x.add_argument("--json", action="store_true")
    x.set_defaults(func=cmd_comments_list)
    x = c.add_parser("reply")
    x.add_argument("comment_id", help="Thread / top-level comment ID")
    x.add_argument("text")
    x.set_defaults(func=cmd_comments_reply)
    x = c.add_parser("moderate")
    x.add_argument("comment_id")
    x.add_argument("status", choices=["published", "heldForReview", "rejected"])
    x.add_argument("--ban", action="store_true", help="Also ban the author (only with 'rejected')")
    x.set_defaults(func=cmd_comments_moderate)
    x = c.add_parser("delete", help="Delete one of your own comments")
    x.add_argument("comment_id")
    x.set_defaults(func=cmd_comments_delete)

    # analytics
    x = sub.add_parser("analytics", help="Channel analytics reports")
    x.add_argument("report", choices=["summary", "daily", "top-videos", "traffic", "geography"], nargs="?", default="summary")
    x.add_argument("--days", type=int, default=28)
    x.add_argument("--limit", type=int, default=10)
    x.add_argument("--json", action="store_true")
    x.set_defaults(func=cmd_analytics)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
