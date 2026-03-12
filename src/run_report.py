import asyncio
import argparse
import sys
from src.engine import DeepCurrentsEngine
from src.utils.logger import get_logger

async def run_report(args):
    engine = DeepCurrentsEngine()
    await engine.db.connect()
    
    try:
        if not args.report_only:
            await engine.collect_data()
        
        result = await engine.generate_and_send_report()
        if result:
            print(f"\n--- 研报生成成功 ({result.date}) ---")
            if args.json:
                import json
                print(json.dumps(result.dict(), indent=2, ensure_ascii=False))
            else:
                print(f"摘要: {result.executiveSummary}")
        else:
            print("\n--- 未能生成研报（可能无新数据） ---")
            
    finally:
        await engine.stop()

def main():
    parser = argparse.ArgumentParser(description="DeepCurrents 手动研报工具")
    parser.add_argument("--report-only", action="store_true", help="跳过采集，仅用已有数据生成")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出到终端")
    
    args = parser.parse_args()
    asyncio.run(run_report(args))

if __name__ == "__main__":
    main()
