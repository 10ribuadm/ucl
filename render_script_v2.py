"""
HayukTube Cloud Render Engine v2.0 — Single Quality Worker
Each GitHub Actions job renders EXACTLY ONE quality tier.
Quality is passed via QUALITY env var: 240p / 360p / 480p / 720p / 1080p

Triggered from: render-240p.yml, render-360p.yml, render-480p.yml,
                render-720p.yml, render-1080p.yml
"""

import os, sys, json, subprocess, requests, re, traceback, time

# ─── ENV VARS ────────────────────────────────────────────────────────────────
url           = os.environ.get('TARGET_URL', '').strip()
category      = os.environ.get('CATEGORY', 'General')
callback_url  = os.environ.get('CALLBACK_URL', '')
bot_token     = os.environ.get('BOT_TOKEN', '')
chat_id       = os.environ.get('CHAT_ID', '')
quality       = os.environ.get('QUALITY', '720p')          # e.g. 240p / 1080p
yt_cookies    = os.environ.get('YOUTUBE_COOKIES', '')

if not url:
    print('❌ No TARGET_URL specified!'); sys.exit(1)

# ─── QUALITY → FFmpeg HEIGHT MAP ─────────────────────────────────────────────
QUALITY_MAP = {
    '144p':  {'height': 144,  'vbr': '150k',  'abr': '48k',  'label': '144p Ultra Low'},
    '240p':  {'height': 240,  'vbr': '300k',  'abr': '64k',  'label': '240p Hemat Data'},
    '360p':  {'height': 360,  'vbr': '600k',  'abr': '96k',  'label': '360p Standard'},
    '480p':  {'height': 480,  'vbr': '1000k', 'abr': '128k', 'label': '480p SD'},
    '720p':  {'height': 720,  'vbr': '2500k', 'abr': '128k', 'label': '720p HD'},
    '1080p': {'height': 1080, 'vbr': '5000k', 'abr': '192k', 'label': '1080p Full HD'},
}
if quality not in QUALITY_MAP:
    print(f'❌ Unknown quality: {quality}. Valid: {list(QUALITY_MAP.keys())}'); sys.exit(1)

qconf  = QUALITY_MAP[quality]
height = qconf['height']
vbr    = qconf['vbr']
abr    = qconf['abr']
qlabel = qconf['label']

print(f'\n🎯 HayukTube Cloud Render v2 — Quality Worker: [{quality}] ({qlabel})')
print(f'🎬 Target URL : {url}')
print(f'📦 Telegram   : {chat_id}')

# ─── HELPERS ─────────────────────────────────────────────────────────────────
video_id = None
match = re.search(r'(?:v=|/|shorts/)([0-9A-Za-z_-]{11})', url)
if match:
    video_id = match.group(1)

title       = 'Downloaded Video'
description = f'Source: {url}'
duration    = 0
thumb_url   = None

# ─── LOG PROGRESS HELPER (Socket.IO Stream Receiver) ───────────────────────
def log_progress(stage, percent, message):
    if not callback_url: return
    try:
        base_api = re.sub(r'/api/.*$', '', callback_url)
        log_url  = f'{base_api}/api/render-log'
        requests.post(log_url, json={
            'url': url,
            'title': f'[{quality}] {title}',
            'stage': stage,
            'percent': percent,
            'message': f'⚡ [{quality}] {message}',
            'timestamp': int(time.time() * 1000)
        }, timeout=5)
    except Exception as e:
        print(f'Log notice: {e}')

log_progress('initializing', 10, f'Runner v2 [{quality}] diinisialisasi untuk {url}')

# HD thumbnail (maxresdefault → sddefault → hqdefault)
if video_id:
    for cand in [
        f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg',
        f'https://img.youtube.com/vi/{video_id}/sddefault.jpg',
        f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
    ]:
        try:
            r = requests.head(cand, timeout=5)
            if r.status_code == 200:
                thumb_url = cand
                print(f'🖼️ HD Thumbnail : {thumb_url}')
                break
        except Exception:
            pass
    if not thumb_url:
        thumb_url = f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg'

    try:
        oe = requests.get(
            f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json',
            timeout=10
        )
        if oe.status_code == 200:
            d = oe.json()
            if d.get('title'):       title = d['title']
            if d.get('author_name'): description = f"Channel: {d['author_name']}\nSource: {url}"
            print(f'✅ Video Title   : {title}')
    except Exception as e:
        print(f'oEmbed warning: {e}')

log_progress('downloading', 25, f'Mengunduh stream video [{quality}] ({title[:40]})...')

# ─── COOKIES ─────────────────────────────────────────────────────────────────
cookies_path = None
if yt_cookies and len(yt_cookies) > 50:
    cookies_path = '/tmp/yt_cookies.txt'
    with open(cookies_path, 'w') as cf:
        cf.write(yt_cookies)
    print(f'🍪 Cookies loaded ({len(yt_cookies)} bytes)')
elif os.path.exists('yt_cookies.txt'):
    cookies_path = 'yt_cookies.txt'
    print(f'🍪 Local Cookies loaded ({os.path.getsize(cookies_path)} bytes)')
elif os.path.exists('/tmp/yt_cookies.txt'):
    cookies_path = '/tmp/yt_cookies.txt'
    print(f'🍪 Temp Cookies loaded ({os.path.getsize(cookies_path)} bytes)')
else:
    print('⚠️  No YOUTUBE_COOKIES — some videos may fail')

cookie_args = ['--cookies', cookies_path, '--remote-components', 'ejs:github'] if cookies_path else ['--remote-components', 'ejs:github'] if cookies_path else []

# ─── DOWNLOAD: yt-dlp (best format for target quality) ───────────────────────
def clean_tmp():
    for f in os.listdir('/tmp'):
        if f.startswith('video.') and f.endswith(('.mp4','.mkv','.webm','.part')):
            try: os.remove(f'/tmp/{f}')
            except: pass

def check_valid_video():
    for f in os.listdir('/tmp'):
        if f.startswith('video.') and f.endswith(('.mp4','.mkv','.webm')):
            p = f'/tmp/{f}'
            if os.path.getsize(p) >= 500_000:
                return p
    return None

# yt-dlp format selector: Try target height first, then fallback to best available stream
fmt = f'bv*[height<={height}]+ba/bv*[height<={height}]+ba[language=id]/bv*+ba/b[height<={height}]/bestvideo+bestaudio/best'
lang_args = ['--extractor-args', 'youtube:lang=id', '--add-header', 'Accept-Language:id-ID,id;q=0.9,en;q=0.8']

STRATEGIES = [
    ['yt-dlp', '--js-runtimes', 'deno', '--remote-components', 'ejs:github',
     '-f', fmt, '--format-sort', f'res:{height},fps', '--merge-output-format', 'mp4',
     '--no-playlist', '--no-check-certificates'] + lang_args + cookie_args + ['-o', '/tmp/video.%(ext)s', url],

    ['yt-dlp', '--js-runtimes', 'deno', '--remote-components', 'ejs:github', '--extractor-args', 'youtube:player_client=mweb,web',
     '-f', fmt, '--format-sort', f'res:{height},fps', '--merge-output-format', 'mp4',
     '--no-playlist', '--no-check-certificates'] + lang_args + cookie_args + ['-o', '/tmp/video.%(ext)s', url],

    ['yt-dlp', '--js-runtimes', 'deno', '--remote-components', 'ejs:github', '--extractor-args', 'youtube:player_client=ios,android',
     '-f', fmt, '--format-sort', f'res:{height},fps', '--merge-output-format', 'mp4',
     '--no-playlist', '--no-check-certificates'] + lang_args + cookie_args + ['-o', '/tmp/video.%(ext)s', url]
]

video_path = None
print(f'\n⬇️  Downloading [{quality}]...')
for i, cmd in enumerate(STRATEGIES):
    print(f'--- Strategy #{i+1} ---')
    clean_tmp()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if res.stdout: print(res.stdout[-400:])
        if res.returncode != 0 and res.stderr: print('STDERR:', res.stderr[-300:])
    except subprocess.TimeoutExpired:
        print(f'Strategy #{i+1} timed out'); continue
    v = check_valid_video()
    if v:
        video_path = v
        print(f'✅ Download OK [{quality}] — {os.path.getsize(v)/(1024*1024):.1f} MB')
        break

if not video_path:
    print(f'❌ All download strategies failed for [{quality}]')
    sys.exit(1)

# ─── TRANSCODE to exact quality ───────────────────────────────────────────────
out_path = f'/tmp/video_{quality}.mp4'
print(f'\n🔧 Transcoding to [{quality}] — height={height} vbr={vbr} abr={abr}...')
log_progress('transcoding', 50, f'Mengoversi video ke [{quality}] dengan FFmpeg...')
preset = 'ultrafast' if height <= 480 else 'superfast'
ff_cmd = [
    'ffmpeg', '-y', '-i', video_path,
    '-vf', f'scale=-2:{height}',
    '-c:v', 'libx264', '-b:v', vbr, '-maxrate', vbr, '-bufsize', str(int(vbr[:-1])*2)+'k',
    '-preset', preset, '-tune', 'fastdecode',
    '-c:a', 'aac', '-b:a', abr, '-ac', '2',
    '-movflags', '+faststart',
    '-threads', '0',
    out_path
]
try:
    ff = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=3600)
    if ff.returncode != 0:
        print('FFmpeg STDERR:', ff.stderr[-500:])
        # fallback: try to use downloaded file directly without transcode
        print('⚠️  Transcode failed — trying faststart pass on original...')
        ff2 = subprocess.run(
            ['ffmpeg', '-y', '-i', video_path, '-c', 'copy', '-movflags', '+faststart', out_path],
            capture_output=True, text=True, timeout=120
        )
        if ff2.returncode != 0 or not os.path.exists(out_path):
            print('❌ Faststart pass also failed'); sys.exit(1)
except subprocess.TimeoutExpired:
    print(f'❌ FFmpeg transcode timed out for [{quality}]'); sys.exit(1)

if not os.path.exists(out_path) or os.path.getsize(out_path) < 100_000:
    print(f'❌ Transcoded file missing or too small for [{quality}]'); sys.exit(1)

file_size = os.path.getsize(out_path)
print(f'✅ Transcode OK — {file_size/(1024*1024):.1f} MB')

# ─── Get Duration ─────────────────────────────────────────────────────────────
try:
    dr = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', out_path],
        capture_output=True, text=True
    )
    if dr.returncode == 0 and dr.stdout.strip():
        duration = int(float(dr.stdout.strip()))
except Exception: pass

# ─── Upload Thumbnail (ONLY 1 Thumbnail per Video, handled by 144p/240p worker) ───
thumb_file_id = None
if thumb_url and (quality in ['144p', '240p'] or os.environ.get('FORCE_THUMBNAIL', 'false').lower() == 'true'):
    try:
        t_res = requests.get(thumb_url, timeout=15)
        if t_res.status_code == 200:
            thumb_path = '/tmp/thumb.jpg'
            with open(thumb_path, 'wb') as tf: tf.write(t_res.content)
            clean_t = re.sub(r'[^\w\s-]', '', title).strip()[:20] or 'Video'
            with open(thumb_path, 'rb') as tf:
                r = requests.post(
                    f'https://api.telegram.org/bot{bot_token}/sendPhoto',
                    data={'chat_id': chat_id, 'caption': f'🖼️ Cover Thumbnail for {title[:40]}'},
                    files={'photo': (f'thumb_{clean_t}.jpg', tf, 'image/jpeg')}
                )
                if r.status_code == 200 and r.json().get('ok'):
                    photos = r.json()['result']['photo']
                    thumb_file_id = photos[-1]['file_id']
                    print(f'🖼️ Cover Thumbnail uploaded — file_id: {thumb_file_id}')
            if os.path.exists(thumb_path): os.remove(thumb_path)
    except Exception as e:
        print(f'Thumbnail warning: {e}')
else:
    print(f'ℹ️ [{quality}] Skipping duplicate thumbnail upload (thumbnail is uploaded once by 240p worker)')

# ─── Upload Video (chunked) ───────────────────────────────────────────────────
CHUNK_SIZE = 15 * 1024 * 1024
parts = []
main_file_id = None
clean_title = re.sub(r'[^\w\s-]', '', title).strip()[:30] or 'Video'
num_parts = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

print(f'\n📤 Uploading [{quality}] to Telegram ({num_parts} part(s))...')
log_progress('uploading', 80, f'Mengunggah berkas [{quality}] ({num_parts} part) ke Telegram Cloud Vault...')

with open(out_path, 'rb') as vf:
    part_idx = 0
    offset   = 0
    while offset < file_size:
        chunk     = vf.read(CHUNK_SIZE)
        chunk_len = len(chunk)
        chunk_path = f'/tmp/chunk_{quality}_{part_idx}.mp4'
        with open(chunk_path, 'wb') as cf: cf.write(chunk)

        fname = f'{clean_title}_{quality}.mp4' if num_parts == 1 else f'{clean_title}_{quality}_pt{part_idx+1}.mp4'
        with open(chunk_path, 'rb') as cf:
            r = requests.post(
                f'https://api.telegram.org/bot{bot_token}/sendDocument',
                data={'chat_id': chat_id, 'caption': f'🎬 [{quality}] {title[:40]} (Part {part_idx+1}/{num_parts})'},
                files={'document': (fname, cf, 'video/mp4')},
                timeout=120
            )
            if r.status_code == 200 and r.json().get('ok'):
                res_obj = r.json().get('result', {})
                doc = res_obj.get('document') or res_obj.get('video')
                if doc:
                    fid   = doc.get('file_id')
                    msg_id = res_obj.get('message_id')
                    if part_idx == 0: main_file_id = fid
                    parts.append({
                        'partIndex': part_idx, 'fileId': fid, 'messageId': msg_id,
                        'startByte': offset, 'endByte': offset + chunk_len - 1, 'chunkSize': chunk_len
                    })
                    print(f'✅ Part {part_idx+1}/{num_parts} uploaded — file_id: {fid}')
                    log_progress('uploading', int(80 + (part_idx+1)/num_parts * 15), f'Part {part_idx+1}/{num_parts} [{quality}] terunggah')
            else:
                print(f'⚠️  Upload part {part_idx+1} failed: {r.text[:200]}')

        if os.path.exists(chunk_path): os.remove(chunk_path)
        offset   += chunk_len
        part_idx += 1

log_progress('completed', 100, f'✅ Process Selesai! Video [{quality}] berhasil diimpor ke Cloud Storage!')

# ─── Callback to VPS ─────────────────────────────────────────────────────────
payload = {
    'status':  'success',
    'quality': quality,
    'media': {
        'title':            title,
        'description':      description[:500],
        'category':         category,
        'duration':         duration,
        'fileSize':         file_size,
        'fileType':         'video',
        'mimeType':         'video/mp4',
        'quality':          quality,
        'fileId':           main_file_id,
        'thumbnailFileId':  thumb_file_id,
        'parts':            parts,
        'qualities':        {
            quality: {
                'quality':  quality,
                'fileId':   main_file_id,
                'parts':    parts,
                'fileSize': file_size
            }
        },
        'subtitles':        []
    }
}

print(f'\n📡 Sending callback → {callback_url}')
try:
    cb = requests.post(callback_url, json=payload, timeout=15)
    print(f'✅ Callback sent! Status: {cb.status_code} — [{quality}] DONE 🎉')
except Exception as e:
    print(f'Callback warning: {e}')
