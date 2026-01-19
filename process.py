import requests
import re
from urllib.parse import urlparse
from collections import defaultdict
import subprocess
import concurrent.futures

# Set to True to enable pipe wrappers in cleaned_pipe.m3u (always applied there)
use_pipe = True

# Function to check if stream is active (using ffprobe)
def check_stream_active(url, timeout=20):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', '-i', url],
            timeout=timeout, capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
        return False
    except Exception:
        return False

# Keywords to filter out (case-insensitive)
filter_keywords = ["sport", "football", "soccer", "nba", "nfl", "espn", "tennis", "cricket", "boxing", "TSN", "golf", "news"]

# EPG URL
epg_url = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"

# Read links from links.txt
with open("links.txt", "r") as f:
    urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Read order from order.txt
with open("order.txt", "r") as f:
    order_list = [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]

# List to store potential channels before active check
potential_channels = []  # List of (title_lower, extinf, url)

for url in urls:
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            lines = response.text.strip().splitlines()
            i = 0
            while i < len(lines):
                if lines[i].startswith("#EXTINF:"):
                    extinf = lines[i]
                    if i + 1 < len(lines) and not lines[i+1].startswith("#"):
                        stream_url = lines[i+1]
                        title_match = re.search(r',(.*)$', extinf)
                        if title_match:
                            title = title_match.group(1).strip()
                            title_lower = title.lower()
                            if any(kw in title_lower for kw in filter_keywords):
                                i += 2
                                continue
                            if urlparse(stream_url).scheme in ("http", "https"):
                                potential_channels.append((title_lower, extinf, stream_url))
                i += 1
    except Exception as e:
        print(f"Error fetching {url}: {e}")

# Active check with concurrency
all_channels = []  # Final list of active (title_lower, extinf, url)
unique_names = set()

def check_and_add(ch):
    title_lower, extinf, url = ch
    if check_stream_active(url):
        return (title_lower, extinf, url)
    return None

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:  # Adjust to 10-20
    futures = [executor.submit(check_and_add, ch) for ch in potential_channels]
    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        if result:
            all_channels.append(result)
            unique_names.add(result[1].split(',')[-1].strip())  # Extract title with original casing

print(f"Checked {len(potential_channels)} streams; {len(all_channels)} active.")

# Dedup all_channels: Keep only unique title+URL pairs (exact match, so country variants stay)
seen = set()
deduped_channels = []
for title_lower, extinf, url in all_channels:
    key = (title_lower, url)
    if key not in seen:
        seen.add(key)
        deduped_channels.append((title_lower, extinf, url))

# Now sort based on order_list
ordered_channels = []
remaining_channels = deduped_channels[:]
for order_name in order_list:
    matches = []
    for ch in remaining_channels[:]:
        if order_name in ch[0]:  # Partial match in lowercased title
            matches.append(ch)
            remaining_channels.remove(ch)
    # Dedup within matches (though already deduped overall, but redundant safe)
    match_seen = set()
    unique_matches = []
    for ch in matches:
        key = (ch[0], ch[2])
        if key not in match_seen:
            match_seen.add(key)
            unique_matches.append(ch)
    ordered_channels.extend(unique_matches)

# Append remaining, sorted alphabetically by title_lower
remaining_channels.sort(key=lambda x: x[0])
ordered_channels.extend(remaining_channels)

# Build cleaned.m3u (original URLs, no pipe)
with open("cleaned.m3u", "w") as f:
    f.write(f'#EXTM3U url-tvg="{epg_url}"\n')
    for _, extinf, url in ordered_channels:
        f.write(f"{extinf}\n{url}\n")

# Build cleaned_pipe.m3u (with enhanced pipe wrappers)
with open("cleaned_pipe.m3u", "w") as f:
    f.write(f'#EXTM3U url-tvg="{epg_url}"\n')
    for _, extinf, url in ordered_channels:
        if use_pipe:
            wrapped_url = f'pipe://ffmpeg -analyzeduration 30000000 -i "{url}" -bsf:v h264_mp4toannexb -c copy -f mpegts pipe:1'
            f.write(f"{extinf}\n{wrapped_url}\n")
        else:
            f.write(f"{extinf}\n{url}\n")

# Build channels.txt (unique names, sorted alphabetically)
unique_names_list = sorted(list(unique_names))
with open("channels.txt", "w") as f:
    for name in unique_names_list:
        f.write(f"{name}\n")

print("Processed: cleaned.m3u, cleaned_pipe.m3u, and channels.txt generated.")
