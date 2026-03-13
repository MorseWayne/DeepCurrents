import asyncio
import signal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from src.config.settings import CONFIG
from src.engine import DeepCurrentsEngine
from src.utils.logger import get_logger

logger = get_logger("main")


def build_cron_trigger(expr: str, env_name: str) -> CronTrigger:
    try:
        return CronTrigger.from_crontab(expr)
    except ValueError as e:
        raise ValueError(f"{env_name} 配置非法: {expr}") from e

async def main():
    engine = DeepCurrentsEngine()
    scheduler = AsyncIOScheduler()

    # 1. 启动引擎（执行首次采集/评分）
    await engine.start()

    # 2. 配置调度任务
    # 数据采集
    scheduler.add_job(
        engine.collect_data,
        trigger=build_cron_trigger(CONFIG.cron_collect, "CRON_COLLECT"),
        id="collect_data",
        replace_existing=True
    )
    
    # 核心事件速报（独立于研报，可选启用）
    if CONFIG.cron_events:
        scheduler.add_job(
            engine.send_core_events,
            trigger=build_cron_trigger(CONFIG.cron_events, "CRON_EVENTS"),
            id="send_core_events",
            replace_existing=True,
        )
        logger.info(f"事件速报调度已启用: {CONFIG.cron_events}")

    # 研报生成
    scheduler.add_job(
        engine.generate_and_send_report,
        trigger=build_cron_trigger(CONFIG.cron_report, "CRON_REPORT"),
        id="generate_report",
        replace_existing=True
    )
    
    # 自动评分 (每4小时一次)
    scheduler.add_job(engine.scorer.run_scoring_task, 'interval', hours=4, id="score_predictions", replace_existing=True)
    
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
