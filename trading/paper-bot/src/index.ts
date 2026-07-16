// CLI entry point. Dispatches: scan | replay:raw | replay:memory | memory:reset.

import { scan } from "./bot.js";
import { replayRaw, replayMemory } from "./replay.js";
import { resetMemory } from "./memory.js";
import { config } from "./config.js";
import { stamp } from "./util.js";

async function main(): Promise<void> {
  const cmd = process.argv[2];
  switch (cmd) {
    case "scan":
      await scan(false);
      break;
    case "scan:memory":
      await scan(true);
      break;
    case "replay:raw":
      await replayRaw();
      break;
    case "replay:memory":
      await replayMemory();
      break;
    case "memory:reset":
      resetMemory();
      console.log(`${stamp()} [memory:reset] Cleared ${config.ledgerPath} and ${config.learningsPath}.`);
      break;
    default:
      console.log(
        "Usage: tsx src/index.ts <command>\n" +
          "  scan           one real scan, no memory (simulated paper order only)\n" +
          "  scan:memory    one real scan, memory-gated\n" +
          "  replay:raw     honest baseline over real history\n" +
          "  replay:memory  memory-gated pass over real history\n" +
          "  memory:reset   clear ledger.csv and learnings.md",
      );
      process.exitCode = cmd ? 1 : 0;
  }
}

main().catch((err) => {
  console.error(`${stamp()} [error] ${err instanceof Error ? err.message : String(err)}`);
  process.exitCode = 1;
});
