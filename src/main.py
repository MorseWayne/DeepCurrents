import asyncio
import signal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.config.settings import CONFIG
from src.engine import DeepCurrentsEngine
from src.utils.logger import get_logger

logger = get_logger("main")

async def main():
    engine = DeepCurrentsEngine()
    scheduler = AsyncIOScheduler()

    # 1. 启动引擎（执行首次采集/评分）
    await engine.start()

    # 2. 配置调度任务
    # 数据采集
    scheduler.add_job(engine.collect_data, 'cron', 
                      minute=CONFIG.cron_collect.split(' ')[0] if ' ' in CONFIG.cron_collect else 0)
    
    # 研报生成
    scheduler.add_job(engine.generate_and_send_report, 'cron', 
                      hour=CONFIG.cron_report.split(' ')[1] if ' ' in CONFIG.cron_report else 8,
                      minute=CONFIG.cron_report.split(' ')[0] if ' ' in CONFIG.cron_report else 0)
    
    # 自动评分 (每4小时一次)
    scheduler.add_job(engine.scorer.run_scoring_task, 'interval', hours=4)
    
    # 数据清理
    scheduler.add_job(engine.cleanup, 'cron',
                      hour=CONFIG.cron_cleanup.split(' ')[1] if ' ' in CONFIG.cron_cleanup else 3,
                      minute=CONFIG.cron_cleanup.split(' ')[0] if ' ' in CONFIG.cron_cleanup else 0)

    scheduler.start()
    logger.info("任务调度器已启动")

    # 3. 优雅退出
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def handle_exit():
        logger.info("收到退出信号...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_exit)

    try:
        await stop_event.wait()
    finally:
        scheduler.shutdown()
        await engine.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
