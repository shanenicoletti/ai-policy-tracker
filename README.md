# AI Policy Tracker

An AI agent that scans Canadian, US and EU government sources every week, finds new AI policy developments, and emails a short digest explaining what happened and why it matters. Developments that affect financial services are flagged.

**Subscribe:** _(signup link coming soon)_

## Why I built it

Keeping up with AI regulation means checking bill trackers, regulatory gazettes and regulator websites in Canada, the US and the EU, every week. It's slow and easy to miss things. This agent does the checking for you and sends only what matters.

## How it works

Using Simon Willison's definition, "an LLM agent runs tools in a loop to achieve a goal":

| | |
|---|---|
| **Goal** | Find every important AI policy development in Canada, the US and the EU from the past week, and explain why each one matters. |
| **Tools** | US Federal Register API, Congress.gov API, Canada's LEGISinfo, Canada Gazette, official EU websites (Commission, AI Office, EUR-Lex, Parliament, EU financial regulators), Google search (for regulators like OSFI, FTC and CFPB), a web page reader, plus `save_finding` and `finish`. |
| **Loop** | Each turn, Gemini sees what it has done so far (sources checked, findings saved, steps left) and picks its next action. It keeps going until it calls `finish`. |
| **Evaluate** | Tested against a list of real AI policy developments from past weeks (see Evaluation below). |

### Guardrails

- **No made-up sources.** The agent can only save a finding if its link appeared in a real tool result.
- **No repeats.** It remembers what it reported in past weeks (`data/reported.json`).
- **No shortcuts.** It can't finish until it has checked every core source.
- **No runaway costs.** Hard limit of 50 steps per run.
- **Web pages are data, not instructions.** The agent is told to ignore any instructions found on pages it reads.
- **Subscriber privacy.** Emails go out as BCC, and the subscriber list is never stored in this repo.

## Files

```
main.py                     Runs everything
tracker/agent.py            The agent loop and guardrails
tracker/sources.py          The tools (data sources)
tracker/memory.py           Remembers past findings
tracker/digest.py           Builds and sends the email
.github/workflows/weekly.yml  Runs it every Monday at 8am ET
digests/                    Archive of every weekly digest
logs/                       Step-by-step record of each run
```

## Evaluation

_(coming soon)_

## Run your own copy

1. Fork this repo.
2. In **Settings → Secrets and variables → Actions**, add:
   - `GEMINI_API_KEY` (free at aistudio.google.com)
   - `CONGRESS_API_KEY` (free at api.congress.gov/sign-up)
   - `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` (a Gmail app password)
   - `OWNER_EMAIL` (where you want the digest sent)
   - `SUBSCRIBERS_CSV_URL` (optional: a Google Form responses sheet published as CSV)
3. Go to **Actions → Weekly AI Policy Digest → Run workflow** to test it.

Built by Shane for an AI course at the Harvard Kennedy School. The digest is written by AI and can make mistakes, so always check the original source.
