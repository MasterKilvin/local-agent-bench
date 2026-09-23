/**
 * Bench step limit for pi (pi has no built-in turn cap).
 * Aborts the agent run when turn number PI_BENCH_MAX_TURNS would start. One turn = one model response + its tool calls.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	const max = Number(process.env.PI_BENCH_MAX_TURNS || "30");
	let turns = 0;
	pi.on("turn_start", async (_event, ctx) => {
		turns += 1;
		if (turns > max) {
			console.error(`[bench] step limit ${max} reached, aborting`);
			ctx.abort();
		}
	});
}
