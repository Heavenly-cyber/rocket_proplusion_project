# Preliminary presentation scope

PRELIMINARY EVALUATION. 95 actual model responses were saved from the planned 216-request schedule. The primary comparison uses all 18 case/seed pairs (36 responses) for which both conditions completed. The other 59 unpaired responses remain in all-observed.csv and the raw evidence ZIP. The run stopped for the presentation deadline. Pair inclusion did not depend on correctness. The full 216-response study remains unfinished. Rates refer to this observed paired subset only.

# Presenter notes

## Slide 1: Local LLM Reliability for Ideal Rocket Nozzles

Introduce the project as an evaluation of a pretrained local model. The course topic is ML-Based Rocket Nozzle Performance Prediction. This is an ideal-flow answer audit. Actual results in this deck come from run preliminary-20261106T034641. Scientific source commit d4affd1f11cf62e592aa4134212b00cde7da4f89. The experiment fingerprint is 0e53eb834115330c35ae1c0cda2d095cc55798bf5aea2d17ade387bf5992f779.

## Slide 2: Research question

The deterministic solver is an evaluator after generation. It does not supply a numerical answer to either answering condition. State the run profile: preliminary completed pairs. Completion: 36/36 responses.

## Slide 3: Why this topic fits rocket propulsion

NASA Glenn: https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-equations-summary/ and https://www.grc.nasa.gov/www/k-12/rocket/astar.html

## Slide 4: Motivation and significance

Use a concrete example: cm^2 requires a squared-length conversion, and chamber stagnation pressure cannot be substituted for exit static pressure. This project measures the tested setting and does not qualify real-engine designs.

## Slide 5: Related research

Primary records rechecked on 5 November 2026. The first three records are 2026 preprints. Their reported scores do not transfer to this project. https://arxiv.org/abs/2603.04452 https://arxiv.org/abs/2604.19758 https://arxiv.org/abs/2602.11666 https://arxiv.org/abs/2506.02019

## Slide 6: The bounded research gap

Ordinary RAG, physics checking and LLM applications to nozzles already have precedent. Avoid saying no previous work exists. The working gap can narrow if the baseline performs well.

## Slide 7: Governing physical relations

Define p0,T0 as chamber stagnation conditions, pe as exit static pressure, pa as ambient pressure, R as the specific gas constant. A complete area-Mach expression appears in the appendix. NASA Glenn: https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-equations-summary/ and https://www.grc.nasa.gov/www/k-12/rocket/astar.html

## Slide 8: Assumptions and validity limits

Supplied-state thrust questions use the stated exit quantities directly. Applicability questions ask whether the specifically requested ideal formula can be applied, rather than whether a richer model could ever solve the problem. NASA Glenn: https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-equations-summary/ and https://www.grc.nasa.gov/www/k-12/rocket/astar.html

## Slide 9: Worked ideal-nozzle example

All values on this slide are generated from the local reference job. They are theoretical ideal-flow results, separate from model inference and engine measurements. Show the saved worked-example.json. NASA Glenn: https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-equations-summary/ and https://www.grc.nasa.gov/www/k-12/rocket/astar.html

## Slide 10: Reference verification

A root cross-check shares the stated area relation and tests numerical solving. The analytic identity, energy relation and continuity add separate consistency constraints. They establish ideal implementation consistency, not real-engine fidelity. Tests are the current recorded laptop run, not a stale readiness count.

## Slide 11: Controlled answering experiment

The answering prompt never receives gold values, reference metadata or issue labels for its particular case. Both conditions see the same allowed issue-code vocabulary. Full payloads, raw responses and retrieved passage IDs persist. BM25S source: https://github.com/xhluca/bm25s

## Slide 12: Frozen benchmark

48 original template-generated cases contain 12 development and 36 evaluation cases. Full mode uses 36 x 2 x 3 = 216 responses. Seeds are 17, 43 and 89, preserving the committed CPU profile. The 12-response presentation profile is an optional pilot. Templates and repeated seeds are correlated. Human question review remains pending.

## Slide 13: Evaluation criteria

Strict seven-field JSON is part of the measured interface. Numerical cases require the issue none, compatible units and a finite number. Abstention cases require the correct decision and issue. Citation scores are separate from primary correctness. ID matching does not prove claim support. Unavailable requests make the run partial.

## Slide 14: Reproducible execution

The cache retains the model and images, while only this invocation's project containers and network are removed. A Git publication failure is separate from local scientific completion. The manifest records model, source and dependency identities.

## Slide 15: Measured overall reliability

Actual run preliminary-20261106T034641. Status preliminary. RAG minus baseline = +5.6 percentage points. Request wall time includes request processing and response generation, not model loading, test or rendering time. Repeated seeds are correlated. The complete HTML report retains all answers.

## Slide 16: Measured accuracy by question family

The native chart contains percentages calculated from the actual run, with all scheduled requests in each denominator. In a complete full run each family-condition cell has 18 responses. No confidence interval or significance claim is made because templates and repeated seeds are correlated.

## Slide 17: Paired outcomes and failure audit

Paired outcomes match the same case and seed. Error categories are mutually exclusive first-failure labels in the frozen evaluator. Do not infer that every numerical failure has the same cause. The raw response and separate unit fields support further review.

## Slide 18: One recorded paired example

Selection is deterministic: choose the first numerical evaluation case where the conditions differ or either fails, otherwise the first numerical case. It is an explanatory example, not an unbiased estimate. The excerpt shortens long responses. Full raw text and prompts are in the HTML report. Case exit_velocity-04, seed 17. Do not invent a failure if both conditions are correct.

## Slide 19: Expected and observed outcomes

The professor guidelines require expected results to be distinguished from demonstrated results. Quantitative expectations concern planned coverage, while accuracy is measured. A descriptive RAG benefit in this benchmark does not establish that retrieval causes broader engineering improvements.

## Slide 20: Potential impact and limitations

Human review of physical explanations and citation support is pending. Future tools or models are proposals, not measured remedies in this implementation. The project is useful for teaching and early research, not operational engine design.

## Slide 21: Demonstration and reproduction

The saved evidence package includes the actual responses and plots. Do not rerun a long inference experiment during the talk. The command all resumes a compatible full study. The presentation profile is a separately identified small pilot. No manual approval is needed between implementation steps.

## Slide 22: Appendix: full protocol

Presence penalty is 1.5. Thinking is disabled with the selected chat template. CPU threads are 6. Service memory cap 8 GiB, worker cap 2 GiB. These are limits, not measured peak use. The full protocol JSON records all settings and a source fingerprint. No incorrect observed answer is selectively retried.

## Slide 23: Appendix: area-Mach derivation

NASA Glenn: https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-equations-summary/ and https://www.grc.nasa.gov/www/k-12/rocket/astar.html Two branches exist when area ratio exceeds 1. The numerical benchmark explicitly requests a shock-free supersonic exit.

## Slide 24: References: related research

Full titles and clickable URLs are in the term paper. Primary source records rechecked 5 November 2026. Research metrics from these papers are not used as this project's results.

## Slide 25: References: physics and implementation

The nine required content points follow the supplied Rocket Propulsion final-presentation guidelines, preserved with the source material. Full source and measurement identities are in the final manifest.


Use the family table to state exact denominators. N/A means no completed pair. Do not describe these responses as independent questions or as a completed 216-response study.
