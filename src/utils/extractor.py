import aiohttp
from bs4 import BeautifulSoup
from typing import Optional, Dict
from ..utils.logger import get_logger

logger = get_logger("extractor")

class Extractor:
    @staticmethod
    async def extract(
        url: str,
        max_length: int = 5000,
        session: Optional[aiohttp.ClientSession] = None
    ) -> Optional[Dict[str, str]]:
        """提取网页正文"""
        try:
            managed_session = session is None
            active_session = session or aiohttp.ClientSession()
            async with active_session.get(url, timeout=15) as response:
                if response.status != 200:
                    return None
                html = await response.text()
            
            parser = 'xml' if html.lstrip().startswith('<?xml') else 'lxml'
            soup = BeautifulSoup(html, parser)
            
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()

            # 简单的内容提取逻辑（寻找最长文本块）
            # 在生产环境中，建议使用 trafilatura 或 goose3
            paragraphs = soup.find_all('p')
            content = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
            
            if len(content) < 100:
                # 如果段落提取失败，尝试获取 body 文本
                content = soup.get_text()

            # 清理文本
            lines = (line.strip() for line in content.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return {
                "title": soup.title.string if soup.title else "",
                "content": text[:max_length]
            }
        except Exception as e:
            logger.debug(f"Failed to extract {url}: {e}")
            return None
        finally:
            if 'managed_session' in locals() and managed_session:
                await active_session.close()
