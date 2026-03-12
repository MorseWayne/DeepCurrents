import { spawnSync } from 'child_process';
import path from 'path';

export interface MarketPrice {
  symbol: string;
  price: number;
  changePercent: number;
  timestamp: string;
}

/**
 * 获取资产的实时行情
 * @param symbol 资产代码（如 GC=F 为黄金, CL=F 为原油, ^GSPC 为标普500）
 */
export async function getMarketPrice(symbol: string): Promise<MarketPrice> {
  const rootDir = path.join(__dirname, '..', '..');
  // 使用项目根目录下的虚拟环境 python
  const pythonPath = path.join(rootDir, 'venv', 'bin', 'python3');
  const scriptPath = path.join(__dirname, 'fetch_prices.py');
  
  const result = spawnSync(pythonPath, [scriptPath, symbol]);
  
  if (result.error) {
    throw new Error(`Failed to execute python script: ${result.error.message}`);
  }
  
  const output = result.stdout.toString().trim();
  if (!output) {
    const errorOutput = result.stderr.toString().trim();
    throw new Error(`Empty output from script. Stderr: ${errorOutput}`);
  }
  
  const data = JSON.parse(output);
  if (data.error) {
    throw new Error(data.error);
  }
  
  return data;
}
