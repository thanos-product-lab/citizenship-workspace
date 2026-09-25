# Citizenship Workspace

A plain-language guide to what this product is, who it is for, and how it works. No
technical knowledge needed.

## In one sentence

A private workspace that helps someone who already has settled status in the UK get their
British citizenship application in order, showing the reasoning behind every check so they
never have to take its word for anything.

## Who it is for

Adults living in the UK who:

- already hold indefinite leave to remain, indefinite leave to enter, or EU settled status;
- are thinking of applying for British citizenship on the standard five-year route;
- have their history spread across emails, bookings, letters and certificates;
- want to know what supports their application, what is missing, and what needs a closer
  look, before they fill in the official form.

It is **not** for spouses of British citizens, children, people without settled status yet,
or anyone who needs legal advice. It says so at the start, rather than guessing.

## The problem it solves

Applying for citizenship means rebuilding five years of your own life: every trip abroad,
the exact date your status was granted, test results, and more. The information exists, but
it is scattered, and the rules turn on small details. One example: you must have been in the
UK on a particular day five years before you apply, and getting that day wrong by one is an
easy mistake.

Checklists and calculators each handle one piece. General AI chat tools can explain the
rules, but they cannot keep a reliable record of your case, and they can sound confident
when they are wrong.

## What it does, step by step

1. **A few questions.** Your age, your status and when it was granted. If your situation is
   outside what the workspace covers, it tells you so straight away.
2. **Your application date.** The date you plan to apply. Everything is measured back from
   it, and you can preview a different date to see what would change before you save it.
3. **Your trips abroad.** Type them in, or import them from a spreadsheet. For each trip you
   say how sure you are about the dates, and why you travelled.
4. **Your documents.** Upload a booking or a certificate. The workspace reads it and suggests
   the values it found, such as travel dates, but **none of them counts until you check it
   against the document yourself**. For the values that matter most, you type what the
   document says rather than accepting a suggestion.
5. **Your results.** Each requirement is checked with fixed calculations (for example, your
   total days outside the UK against the 450-day threshold) and gets a result you can open
   to see exactly how it was worked out.
6. **What to do next.** The overview shows your next steps, and the Issues page lists
   anything that needs your attention, grouped by what you have to do.
7. **Your travel list.** A clean list of your trips from the last five years, ready to print,
   save as a PDF or download as a spreadsheet, for when the official form has more trips
   than it has room for.

## What the results mean

Every requirement shows one of these results, in words and with a symbol, never by colour
alone:

| Result | What it means |
|---|---|
| **Supported** | What you have recorded meets this requirement |
| **Near threshold** | It meets it, but only just, so small changes could matter |
| **Requires judgement** | Guidance leaves room for a decision either way |
| **Professional review recommended** | This is beyond what the workspace should judge; talk to an adviser |
| **Not currently satisfied** | On what you have recorded, it is not met, and the workspace says what would change that |
| **Incomplete** | Something it needs is missing |
| **Inconsistent** | Some of your records disagree with each other |
| **Not yet assessed** | The workspace does not check this one yet |

A result can also be **out of date**. That means you changed something it depends on, such
as a trip, and it has not been rechecked yet. The old result stays visible, clearly marked,
until you update your assessment.

## How it keeps you safe

- **Nothing read from a document counts until you confirm it.** Suggestions are clearly
  marked as suggestions.
- **The checks are fixed calculations, not AI.** The same information always gives the same
  result, and the calculations are tested.
- **Every result shows its working:** the dates it used, the trips it counted, and the rule
  it applied.
- **There is no score and no "you're ready".** A percentage would hide the one detail that
  matters. Instead you see each requirement's result on its own.
- **When it is not sure, it says so.** Recommending a professional, or saying it cannot
  assess something, counts as the product working, not failing.
- **Your data is private.** Documents are stored privately, and only you can see your case.

## What it does not do

- It does not give legal advice or predict whether an application will succeed.
- It does not submit anything, connect to the Home Office, book appointments, or take
  payments.
- It does not cover the spouse route, children's registration, other registration routes,
  or people with pre-settled status.
- It does not assess good character, criminal records, or the referees in depth, and it does
  not decide cases that turn on discretion; it recommends a professional instead.
- It does not teach for the Life in the UK test or English, and does not connect to your email,
  calendar or travel accounts.
- It is not a chatbot, and there is no marketplace of advisers. The workspace is organised
  around your case, not a conversation.

## Where it stands

This is a working prototype built to show how an AI product can be trustworthy: the AI
suggests, a person decides, and the rules are ordinary, tested code. It uses made-up example
data only. What it does not do yet is listed openly in
[Known limitations](../KNOWN_LIMITATIONS.md).

## Further reading

| If you want | Read |
|---|---|
| How it is built | [Architecture overview](../architecture/ARCHITECTURE_OVERVIEW.md) |
| How the AI is tested | [AI evaluation](../evaluations/EVAL_REPORT.md) |
| A walkthrough of the demo | [Demo script](../DEMO_SCRIPT.md) |
