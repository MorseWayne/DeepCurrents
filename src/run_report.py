import asyncio
import argparse
import sys
import json
import os
from src.engine import DeepCurrentsEngine
from src.utils.logger import get_logger

logger = get_logger("run-report")


async def run_report(args):
    engine = DeepCurrentsEngine()
    await engine.bootstrap_runtime()

    try:
        # 1. 采集数据（除非指定 --report-only）
        if not args.report_only:
            await engine.collect_data()

        # 2. 生成研报
        # 注意：如果指定了 --no-push，则不推送；如果指定了 --no-push，通常也建议 --no-mark
        report = await engine.generate_and_send_report(
            skip_push=args.no_push,
            skip_mark=args.no_push,  # 预览模式通常不标记已读
            force=args.force,
        )

        if not report:
            print("\n--- 未能生成研报（可能无新数据） ---")
            return

        # 3. 输出处理
        report_dict = report.model_dump()

        if args.json:
            output_text = json.dumps(report_dict, indent=2, ensure_ascii=False)
        else:
            # 格式化 Markdown 输出
            lines = [
                f"# 🌊 DeepCurrents Daily Report ({report.date})",
                f"\n## 核心主线\n{report.executiveSummary}",
                f"\n## 宏观研判\n{report.economicAnalysis}",
                "\n## 资产风向",
            ]
            for t in report.investmentTrends:
                lines.append(f"- **{t.assetClass}**: {t.trend} | {t.rationale}")
            output_text = "\n".join(lines)

        # 写入文件或打印
        if args.output:
            os.makedirs(
                os.path.dirname(args.output) if os.path.dirname(args.output) else ".",
                exist_ok=True,
            )
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_text)
            print(f"\n✅ 研报已写入: {args.output}")
        else:
            print("\n" + "=" * 50)
            print(output_text)
            print("=" * 50)

    except Exception as e:
        logger.error(f"手动生成研报失败: {e}")
    finally:
        await engine.stop()


def main():
    parser = argparse.ArgumentParser(description="DeepCurrents 研报命令行工具 (v2.2)")
    parser.add_argument(
        "--report-only", action="store_true", help="仅用已有数据生成（跳过采集）"
    )
    parser.add_argument(
        "--no-push", action="store_true", help="预览模式：不推送通知，不标记已报告"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制生成：忽略最近一次报告时间窗口（仍仅使用现有数据）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--output", "-o", type=str, help="将研报保存到指定文件")

    args = parser.parse_args()
    asyncio.run(run_report(args))


if __name__ == "__main__":
    main()
