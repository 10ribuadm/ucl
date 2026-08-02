import os
import sys
import json
import subprocess
import requests
import re
import traceback

url = os.environ.get('TARGET_URL')
category = os.environ.get('CATEGORY', 'General')
callback_url = os.environ.get('CALLBACK_URL')
bot_token = os.environ.get('BOT_TOKEN')
chat_id = os.environ.get('CHAT_ID')

if not url:
    print('❌ No Target URL specified!')
    sys.exit(1)

video_id = None
match = re.search(r'(?:v=|\/|shorts\/)([0-9A-Za-z_-]{11})', url)
if match:
    video_id = match.group(1)

title = 'Downloaded Video'
description = f'Source: {url}'
duration = 0
thumb_url = None

if video_id:
    thumb_url = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
    try:
        oembed_resp = requests.get(f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json', timeout=10)
        if oembed_resp.status_code == 200:
            o_data = oembed_resp.json()
            if o_data.get('title'):
                title = o_data['title']
            if o_data.get('author_name'):
                description = f"Channel: {o_data['author_name']}\nSource: {url}"
            if o_data.get('thumbnail_url'):
                thumb_url = o_data['thumbnail_url']
            print('✅ Extracted Video Title via oEmbed API:', title)
    except Exception as e_oe:
        print('oEmbed API error:', e_oe)

video_path = None

def check_valid_video():
    if os.path.exists('/tmp'):
        for f in os.listdir('/tmp'):
            if f.startswith('video.') and f.endswith(('.mp4', '.mkv', '.webm')):
                candidate = os.path.join('/tmp', f)
                if os.path.getsize(candidate) >= 1000000:
                    return candidate
    return None

def fetch_free_proxies():
    print('🌐 Fetching free proxies to bypass YouTube datacenter IP block...')
    proxy_list = []
    try:
        r = requests.get('https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all', timeout=5)
        if r.status_code == 200:
            for line in r.text.split('\n'):
                line = line.strip()
                if line and ':' in line:
                    proxy_list.append(f'http://{line}')
    except Exception as e:
        print('ProxyScrape warning:', e)
    try:
        r2 = requests.get('https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt', timeout=5)
        if r2.status_code == 200:
            for line in r2.text.split('\n'):
                line = line.strip()
                if line and ':' in line:
                    proxy_list.append(f'http://{line}')
    except Exception as e2:
        print('TheSpeedX warning:', e2)
    print(f'🌐 Fetched {len(proxy_list)} candidate proxies.')
    return proxy_list[:25]

# Load cookies if available
cookies_path = None
yt_cookies = os.environ.get('YOUTUBE_COOKIES', '')
if yt_cookies and len(yt_cookies) > 50:
    cookies_path = '/tmp/yt_cookies.txt'
    with open(cookies_path, 'w') as cf:
        cf.write(yt_cookies)
    print(f'🍪 Loaded YouTube Cookies from Secrets (Length: {len(yt_cookies)} bytes)')

# Build cookie args
cookie_args = ['--cookies', cookies_path] if cookies_path else []

# Strategy 1: Direct yt-dlp with multiple player_client combos + Deno JS
print('\n⚡ Strategy #1: Direct yt-dlp + Deno JS Challenge Solver Engine...')
yt_strategies = [
    # 1a: mediaconnect + tv (newest bypass for 2026)
    ['yt-dlp', '--js-runtimes', 'deno', '--extractor-args', 'youtube:player_client=mediaconnect,tv', '-f', 'bv*[height<=1080]+ba/b[height<=1080]/best', '--format-sort', 'res:1080,fps', '--merge-output-format', 'mp4', '--no-playlist', '--no-check-certificates'] + cookie_args + ['-o', '/tmp/video.%(ext)s', url],
    # 1b: ios + mweb
    ['yt-dlp', '--js-runtimes', 'deno', '--extractor-args', 'youtube:player_client=ios,mweb', '-f', 'bv*[height<=1080]+ba/b[height<=1080]/best', '--format-sort', 'res:1080,fps', '--merge-output-format', 'mp4', '--no-playlist', '--no-check-certificates'] + cookie_args + ['-o', '/tmp/video.%(ext)s', url],
    # 1c: android + mweb (original)
    ['yt-dlp', '--js-runtimes', 'deno', '--extractor-args', 'youtube:player_client=android,mweb', '-f', 'bv*[height<=1080]+ba/b[height<=1080]/best', '--format-sort', 'res:1080,fps', '--merge-output-format', 'mp4', '--no-playlist', '--no-check-certificates'] + cookie_args + ['-o', '/tmp/video.%(ext)s', url],
    # 1d: default client with impersonate
    ['yt-dlp', '--js-runtimes', 'deno', '--impersonate', 'chrome', '-f', 'bv*[height<=1080]+ba/b/best', '--merge-output-format', 'mp4', '--no-playlist', '--no-check-certificates'] + cookie_args + ['-o', '/tmp/video.%(ext)s', url],
    # 1e: tv_embedded client  
    ['yt-dlp', '--js-runtimes', 'deno', '--extractor-args', 'youtube:player_client=tv_embedded', '-f', 'b[height<=1080]/best', '--no-playlist', '--no-check-certificates'] + cookie_args + ['-o', '/tmp/video.%(ext)s', url],
]

for idx, cmd in enumerate(yt_strategies):
    print(f'--- 🔄 Trying Direct yt-dlp Strategy #{idx+1}: {" ".join(cmd[3:8])}... ---')
    # Clean old files
    for f in os.listdir('/tmp'):
        if f.startswith('video.') and f.endswith(('.mp4', '.mkv', '.webm', '.part')):
            os.remove(os.path.join('/tmp', f))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.stdout: print(result.stdout[-500:])
    if result.returncode != 0 and result.stderr: print('STDERR:', result.stderr[-300:])
    candidate = check_valid_video()
    if candidate:
        video_path = candidate
        print(f'✅ Direct yt-dlp Strategy #{idx+1} Succeeded!')
        break

# Strategy 2: Proxy-Rotated yt-dlp Engine (Bypasses Datacenter IP Blacklist)
if not video_path:
    print('\n⚡ Strategy #2: Proxy-Rotated yt-dlp Engine...')
    proxies = fetch_free_proxies()
    for p_idx, proxy in enumerate(proxies):
        print(f'--- 🔄 Trying Proxy #{p_idx+1}: {proxy} ---')
        for f in os.listdir('/tmp'):
            if f.startswith('video.') and f.endswith(('.mp4', '.mkv', '.webm', '.part')):
                os.remove(os.path.join('/tmp', f))
        cmd = ['yt-dlp', '--proxy', proxy, '--extractor-args', 'youtube:player_client=mediaconnect,tv', '-f', 'bv*[height<=1080]+ba/b[height<=1080]/best', '--format-sort', 'res:1080,fps', '--merge-output-format', 'mp4', '--no-playlist', '--no-check-certificates'] + cookie_args + ['-o', '/tmp/video.%(ext)s', url]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired:
            print(f'Proxy #{p_idx+1} timed out, skipping...')
            continue
        candidate = check_valid_video()
        if candidate:
            video_path = candidate
            print(f'✅ Proxy-Rotated yt-dlp Strategy (Proxy #{p_idx+1}) Succeeded!')
            break


# Strategy 3: PyTubeFix Engine
if not video_path:
    print('\n⚡ Strategy #3: PyTubeFix Engine...')
    for client_mode in ['ANDROID', 'MWEB']:
        try:
            print(f'Trying PyTubeFix client={client_mode}...')
            from pytubefix import YouTube
            yt = YouTube(url, client=client_mode)
            if yt.title and title == 'Downloaded Video':
                title = yt.title
            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
            if not stream:
                stream = yt.streams.filter(file_extension='mp4').order_by('resolution').desc().first()
            if stream:
                print(f'Downloading stream ({stream.resolution}) via PyTubeFix...')
                stream.download(output_path='/tmp', filename='video.mp4')
                candidate = check_valid_video()
                if candidate:
                    video_path = candidate
                    print(f'✅ Strategy #3 (PyTubeFix {client_mode}) Succeeded!')
                    break
        except Exception as e_ptf:
            print(f'PyTubeFix client={client_mode} error:', e_ptf)

if not video_path or not os.path.exists(video_path) or os.path.getsize(video_path) < 1000000:
    print('\n❌ All GitHub Actions Cloud Machine download strategies failed.')
    sys.exit(1)

file_size = os.path.getsize(video_path)
print(f'\n✅ Downloaded valid video to {video_path} (Size: {file_size} bytes / {(file_size/(1024*1024)):.2f} MB)')

# Faststart Optimization Pass (Relocates MOOV atom to index 0 for instant 0.1s HTML5 Video playback)
faststart_path = '/tmp/video_faststart.mp4'
try:
    print('⚡ Running Faststart Optimization (-movflags +faststart) for instant browser playback...')
    fs_cmd = ['ffmpeg', '-y', '-i', video_path, '-c', 'copy', '-movflags', '+faststart', faststart_path]
    fs_res = subprocess.run(fs_cmd, capture_output=True, text=True, timeout=60)
    if os.path.exists(faststart_path) and os.path.getsize(faststart_path) > 1000000:
        os.replace(faststart_path, video_path)
        print('✅ Faststart Optimization Succeeded! (moov atom relocated to byte 0)')
except Exception as e_fs:
    print('Faststart warning:', e_fs)


# Extract Duration if missing
if duration == 0:
    try:
        dur_res = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path], capture_output=True, text=True)
        if dur_res.returncode == 0 and dur_res.stdout.strip():
            duration = int(float(dur_res.stdout.strip()))
    except Exception: pass

subtitles = []

# Thumbnail Upload
thumb_file_id = None
if thumb_url:
    try:
        t_res = requests.get(thumb_url, timeout=15)
        if t_res.status_code == 200:
            thumb_path = '/tmp/thumb.jpg'
            with open(thumb_path, 'wb') as tf:
                tf.write(t_res.content)
            clean_t = re.sub(r'[^\w\s-]', '', title).strip() or 'Video'
            with open(thumb_path, 'rb') as tf:
                files = {'photo': (f'thumb_{clean_t[:20]}.jpg', tf, 'image/jpeg')}
                resp = requests.post(f'https://api.telegram.org/bot{bot_token}/sendPhoto', data={'chat_id': chat_id, 'caption': f'🖼️ Cover Thumbnail for {title[:40]}'}, files=files)
                if resp.status_code == 200 and resp.json().get('ok'):
                    photos = resp.json()['result']['photo']
                    thumb_file_id = photos[-1]['file_id']
                    print('🖼️ HD Cover Thumbnail uploaded successfully! File ID:', thumb_file_id)
            if os.path.exists(thumb_path): os.remove(thumb_path)
    except Exception as e_th:
        print('Thumbnail upload warning:', e_th)

# Video Upload
CHUNK_SIZE = 15 * 1024 * 1024
parts = []
main_file_id = None
clean_title = re.sub(r'[^\w\s-]', '', title).strip() or 'Video'

with open(video_path, 'rb') as vf:
    part_idx = 0
    offset = 0
    num_parts = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    while offset < file_size:
        chunk = vf.read(CHUNK_SIZE)
        chunk_len = len(chunk)
        chunk_path = f'/tmp/chunk_{part_idx}.mp4'
        with open(chunk_path, 'wb') as cf:
            cf.write(chunk)
        
        upload_filename = f"{clean_title[:30]}.mp4" if num_parts == 1 else f"{clean_title[:30]}_part{part_idx+1}.mp4"
        
        with open(chunk_path, 'rb') as cf:
            files = {'document': (upload_filename, cf, 'video/mp4')}
            resp = requests.post(f'https://api.telegram.org/bot{bot_token}/sendDocument', data={'chat_id': chat_id, 'caption': f'🎬 {title[:40]} (Part {part_idx+1}/{num_parts})'}, files=files)
            if resp.status_code == 200 and resp.json().get('ok'):
                res_obj = resp.json().get('result', {})
                doc = res_obj.get('document') or res_obj.get('video')
                if doc:
                    fid = doc.get('file_id')
                    msg_id = res_obj.get('message_id')
                    if part_idx == 0: main_file_id = fid
                    parts.append({'partIndex': part_idx, 'fileId': fid, 'messageId': msg_id, 'startByte': offset, 'endByte': offset + chunk_len - 1, 'chunkSize': chunk_len})
        
        if os.path.exists(chunk_path): os.remove(chunk_path)
        offset += chunk_len
        part_idx += 1

payload = {
    'status': 'success',
    'media': {
        'title': title,
        'description': description[:500],
        'category': category,
        'duration': duration,
        'fileSize': file_size,
        'fileType': 'video',
        'mimeType': 'video/mp4',
        'fileId': main_file_id,
        'thumbnailFileId': thumb_file_id or main_file_id,
        'parts': parts,
        'subtitles': subtitles
    }
}

print('📡 Sending Completion Callback to VPS:', callback_url)
try:
    cb_res = requests.post(callback_url, json=payload, timeout=15)
    print('✅ Process Completed Successfully! Callback status:', cb_res.status_code)
except Exception as e_cb:
    print('Callback warning:', e_cb)
