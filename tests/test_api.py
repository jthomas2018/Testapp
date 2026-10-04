from unittest.mock import MagicMock

from ytmanager import api


def fake_video(**overrides):
    v = {
        "id": "vid1",
        "snippet": {"title": "Old", "description": "desc", "tags": ["a"], "categoryId": "22"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    for key, val in overrides.items():
        v[key].update(val)
    return v


def yt_with(video):
    yt = MagicMock()
    yt.videos().list().execute.return_value = {"items": [video]}
    yt.videos().update.side_effect = lambda part, body: MagicMock(execute=lambda: body)
    return yt


def test_update_video_preserves_untouched_fields():
    yt = yt_with(fake_video())
    body = api.update_video(yt, "vid1", title="New", add_tags=["b", "a"])
    assert body["snippet"] == {"title": "New", "description": "desc", "categoryId": "22", "tags": ["a", "b"]}
    assert body["status"] == {"privacyStatus": "public", "selfDeclaredMadeForKids": False}


def test_update_video_schedule_forces_private():
    yt = yt_with(fake_video())
    body = api.update_video(yt, "vid1", publish_at="2026-10-10T15:00:00Z")
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"] == "2026-10-10T15:00:00Z"


def test_update_video_keeps_existing_schedule():
    yt = yt_with(fake_video(status={"privacyStatus": "private", "publishAt": "2026-11-01T00:00:00Z"}))
    body = api.update_video(yt, "vid1", title="x")
    assert body["status"]["publishAt"] == "2026-11-01T00:00:00Z"


def test_to_rfc3339_converts_offsets_to_utc():
    assert api.to_rfc3339("2026-10-10T15:00:00+02:00") == "2026-10-10T13:00:00Z"
    assert api.to_rfc3339("2026-10-10T15:00:00Z") == "2026-10-10T15:00:00Z"


def test_unanswered_comments_filters_threads_with_channel_reply():
    me = "UCme"
    def thread(tid, author, replies):
        return {"id": tid, "snippet": {"totalReplyCount": replies, "topLevelComment": {
            "snippet": {"authorChannelId": {"value": author}}}}}
    threads = [thread("t1", "UCfan", 0), thread("t2", "UCfan", 1), thread("t3", me, 0), thread("t4", "UCfan", 1)]
    yt = MagicMock()
    replies = {
        "t2": [{"snippet": {"authorChannelId": {"value": me}}}],
        "t4": [{"snippet": {"authorChannelId": {"value": "UCother"}}}],
    }
    yt.comments().list.side_effect = lambda part, parentId, maxResults: MagicMock(
        execute=lambda: {"items": replies[parentId]})
    assert [t["id"] for t in api.unanswered_comments(yt, me, threads)] == ["t1", "t4"]


def test_analytics_report_maps_rows_to_dicts():
    ya = MagicMock()
    ya.reports().query().execute.return_value = {
        "columnHeaders": [{"name": "day"}, {"name": "views"}],
        "rows": [["2026-10-01", 10], ["2026-10-02", 12]],
    }
    assert api.analytics_report(ya, days=2) == [{"day": "2026-10-01", "views": 10}, {"day": "2026-10-02", "views": 12}]


def test_cli_parser_builds():
    from ytmanager.cli import build_parser
    args = build_parser().parse_args(["videos", "update", "abc", "--add-tags", "x,y"])
    assert args.video_id == "abc" and args.add_tags == "x,y"
