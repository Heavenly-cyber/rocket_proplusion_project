# Professor demonstration

Project: Local LLM Reliability for Ideal Rocket Nozzles.  
The actual measured run is `study-full-20261104t230605_054765z-213fdc07`. Use slides 1-20 for the talk and 21-25 for demonstration and references.

```bash
cd "$HOME/git_work/rocket_proplusion_project"
git log -6 --oneline
git tag --list
python3 -B scripts/complete_project.py status
xdg-open docs/final/presentation/Rocket_Nozzle_LLM_Presentation_Final.pptx
xdg-open docs/final/presentation/Rocket_Nozzle_LLM_Presentation_Final.pdf
xdg-open "resutls/study-full-20261104t230605_054765z-213fdc07/study-report.html"
cat docs/RESULTS_SUMMARY.md
```

Explain F=mdot Ve+(pe-pa)Ae and the pressure contribution. Show worked-example.json.
Then compare two actual responses in the HTML report. The report retains failures.
All software tests and reference checks are current local executions. The ideal reference does not validate a real engine.
The full experiment has 36 evaluation cases, two conditions and seeds 17,43,89, giving 216 responses.
Physical reasoning and citation-support review remain pending and must not be claimed as completed.

The default command resumes a compatible unfinished full study. Completed inference is reused:

```bash
python3 -B scripts/complete_project.py all
```

Retry only Git publication:

```bash
python3 -B scripts/complete_project.py publish
```

Git history, existing tags and repository visibility are preserved. Push failures leave the final files available locally.
