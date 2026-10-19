await Bun.write("PWNED_PRELOAD", `pwned at ${new Date().toISOString()} by preload.ts\nGITHUB_ACTION=${process.env.GITHUB_ACTION ?? "?"}\n`);
