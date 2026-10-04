"""Thin, testable wrappers over the YouTube Data API v3 and Analytics API v2.

Every function takes the API service object as its first argument so tests can
pass a fake.
"""

from datetime import date, datetime, timedelta, timezone


# --- channel -----------------------------------------------------------------

def my_channel(yt):
    resp = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise SystemExit("No YouTube channel found for this Google account.")
    return items[0]


def uploads_playlist_id(yt):
    return my_channel(yt)["contentDetails"]["relatedPlaylists"]["uploads"]


# --- videos ------------------------------------------------------------------

def list_videos(yt, limit=25):
    """Most recent uploads with stats and status, newest first."""
    playlist = uploads_playlist_id(yt)
    ids, token = [], None
    while len(ids) < limit:
        resp = yt.playlistItems().list(
            part="contentDetails", playlistId=playlist,
            maxResults=min(50, limit - len(ids)), pageToken=token,
        ).execute()
        ids += [i["contentDetails"]["videoId"] for i in resp.get("items", [])]
        token = resp.get("nextPageToken")
        if not token:
            break
    return get_videos(yt, ids)


def get_videos(yt, video_ids):
    out = []
    for start in range(0, len(video_ids), 50):
        chunk = video_ids[start:start + 50]
        resp = yt.videos().list(part="snippet,statistics,status", id=",".join(chunk)).execute()
        out += resp.get("items", [])
    return out


def upload_video(yt, path, title, description="", tags=None, category_id="22",
                 privacy="private", publish_at=None, made_for_kids=False, progress=None):
    """Upload a file. If publish_at is set the video stays private until then."""
    from googleapiclient.http import MediaFileUpload

    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids}
    if publish_at:
        status["privacyStatus"] = "private"  # required by the API for scheduling
        status["publishAt"] = to_rfc3339(publish_at)
    body = {
        "snippet": {"title": title, "description": description,
                    "tags": tags or [], "categoryId": category_id},
        "status": status,
    }
    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        chunk_status, response = request.next_chunk()
        if chunk_status and progress:
            progress(chunk_status.progress())
    return response


def update_video(yt, video_id, title=None, description=None, tags=None, add_tags=None,
                 category_id=None, privacy=None, publish_at=None):
    """Patch only the fields given; everything else is preserved."""
    current = get_videos(yt, [video_id])
    if not current:
        raise SystemExit(f"Video {video_id} not found.")
    video = current[0]
    snippet = video["snippet"]
    status = video["status"]

    new_snippet = {
        "title": title if title is not None else snippet["title"],
        "description": description if description is not None else snippet.get("description", ""),
        "categoryId": category_id or snippet["categoryId"],
        "tags": list(tags) if tags is not None else list(snippet.get("tags", [])),
    }
    for tag in add_tags or []:
        if tag not in new_snippet["tags"]:
            new_snippet["tags"].append(tag)
    if snippet.get("defaultLanguage"):
        new_snippet["defaultLanguage"] = snippet["defaultLanguage"]

    new_status = {"privacyStatus": privacy or status["privacyStatus"]}
    if "selfDeclaredMadeForKids" in status:
        new_status["selfDeclaredMadeForKids"] = status["selfDeclaredMadeForKids"]
    if publish_at:
        new_status["privacyStatus"] = "private"
        new_status["publishAt"] = to_rfc3339(publish_at)
    elif status.get("publishAt") and not privacy:
        new_status["publishAt"] = status["publishAt"]

    body = {"id": video_id, "snippet": new_snippet, "status": new_status}
    return yt.videos().update(part="snippet,status", body=body).execute()


def set_thumbnail(yt, video_id, image_path):
    from googleapiclient.http import MediaFileUpload

    return yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(image_path))).execute()


def delete_video(yt, video_id):
    yt.videos().delete(id=video_id).execute()


# --- playlists -----------------------------------------------------------------

def list_playlists(yt, limit=50):
    items, token = [], None
    while len(items) < limit:
        resp = yt.playlists().list(
            part="snippet,contentDetails,status", mine=True,
            maxResults=min(50, limit - len(items)), pageToken=token,
        ).execute()
        items += resp.get("items", [])
        token = resp.get("nextPageToken")
        if not token:
            break
    return items


def create_playlist(yt, title, description="", privacy="private"):
    body = {"snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy}}
    return yt.playlists().insert(part="snippet,status", body=body).execute()


def add_to_playlist(yt, playlist_id, video_id):
    body = {"snippet": {"playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
    return yt.playlistItems().insert(part="snippet", body=body).execute()


# --- comments ------------------------------------------------------------------

def list_comments(yt, video_id=None, limit=20, moderation="published", order="time"):
    """Top-level comment threads on one video, or across the whole channel."""
    params = {"part": "snippet", "maxResults": min(100, limit),
              "moderationStatus": moderation, "order": order, "textFormat": "plainText"}
    if video_id:
        params["videoId"] = video_id
    else:
        params["allThreadsRelatedToChannelId"] = my_channel(yt)["id"]
    items, token = [], None
    while len(items) < limit:
        resp = yt.commentThreads().list(pageToken=token, **params).execute()
        items += resp.get("items", [])
        token = resp.get("nextPageToken")
        if not token:
            break
    return items[:limit]


def unanswered_comments(yt, channel_id, threads):
    """Threads whose top comment wasn't written by the channel and that have no reply from it."""
    out = []
    for t in threads:
        top = t["snippet"]["topLevelComment"]["snippet"]
        if top.get("authorChannelId", {}).get("value") == channel_id:
            continue
        if t["snippet"].get("totalReplyCount", 0) == 0:
            out.append(t)
            continue
        replies = yt.comments().list(part="snippet", parentId=t["id"], maxResults=100).execute()
        if not any(r["snippet"].get("authorChannelId", {}).get("value") == channel_id
                   for r in replies.get("items", [])):
            out.append(t)
    return out


def reply_to_comment(yt, parent_id, text):
    body = {"snippet": {"parentId": parent_id, "textOriginal": text}}
    return yt.comments().insert(part="snippet", body=body).execute()


def moderate_comment(yt, comment_id, status, ban_author=False):
    """status: published | heldForReview | rejected"""
    yt.comments().setModerationStatus(
        id=comment_id, moderationStatus=status, banAuthor=ban_author,
    ).execute()


def delete_comment(yt, comment_id):
    yt.comments().delete(id=comment_id).execute()


# --- analytics -----------------------------------------------------------------

DEFAULT_METRICS = "views,estimatedMinutesWatched,averageViewDuration,likes,comments,subscribersGained,subscribersLost"


def analytics_report(ya, days=28, metrics=DEFAULT_METRICS, dimensions=None, sort=None,
                     limit=None, video_id=None, end=None):
    end = end or date.today()
    start = end - timedelta(days=days)
    params = {"ids": "channel==MINE", "startDate": start.isoformat(),
              "endDate": end.isoformat(), "metrics": metrics}
    if dimensions:
        params["dimensions"] = dimensions
    if sort:
        params["sort"] = sort
    if limit:
        params["maxResults"] = limit
    if video_id:
        params["filters"] = f"video=={video_id}"
    resp = ya.reports().query(**params).execute()
    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    return [dict(zip(headers, row)) for row in resp.get("rows", [])]


# --- helpers -------------------------------------------------------------------

def to_rfc3339(value):
    """Accept '2026-10-10T15:00', '2026-10-10 15:00', or a datetime; naive means local time."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
