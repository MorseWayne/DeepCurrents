import pino, { Logger, LoggerOptions } from 'pino';
import pinoPretty from 'pino-pretty';
import fs from 'fs';
import path from 'path';
import { CONFIG } from '../config/settings';

const baseOptions: LoggerOptions = {
  name: 'DeepCurrents',
  level: CONFIG.LOG_LEVEL,
  base: undefined,
  timestamp: pino.stdTimeFunctions.isoTime,
};

const streams: Array<{ stream: any }> = [];

if (CONFIG.LOG_TO_STDERR) {
  if (CONFIG.LOG_PRETTY) {
    streams.push({
      stream: pinoPretty({
        colorize: true,
        translateTime: 'SYS:standard',
        destination: 2,
      }),
    });
  } else {
    streams.push({ stream: pino.destination(2) });
  }
}

if (CONFIG.LOG_TO_FILE) {
  const resolvedPath = path.resolve(process.cwd(), CONFIG.LOG_FILE_PATH);
  fs.mkdirSync(path.dirname(resolvedPath), { recursive: true });
  streams.push({ stream: pino.destination(resolvedPath) });
}

if (streams.length === 0) {
  streams.push({ stream: pino.destination(2) });
}

const rootLogger: Logger = pino(baseOptions, pino.multistream(streams));

export function getLogger(component: string): Logger {
  return rootLogger.child({ component });
}

export { rootLogger };
