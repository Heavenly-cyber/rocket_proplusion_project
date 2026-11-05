# Resume after CPU inference timeouts

The saved checkpoint `0ffa140` contains 35 of 216 scheduled responses. The next
request, `mixed_units-05__17__rag`, hit the 300-second HTTP read timeout on both
allowed attempts. Other successful responses took about 288-290 seconds.
The timeout was too close to the observed CPU generation time.

The correction extends only the worker's HTTP read timeout to 1800 seconds.
It leaves the 768-token generation cap, prompts, model, seeds, frozen question
set, retrieval method, references and scoring unchanged. The original scientific
source files and their experiment fingerprint remain unchanged. The host now
calls a separately recorded transport adapter before the frozen worker.

Previously received responses remain immutable. Missing requests are resumed.
No answer is regenerated to improve its score, and no final success is claimed
until the full schedule completes. Transport failures already recorded remain
part of the evidence. The execution boundary is documented in
`execution-overrides.json` and the run manifest, reports and final hand-in.

The repair commits and attempts to push its explicit changed files, then invokes
the full workflow with the existing active run. It preserves existing tags,
model/image caches, Git remotes and all raw measurements. It updates only the
installer's source-integrity record for the deliberately repaired host/doc files.

Run the downloaded `resume_rocket_project.sh` as your normal user. Later resumes
can use `python3 -B scripts/complete_project.py all` from the repository. Keep
using this corrected checkout rather than reinstalling the earlier launcher.
