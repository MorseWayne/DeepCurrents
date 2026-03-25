import asyncio
import argparse
import json
import os
from src.engine import DeepCurrentsEngine
from src.utils.logger import get_logger

logger = get_logger("run-report")


async def run_events(args):
    engine = DeepCurrentsEngine()
    await engine.bootstrap_runtime()

    try:
        if not args.report_only:
            await engine.collect_data()

        event_briefs = await engine.send_core_events(
            skip_push=args.no_push,
            force=args.force,
            translate=not args.no_translate,
        )

        if not event_briefs:
            print("\n--- 未检测到核心事件 ---")
            return

        if args.json:
            output_text = json.dumps(
                [_brief_to_dict(b) for b in event_briefs],
                indent=2,
                ensure_ascii=False,
            )
        else:
            lines = [f"# 🔥 核心事件速报 (共 {len(event_briefs)} 个)\n"]
            for i, brief in enumerate(event_briefs):
                bj = brief.get("brief_json", brief) if isinstance(brief, dict) else {}
                title = bj.get("canonicalTitle", "")
                state = bj.get("stateChange", "")
                score = bj.get("totalScore", 0)
                why = bj.get("whyItMatters", "")
                lines.append(f"{i+1}. [{state}] {title} (score={score:.3f})")
                if why:
                    lines.append(f"   {why}")
                lines.append("")
            output_text = "\n".join(lines)

        if args.output:
            os.makedirs(
                os.path.dirname(args.output) if os.path.dirname(args.output) else ".",
                exist_ok=True,
            )
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_text)
            print(f"\n✅ 事件速报已写入: {args.output}")
        else:
            print("\n" + "=" * 50)
            print(output_text)
            print("=" * 50)

    except Exception as e:
        logger.error(f"事件速报生成失败: {e}")
    finally:
        await engine.stop()


async def run_report(args):
    engine = DeepCurrentsEngine()
    await engine.bootstrap_runtime()

    try:
        if not args.report_only:
            await engine.collect_data()

        report = await engine.generate_and_send_report(
            skip_push=args.no_push,
            skip_mark=args.no_push,
            force=args.force,
        )

        if not report:
            print("\n--- 未能生成研报（可能无新数据） ---")
            return

        report_dict = report.model_dump()

        if args.json:
            output_text = json.dumps(report_dict, indent=2, ensure_ascii=False)
        else:
            lines = [
                f"# 🌊 DeepCurrents Daily Report ({report.date})",
                f"\n## 核心主线\n{report.executiveSummary}",
            ]
            if report.macroTransmissionChain:
                chain = report.macroTransmissionChain
                lines.append("\n## 总主线传导链")
                lines.append(f"- 主线: {chain.headline}")
                if chain.shockSource:
                    lines.append(f"- 冲击源: {chain.shockSource}")
                if chain.macroVariables:
                    lines.append(f"- 宏观变量: {'、'.join(chain.macroVariables[:4])}")
                if chain.marketPricing:
                    lines.append(f"- 市场定价: {chain.marketPricing}")
                if chain.allocationImplication:
                    lines.append(f"- 配置含义: {chain.allocationImplication}")
                for idx, step in enumerate(chain.steps[:4], start=1):
                    lines.append(f"  {idx}. {step.stage}: {step.driver}")
            lines.append(f"\n## 宏观研判\n{report.economicAnalysis}")
            if report.assetTransmissionBreakdowns:
                lines.append("\n## 关键资产拆解")
                for item in report.assetTransmissionBreakdowns[:4]:
                    lines.append(
                        f"- **{item.assetClass}**: {item.trend} | {item.coreView}"
                    )
                    lines.append(f"  传导路径: {item.transmissionPath}")
            lines.append("\n## 资产风向")
            for t in report.investmentTrends:
                lines.append(f"- **{t.assetClass}**: {t.trend} | {t.rationale}")
            output_text = "\n".join(lines)

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

        if args.format in ("docx", "pdf"):
            from src.services.report_exporter import ReportExporter
            exporter = ReportExporter()
            # Determine base path: strip extension from --output if provided, else use date
            base = args.output.rsplit(".", 1)[0] if args.output else f"data/reports/{report.date}"
            if args.format == "docx":
                path = exporter.export_word(output_text, f"{base}.docx")
                print(f"Word report saved: {path}")
            elif args.format == "pdf":
                path = exporter.export_pdf(output_text, f"{base}.pdf")
                if path:
                    print(f"PDF report saved: {path}")
                else:
                    print("PDF export failed (wkhtmltopdf not installed?)")

    except Exception as e:
        logger.error(f"手动生成研报失败: {e}")
    finally:
        await engine.stop()


def _brief_to_dict(brief):
    if isinstance(brief, dict):
        bj = brief.get("brief_json", brief)
        return dict(bj) if isinstance(bj, dict) else brief
    return {}


def main():
    parser = argparse.ArgumentParser(description="DeepCurrents 研报命令行工具 (v2.2)")
    parser.add_argument(
        "--events-only",
        action="store_true",
        help="仅推送核心事件速报（不生成研报）",
    )
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
    parser.add_argument(
        "--no-translate",
        action="store_true",
        help="事件速报不翻译（保留英文原文）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--output", "-o", type=str, help="将输出保存到指定文件")
    parser.add_argument(
        "--format",
        choices=["md", "docx", "pdf"],
        default="md",
        help="Output format: md (default), docx, or pdf",
    )

    args = parser.parse_args()
    if args.events_only:
        asyncio.run(run_events(args))
    else:
        asyncio.run(run_report(args))


if __name__ == "__main__":
    main()
