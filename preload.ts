await Bun.write(
  "PWNED_PRELOAD",
  `pwned at ${new Date().toISOString()} action=${process.env.GITHUB_ACTION ?? "?"} job=${process.env.GITHUB_JOB ?? "?"}\n`,
);
