import asyncio
import aiohttp
import time
from typing import List

async def fetch_source(session: aiohttp.ClientSession, url: str, semaphore: asyncio.Semaphore):
    async with semaphore:
        try:
            start_time = time.time()
            async with session.get(url, timeout=10) as response:
                status = response.status
                text = await response.text()
                end_time = time.time()
                print(f"Fetched {url} | Status: {status} | Size: {len(text)} bytes | Time: {end_time - start_time:.2f}s")
                return True
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return False

async def main():
    # 模拟项目中的部分 RSS 源
    urls = [
        "https://www.reutersagency.com/feed/",
        "https://www.bloomberg.com/politics/feeds/site.xml",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://cn.reuters.com/rssfeed/chinaNews",
        "https://www.ft.com/?format=rss",
    ] * 4  # 复制 4 次模拟 20 个请求
    
    # 并发控制，模拟 p-limit(5)
    sem = asyncio.Semaphore(5)
    
    print(f"Starting crawl of {len(urls)} URLs with concurrency limit 5...")
    start_total = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_source(session, url, sem) for url in urls]
        results = await asyncio.gather(*tasks)
    
    end_total = time.time()
    success_count = sum(1 for r in results if r)
    print(f"\nFinished! Success: {success_count}/{len(urls)}")
    print(f"Total time: {end_total - start_total:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
