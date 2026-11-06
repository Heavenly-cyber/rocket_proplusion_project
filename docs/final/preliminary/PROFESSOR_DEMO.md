# Preliminary presentation demonstration

The full 216-response study remains unfinished. This package uses actual saved
responses and includes every available complete baseline/RAG case-and-seed pair.
No additional model inference was performed to create the presentation.

1. Open the preliminary PPTX or PDF in this folder.
2. Explain nozzle thrust and the independent worked-example.json.
3. Show the saved-response count and the number of matched pairs separately.
4. Open evidence/study-report.html to inspect actual paired responses and failures.
5. State template correlation, time-cutoff selection and pending human review.

The source run stays resumable. To finish the original 216-response study later:

```bash
cd "$HOME/git_work/rocket_proplusion_project"
python3 -B scripts/complete_project.py all
```

Use `python3 -B scripts/complete_project.py publish` to retry pending publication.
