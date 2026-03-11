"""
Crypto News Discord Bot
========================
Posts top crypto news + @GarethSoloway tweets to Discord every 8 hours.
"""

import requests
import schedule
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# ============================================================
# CONFIGURATION
# ============================================================

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1480747139054305381/LYgF02cuMhLXwP_WqUcIZ8ksul0tfvSxAKuo8VXPYTxSv1UiOT6mQXq-tTpPtDY_FFEK"

TWITTER_USERNAME   = "GarethSoloway"

# CryptoCompare news API (free, no key needed)
NEWS_URL = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&sortOrder=popular&extraParams=crypto_bot"

# Nitter RSS instances (will try each in order until one works)
NITTER_RSS_INSTANCES = [
    "https://nitter.privacydev.net/{user}/rss",
    "https://nitter.poast.org/{user}/rss",
    "https://nitter.1d4.us/{user}/rss",
    "https://nitter.kavin.rocks/{user}/rss",
    "https://nitter.unixfox.eu/{user}/rss",
]

POSTED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posted_news.json")

# Colors for Discord embeds
COLOR_NEWS  = 0xF7931A   # Bitcoin orange
COLOR_TWEET = 0x1DA1F2   # Twitter blue
COLOR_ERROR = 0xFF4444   # Red (for error messages)

# How many news items to post per run
NEWS_LIMIT = 10

# ============================================================
# HELPERS — Duplicate Tracking
# ============================================================

def load_posted():
    if os.path.exists(POSTED_FILE):
        try:
            with open(POSTED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("news_ids", [])), set(data.get("tweet_ids", []))
        except Exception:
            pass
    return set(), set()


def save_posted(news_ids: set, tweet_ids: set):
    # Keep last 1000 IDs max to prevent file bloat
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "news_ids":  list(news_ids)[-1000:],
            "tweet_ids": list(tweet_ids)[-1000:],
        }, f, ensure_ascii=False)


# ============================================================
# HELPERS — Discord
# ============================================================

def post_to_discord(embed: dict, username: str = "Crypto Bot", avatar_url: str = "") -> bool:
    payload = {"username": username, "embeds": [embed]}
    if avatar_url:
        payload["avatar_url"] = avatar_url

    for attempt in range(3):
        try:
            r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
            if r.status_code == 204:
                return True
            elif r.status_code == 429:
                wait = r.json().get("retry_after", 5)
                print(f"    ⏳ Discord rate limit, waiting {wait}s...")
                time.sleep(float(wait))
                continue
            else:
                print(f"    ❌ Discord error {r.status_code}: {r.text[:200]}")
                return False
        except requests.RequestException as e:
            print(f"    ❌ Discord post failed (attempt {attempt+1}): {e}")
            time.sleep(3)
    return False


def post_header_to_discord(title: str, desc: str, color: int):
    """Post a section header embed (divider message)."""
    embed = {
        "title": title,
        "description": desc,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    post_to_discord(embed, username="📡 Crypto Bot")


# ============================================================
# MODULE 1 — Crypto News (CryptoCompare)
# ============================================================

def fetch_crypto_news():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📰 Fetching crypto news...")

    news_ids, tweet_ids = load_posted()

    try:
        r = requests.get(NEWS_URL, timeout=20)
        r.raise_for_status()
        data = r.json()
        articles = data.get("Data", [])
        if not isinstance(articles, list):
            print("    ⚠️  Unexpected API response format.")
            return
    except requests.RequestException as e:
        print(f"    ❌ Failed to fetch news: {e}")
        return

    if not articles:
        print("    ⚠️  No articles returned from API.")
        return

    # Filter out already-posted
    new_articles = []
    for article in articles:
        aid = str(article.get("id", ""))
        if aid and aid not in news_ids:
            new_articles.append(article)

    if not new_articles:
        print("    ℹ️  All articles already posted. Skipping.")
        return

    # Take up to NEWS_LIMIT, post oldest first
    to_post = new_articles[:NEWS_LIMIT]
    to_post.reverse()

    # Send a section header
    post_header_to_discord(
        title="📰 Crypto News Update",
        desc=f"Here are the top **{len(to_post)}** crypto news articles right now 🚀",
        color=COLOR_NEWS,
    )
    time.sleep(1)

    posted_count = 0
    for article in to_post:
        aid   = str(article.get("id", ""))
        title = article.get("title", "No Title")
        body  = article.get("body", "")
        url   = article.get("url", "")
        src   = (article.get("source_info") or {}).get("name") or article.get("source", "Unknown")
        img   = article.get("imageurl", "")
        pub   = article.get("published_on", 0)

        # Truncate body
        body = (body[:300] + "...") if len(body) > 300 else body

        embed = {
            "title":       f"📰 {title}",
            "url":         url,
            "description": body,
            "color":       COLOR_NEWS,
            "fields":      [{"name": "📌 Source", "value": src, "inline": True}],
            "footer":      {"text": "CryptoCompare • Crypto News"},
        }
        if img:
            embed["thumbnail"] = {"url": img}
        if pub:
            embed["timestamp"] = datetime.fromtimestamp(pub, tz=timezone.utc).isoformat()

        if post_to_discord(embed, username="📰 Crypto News"):
            news_ids.add(aid)
            posted_count += 1
            print(f"    ✅ [{posted_count}/{len(to_post)}] {title[:70]}")
            time.sleep(2)  # Avoid Discord rate limit

    save_posted(news_ids, tweet_ids)
    print(f"    → Done: {posted_count} new article(s) posted.")


# ============================================================
# MODULE 2 — @GarethSoloway Tweets via Nitter RSS
# ============================================================

def parse_nitter_rss(xml_text: str) -> list:
    """Parse Nitter RSS XML and return list of tweet dicts."""
    tweets = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        channel = root.find("channel")
        if channel is None:
            return tweets

        # Channel-level info (profile image, display name)
        channel_title = channel.findtext("title", default=TWITTER_USERNAME)
        display_name  = channel_title.replace(" / Nitter", "").strip()

        for item in channel.findall("item"):
            title      = item.findtext("title", default="")
            link       = item.findtext("link",  default="")
            pub_date   = item.findtext("pubDate", default="")
            content    = item.findtext("content:encoded", default="", namespaces=ns)

            # Extract tweet text: strip HTML tags from title/content
            text = re.sub(r"<[^>]+>", "", title).strip()
            if not text:
                text = re.sub(r"<[^>]+>", "", content).strip()

            # Extract image URLs from content HTML
            images = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content)
            # Filter out profile images (usually small)
            images = [i for i in images if "profile_images" not in i and "avatar" not in i]

            # Tweet ID from link
            tid = link.split("/")[-1].split("#")[0] if link else ""

            # Skip retweets
            if title.lower().startswith("rt @"):
                continue

            if tid:
                tweets.append({
                    "id":           tid,
                    "text":         text,
                    "link":         link,
                    "pub_date":     pub_date,
                    "display_name": display_name,
                    "image":        images[0] if images else "",
                })
    except ET.ParseError as e:
        print(f"    ⚠️  RSS parse error: {e}")
    return tweets


def fetch_nitter_rss() -> list:
    """Try each Nitter instance and return tweets from the first working one."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/rss+xml, application/xml, text/xml, */*",
    }
    for url_template in NITTER_RSS_INSTANCES:
        url = url_template.format(user=TWITTER_USERNAME)
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200 and "<rss" in r.text:
                tweets = parse_nitter_rss(r.text)
                if tweets:
                    print(f"    ✅ Got {len(tweets)} tweets from: {url.split('/')[2]}")
                    return tweets
                else:
                    print(f"    ⚠️  {url.split('/')[2]} returned empty RSS")
            else:
                print(f"    ⚠️  {url.split('/')[2]} → HTTP {r.status_code}")
        except requests.RequestException as e:
            print(f"    ⚠️  {url.split('/')[2]} → {e}")
        time.sleep(1)
    return []


def fetch_gareth_tweets():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 𝕏 Fetching @{TWITTER_USERNAME} tweets...")

    news_ids, tweet_ids = load_posted()

    tweets = fetch_nitter_rss()

    if not tweets:
        print("    ❌ Could not fetch tweets from any Nitter instance.")
        return

    # Exclude already-posted
    new_tweets = [t for t in tweets if t["id"] not in tweet_ids]

    if not new_tweets:
        print("    ℹ️  All tweets already posted. Skipping.")
        return

    # Post oldest first, max 5 per run (avoid spam)
    to_post = list(reversed(new_tweets[:5]))

    # Send a section header
    post_header_to_discord(
        title=f"𝕏 Latest from @{TWITTER_USERNAME}",
        desc=f"New tweets from **Gareth Soloway** 🐦",
        color=COLOR_TWEET,
    )
    time.sleep(1)

    posted_count = 0
    for tweet in to_post:
        tid  = tweet["id"]
        text = tweet["text"]
        link = tweet["link"]
        name = tweet["display_name"]
        img  = tweet["image"]

        if len(text) > 500:
            text = text[:497] + "..."

        embed = {
            "author": {
                "name":    f"{name} (@{TWITTER_USERNAME})",
                "url":     f"https://x.com/{TWITTER_USERNAME}",
                "icon_url": f"https://unavatar.io/twitter/{TWITTER_USERNAME}",
            },
            "description": text,
            "url":   link,
            "color": COLOR_TWEET,
            "footer": {"text": f"𝕏 Twitter • @{TWITTER_USERNAME}"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if img:
            embed["image"] = {"url": img}

        if post_to_discord(embed, username=f"𝕏 {name}"):
            tweet_ids.add(tid)
            posted_count += 1
            clean = text.replace("\n", " ")
            print(f"    ✅ [{posted_count}] {clean[:70]}")
            time.sleep(2)

    save_posted(news_ids, tweet_ids)
    print(f"    → Done: {posted_count} new tweet(s) posted.")


# ============================================================
# DAILY RUN — runs news + tweets together
# ============================================================

def daily_run():
    now = datetime.now().strftime("%A %d %b %Y %H:%M")
    print(f"\n{'='*55}")
    print(f"  🔔 Daily Run @ {now}")
    print(f"{'='*55}")
    fetch_crypto_news()
    time.sleep(5)
    fetch_gareth_tweets()
    print(f"\n{'='*55}\n  ✅ Run complete. Next run scheduled.\n{'='*55}\n")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 55)
    print("   🚀 Crypto News Bot — Starting!")
    print("=" * 55)
    print(f"   📰 News limit:  {NEWS_LIMIT} articles per run")
    print(f"   🕐 Schedule:   Every 8 hours")
    print(f"   𝕏  Twitter:    @{TWITTER_USERNAME}")
    print(f"   🔗 Webhook:    ...{DISCORD_WEBHOOK_URL[-20:]}")
    print("=" * 55)

    # Run once immediately on startup
    print("\n⚡ Running initial fetch now...\n")
    daily_run()

    # Schedule every 8 hours
    schedule.every(8).hours.do(daily_run)

    print("✅ Bot is running! Scheduled every 8 hours.")
    print("   Press Ctrl+C to stop.\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped (KeyboardInterrupt).")
    except Exception as e:
        print(f"\n🛑 Bot encountered an error: {e}")


if __name__ == "__main__":
    main()
