#!/usr/bin/env python3
"""
YouTube helper for the TeamTalk AI Bot.
No API key needed - parses YouTube's public pages with urllib.
"""

import json
import re
import urllib.parse
import urllib.request

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


def _fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8', errors='replace')


def _parse_duration(text):
    """'PT4M15S' -> '4:15'"""
    try:
        m = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', text)
        if not m:
            return ''
        h, mi, s = m.group(1), m.group(2), m.group(3)
        h = int(h) if h else 0
        mi = int(mi) if mi else 0
        s = int(s) if s else 0
        if h:
            return '%d:%02d:%02d' % (h, mi, s)
        return '%d:%02d' % (mi, s)
    except Exception:
        return ''


def _parse_count(text):
    """'1234567' -> '1.2M views'"""
    try:
        n = int(text)
    except Exception:
        return ''
    if n >= 1000000000:
        return '%.1fB' % (n / 1000000000)
    if n >= 1000000:
        return '%.1fM' % (n / 1000000)
    if n >= 1000:
        return '%.1fK' % (n / 1000)
    return str(n)


def search_youtube(query, max_results=5):
    """
    Search YouTube, return list of dicts:
    {title, url, channel, views, duration}
    """
    try:
        url = 'https://www.youtube.com/results?search_query=' + urllib.parse.quote(query)
        html = _fetch(url)

        # The page embeds a JSON blob: ytInitialData = {...};
        m = re.search(r'ytInitialData\s*=\s*(\{.*?\});\s*</script>', html, re.DOTALL)
        if not m:
            m = re.search(r'ytInitialData\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not m:
            return []

        data = json.loads(m.group(1))
        results = []

        def walk(node):
            # recursive walk through the JSON to find videoRenderer
            if isinstance(node, dict):
                vr = node.get('videoRenderer')
                if isinstance(vr, dict):
                    try:
                        vid = vr.get('videoId')
                        if not vid:
                            return
                        title = ''
                        for r in vr.get('title', {}).get('runs', []):
                            title += r.get('text', '')
                        channel = ''
                        for r in vr.get('ownerText', {}).get('runs', []):
                            channel += r.get('text', '')
                        views_raw = ''
                        for r in vr.get('viewCountText', {}).get('runs', []):
                            views_raw += r.get('text', '')
                        dur = vr.get('lengthText', {}).get('simpleText', '')
                        results.append({
                            'title': title,
                            'url': 'https://www.youtube.com/watch?v=' + vid,
                            'channel': channel,
                            'views': views_raw,
                            'duration': dur,
                        })
                    except Exception:
                        pass
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)

        # Deduplicate by videoId
        seen = set()
        unique = []
        for r in results:
            if r['url'] not in seen:
                seen.add(r['url'])
                unique.append(r)
        return unique[:max_results]
    except Exception as e:
        print('  -> YouTube search error: ' + str(e))
        return []


def get_video_info(video_url):
    """
    Get info for a single video: {title, channel, views, duration}
    """
    try:
        # Normalize: accept watch?v=ID, youtu.be/ID, short links
        vid = None
        m = re.search(r'[?&]v=([A-Za-z0-9_-]{11})', video_url)
        if m:
            vid = m.group(1)
        if not vid:
            m = re.search(r'youtu\.be/([A-Za-z0-9_-]{11})', video_url)
            if m:
                vid = m.group(1)
        if not vid:
            m = re.search(r'shorts/([A-Za-z0-9_-]{11})', video_url)
            if m:
                vid = m.group(1)
        if not vid:
            m = re.search(r'([A-Za-z0-9_-]{11})', video_url)
            if m:
                vid = m.group(1)
        if not vid:
            return None

        url = 'https://www.youtube.com/watch?v=' + vid
        html = _fetch(url)

        m = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(1))

        vd = data.get('videoDetails', {})
        title = vd.get('title', '')
        channel = vd.get('author', '')
        views = _parse_count(vd.get('viewCount', '0'))
        dur_sec = int(vd.get('lengthSeconds', '0') or 0)
        if dur_sec:
            duration = '%d:%02d' % (dur_sec // 60, dur_sec % 60)
        else:
            duration = ''
        return {
            'title': title,
            'url': 'https://www.youtube.com/watch?v=' + vid,
            'channel': channel,
            'views': views,
            'duration': duration,
        }
    except Exception as e:
        print('  -> YouTube info error: ' + str(e))
        return None


if __name__ == '__main__':
    import sys
    q = ' '.join(sys.argv[1:]) or 'lofi hip hop'
    print('Searching: ' + q)
    for r in search_youtube(q):
        print('- ' + r['title'] + ' | ' + r['duration'] + ' | ' + r['views'])
        print('  ' + r['url'])