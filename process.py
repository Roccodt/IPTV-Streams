import requests
import re
from urllib.parse import urlparse
from collections import defaultdict

# Keywords to filter out (case-insensitive)
filter_keywords = ["sport", "football", "soccer", "nba", "nfl", "espn", "tennis", "cricket", "boxing", "TSN", "golf", "news", "M4"]

# EPG URL
epg_url = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"

# Read links from links.txt
with open("links.txt", "r") as f:
    urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Read order from order.txt
with open("order.txt", "r") as f:
    order_list = [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]

# Dict to store channels: key=URL (for initial collection), but we'll handle dups by title+URL later
all_channels = []  # List of (title.lower(), extinf, url) for easier matching
unique_names = set()  # For channels.txt

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
                        # Extract title from #EXTINF (after comma)
                        title_match = re.search(r',(.*)$', extinf)
                        if title_match:
                            title = title_match.group(1).strip()
                            title_lower = title.lower()
                            # Skip if keyword in title
                            if any(kw in title_lower for kw in filter_keywords):
                                i += 2
                                continue
                            # Clean: Ensure valid URL
                            if urlparse(stream_url).scheme in ("http", "https"):
                                all_channels.append((title_lower, extinf, stream_url))
                                unique_names.add(title)  # Original casing for output
                i += 1
    except Exception as e:
        print(f"Error fetching {url}: {e}")

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

# Build cleaned.m3u
with open("cleaned.m3u", "w") as f:
    f.write(f'#EXTM3U url-tvg="{epg_url}"\n')
    for _, extinf, url in ordered_channels:
        f.write(f"{extinf}\n{url}\n")

# Build channels.txt (unique names, sorted alphabetically)
unique_names_list = sorted(list(unique_names))
with open("channels.txt", "w") as f:
    for name in unique_names_list:
        f.write(f"{name}\n")

print("Processed: cleaned.m3u and channels.txt generated.")
